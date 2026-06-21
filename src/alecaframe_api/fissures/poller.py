"""FissurePoller — periodic match of live fissures against subscriptions.

Per tick:
1. Fetch live fissures (errors logged, tick never aborts).
2. Read enabled subscriptions; if none, just prune the ledger and return.
3. For each subscription × matching fissure not yet in the dedup ledger:
   record it, then (if Telegram is on) broadcast to every registered chat.
4. Prune ledger entries older than NOTIFICATION_TTL_S."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.client import FissureClient, FissureClientError
from alecaframe_api.fissures.matcher import matches
from alecaframe_api.fissures.models import Fissure, Subscription
from alecaframe_api.fissures.telegram import TelegramClient

log = logging.getLogger("alecaframe.fissures.poller")

DEFAULT_POLL_INTERVAL_S = 60.0
NOTIFICATION_TTL_S = 3 * 3600


def format_message(f: Fissure) -> str:
    track: list[str] = []
    if f.is_hard:
        track.append("Стальной путь")
    if f.is_storm:
        track.append("Void Storm")
    line2 = f"{f.era} · {f.mission_type}"
    if track:
        line2 += " · " + ", ".join(track)
    bits = ["🌀 Новый разрыв Бездны", line2]
    if f.node:
        bits.append(f.node)
    return "\n".join(bits)


def _row_to_sub(r: dict) -> Subscription:
    def _b(v) -> bool | None:
        return None if v is None else bool(v)
    return Subscription(
        id=int(r["id"]), era=r["era"], mission_type=r["mission_type"],
        is_hard=_b(r["is_hard"]), is_storm=_b(r["is_storm"]),
        enabled=bool(r["enabled"]), created_at=int(r["created_at"]),
    )


@dataclass
class FissurePoller:
    repo: Repo
    client: FissureClient
    telegram: TelegramClient | None = None
    poll_interval: float = DEFAULT_POLL_INTERVAL_S

    async def tick(self, *, now: int | None = None) -> None:
        t = now if now is not None else int(time.time())
        try:
            fissures = await self.client.get_fissures()
        except FissureClientError as e:
            log.warning("fissure fetch failed: %s; skipping tick", e)
            return
        subs_raw = await self.repo.list_fissure_subscriptions(enabled_only=True)
        if not subs_raw:
            await self.repo.prune_fissure_notifications(older_than=t - NOTIFICATION_TTL_S)
            return
        subs = [_row_to_sub(r) for r in subs_raw]
        chats = await self.repo.list_telegram_chats()
        for sub in subs:
            for f in fissures:
                if not matches(f, sub):
                    continue
                newly = await self.repo.record_fissure_notification(
                    subscription_id=sub.id, fissure_id=f.id, ts=t,
                )
                if not newly:
                    continue
                if self.telegram is not None and chats:
                    text = format_message(f)
                    for chat in chats:
                        await self.telegram.send_message(int(chat["chat_id"]), text)
        await self.repo.prune_fissure_notifications(older_than=t - NOTIFICATION_TTL_S)

    async def run(self) -> None:
        log.info("fissure poller starting; interval=%.1fs", self.poll_interval)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("fissure poller tick failed: %s", e)
            await asyncio.sleep(self.poll_interval)
