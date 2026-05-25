"""AuctionPoller — periodic refresh of every watchlisted weapon.

Per tick:
1. Read watchlist from `riven_watchlist`.
2. For each weapon (in parallel): fetch live auctions via WFMAuctionClient.
3. Classify into god/mid/low tiers, compute distribution stats per tier.
4. Write snapshots (one row per tier + an 'all' row).
5. Upsert each seen auction into `riven_auction`; mark unseen ones 'gone'.
6. Look up the rolling historical median per tier from `riven_snapshot`
   (last 7 days). Run outlier detection against it. Publish each outlier
   to Centrifugo channel `rivens.{slug}`.

Errors from one weapon never abort the tick — they're logged and the next
weapon proceeds.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from alecaframe_api.db.repo import Repo
from alecaframe_api.infra.push import CentrifugoPublisher
from alecaframe_api.wfm.auctions_client import WFMAuctionClient, WFMAuctionError
from alecaframe_api.wfm.rivens_analysis import (
    classify_tiers, compute_tier_stats, detect_outliers,
)

log = logging.getLogger("alecaframe.wfm.auction_poller")


RIVEN_CHANNEL_PREFIX = "rivens."
DEFAULT_POLL_INTERVAL_S = 60.0
DEFAULT_OUTLIER_THRESHOLD = 0.8
HISTORICAL_WINDOW_S = 7 * 24 * 3600


@dataclass
class AuctionPoller:
    repo: Repo
    client: WFMAuctionClient
    publisher: CentrifugoPublisher
    poll_interval: float = DEFAULT_POLL_INTERVAL_S
    outlier_threshold: float = DEFAULT_OUTLIER_THRESHOLD

    async def tick(self, *, now: int | None = None) -> None:
        t = now if now is not None else int(time.time())
        try:
            watchlist = await self.repo.list_riven_watch()
        except Exception as e:
            log.warning("watchlist read failed: %s; skipping tick", e)
            return
        if not watchlist:
            return
        await asyncio.gather(
            *[self._process_weapon(row["weapon_slug"], t) for row in watchlist],
            return_exceptions=True,
        )

    async def _process_weapon(self, weapon_slug: str, now: int) -> None:
        try:
            auctions = await self.client.get_riven_auctions(weapon_slug)
        except WFMAuctionError as e:
            log.warning("riven fetch %s failed: %s", weapon_slug, e)
            return
        except Exception as e:
            log.warning("riven fetch %s unexpected: %s", weapon_slug, e)
            return

        tiers = classify_tiers(auctions)
        # Write per-tier + overall snapshots
        await self._snapshot(weapon_slug, now, "all", auctions)
        for tier_name in ("god", "mid", "low"):
            await self._snapshot(weapon_slug, now, tier_name, tiers[tier_name])

        # Per-auction tracking — upsert current, mark missing as 'gone'.
        seen_ids: set[str] = set()
        tier_of: dict[str, str] = {}
        for tier_name in ("god", "mid", "low"):
            for a in tiers[tier_name]:
                tier_of[str(a.get("id") or "")] = tier_name
        for a in auctions:
            aid = str(a.get("id") or "")
            if not aid:
                continue
            seen_ids.add(aid)
            item = a.get("item") or {}
            try:
                await self.repo.upsert_riven_auction(
                    auction_id=aid, weapon_slug=weapon_slug, seen_at=now,
                    buyout_price=_int_or_none(a.get("buyout_price")),
                    starting_price=_int_or_none(a.get("starting_price")),
                    top_bid=_int_or_none(a.get("top_bid")),
                    re_rolls=_int_or_none(item.get("re_rolls")),
                    mod_rank=_int_or_none(item.get("mod_rank")),
                    polarity=item.get("polarity"),
                    attributes=item.get("attributes") or [],
                    owner_name=((a.get("owner") or {}).get("ingame_name")),
                    tier=tier_of.get(aid, "mid"),
                )
            except Exception as e:
                log.warning("upsert auction %s failed: %s", aid, e)
        try:
            await self.repo.mark_riven_auctions_gone(
                weapon_slug=weapon_slug, seen_ids=seen_ids, at=now,
            )
        except Exception as e:
            log.warning("mark-gone for %s failed: %s", weapon_slug, e)

        # Outlier detection vs historical median per tier.
        await self._publish_outliers(weapon_slug, now, tiers)

    async def _snapshot(
        self, weapon_slug: str, now: int, tier: str, auctions: list[dict],
    ) -> None:
        stats = compute_tier_stats(auctions)
        await self.repo.write_riven_snapshot(
            weapon_slug=weapon_slug, ts=now, tier=tier,
            count=stats.count, min_price=stats.min_price,
            p25=stats.p25, median=stats.median, p75=stats.p75, max_price=stats.max_price,
        )

    async def _publish_outliers(
        self, weapon_slug: str, now: int, tiers: dict[str, list[dict]],
    ) -> None:
        # Use the prior week's snapshots (excluding the one we just wrote)
        # so the comparison is against the rolling history, not our own
        # current snapshot.
        since = now - HISTORICAL_WINDOW_S
        for tier_name in ("god", "mid", "low"):
            history = await self.repo.riven_snapshot_history(
                weapon_slug=weapon_slug, tier=tier_name, since_ts=since,
            )
            historical_medians = [r["median"] for r in history if r["median"] is not None and r["ts"] != now]
            if not historical_medians:
                continue
            # Median of medians — robust to outlier days.
            import statistics as _stats
            hist_median = int(_stats.median(historical_medians))
            outliers = detect_outliers(
                tiers[tier_name], historical_median=hist_median,
                threshold=self.outlier_threshold, tier=tier_name,
            )
            for o in outliers:
                try:
                    await self.publisher.publish(
                        f"{RIVEN_CHANNEL_PREFIX}{weapon_slug}",
                        {
                            "kind": "outlier",
                            "weapon_slug": weapon_slug,
                            "auction_id": o.auction_id,
                            "tier": o.tier,
                            "price": o.price,
                            "historical_median": o.historical_median,
                            "discount_pct": o.discount_pct,
                            "ts": now,
                        },
                    )
                except Exception as e:
                    log.warning("publish outlier %s failed: %s", o.auction_id, e)

    async def run(self) -> None:
        log.info("auction poller starting; interval=%.1fs threshold=%.2f",
                 self.poll_interval, self.outlier_threshold)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("auction poller tick failed: %s", e)
            await asyncio.sleep(self.poll_interval)


def _int_or_none(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
