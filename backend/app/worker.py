"""Async background scanner — the FastAPI replacement for ``AuctionWorker``.

Port of the 4-mode state machine from ``scanner2.AuctionWorker.run``:

    GROLL              → bootstrap, fires the GROLL query once on startup
    BASE_API           → poll /auctions; promotes to WEAPON_FOR_DB_SEARCH on new IDs
    WEAPON_FOR_DB_SEARCH → cycle through good_weapons, writing top-3 prices
    WEAPON_FAST_SEARCH   → cycle through fast_weapons_list, watching for alerts

All concurrency primitives are asyncio — no threads, no QThread, no time.sleep.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI

from app import repositories, settings_store
from app.alert_rules import riven_alert_check
from app.db import async_session
from app.market_client import MarketClient
from app.ws import ConnectionManager

logger = logging.getLogger(__name__)

# How often to refresh in-memory copies of the AppSetting rows. The settings
# rarely change at runtime, so once per ~20 iterations is plenty cheap.
SETTINGS_REFRESH_EVERY = 20

# Timeout to flip back to BASE_API when nothing has happened (mirrors scanner2:
# `time.time() - last_api_update > 100`).
BASE_API_RESET_SECONDS = 100

# Mirror scanner2: write WEAPON_FOR_DB_SEARCH samples 6 times then switch.
DB_WRITES_PER_CYCLE = 6


async def _load_settings_snapshot() -> tuple[dict[str, int], list[str]]:
    async with async_session() as session:
        good = await settings_store.get_good_weapons(session)
        fast = await settings_store.get_fast_weapons_list(session)
    return good, fast


async def _seed_seen_ids() -> set[str]:
    async with async_session() as session:
        ids = await repositories.list_saved_groll_ids(session)
    return set(ids)


def _extract_top_prices(auctions: list[dict[str, Any]]) -> list[int]:
    """Mirror of ``scanner2.write_prices_to_db`` price-extraction logic.

    Take the first ≤3 buyout prices from non-offline owners. Pad with ``-1``
    sentinels so the row always has exactly 3 columns (matches the legacy
    SQLite schema).
    """
    prices: list[int] = []
    for auction in auctions:
        owner = auction.get("owner") or {}
        if owner.get("status") == "offline":
            continue
        buyout = auction.get("buyout_price")
        if buyout is None:
            continue
        prices.append(int(buyout))
        if len(prices) >= 3:
            break
    while len(prices) < 3:
        prices.append(-1)
    return prices


async def _broadcast_alert(
    app: FastAPI,
    auction: dict[str, Any],
    reason: str,
) -> None:
    """Push an alert onto the in-memory deque and broadcast over WS."""
    payload = {"type": "alert", "auction": auction, "reason": reason}
    # Newest first — push to the left of the deque.
    app.state.recent_alerts.appendleft(payload)
    manager: ConnectionManager = app.state.ws_manager
    await manager.broadcast_json(payload)


async def _broadcast_stats(app: FastAPI) -> None:
    manager: ConnectionManager = app.state.ws_manager
    await manager.broadcast_json(
        {"type": "stats", "api_updates": app.state.api_update_count}
    )


async def _handle_auctions(
    app: FastAPI,
    auctions: list[dict[str, Any]],
    good_weapons: dict[str, int],
    seen_ids: set[str],
) -> int:
    """Run the alert rules over a freshly-fetched batch.

    Returns the number of *new* (previously-unseen) auction IDs. The caller
    uses this number to drive the GROLL/BASE_API → WEAPON_FOR_DB_SEARCH
    transition (same trigger as scanner2.newRivensCount).
    """
    new_count = 0
    saved_ids: set[str] = app.state.saved_groll_ids

    for auction in auctions:
        auc_id = auction.get("id")
        if not auc_id:
            continue

        # Skip anything the user has already saved (loaded on boot from
        # SavedGroll, kept in sync by the POST /api/groll route).
        if auc_id in saved_ids:
            continue

        if auc_id not in seen_ids:
            seen_ids.add(auc_id)
            new_count += 1

        reason = riven_alert_check(auction, good_weapons)
        if reason == "none":
            continue

        # Don't re-alert on auctions we've already pushed once this session.
        if auc_id in app.state.alerted_ids:
            continue
        app.state.alerted_ids.add(auc_id)

        await _broadcast_alert(app, auction, reason)

    return new_count


async def _write_weapon_prices(
    auctions: list[dict[str, Any]],
    weapon: str,
) -> None:
    if not auctions:
        return
    prices = _extract_top_prices(auctions)
    async with async_session() as session:
        await repositories.insert_price_sample(
            session,
            weapon,
            prices[0],
            prices[1],
            prices[2],
            ts=datetime.now(timezone.utc),
        )


async def run_scanner(app: FastAPI) -> None:
    """Long-running worker. Cancelled by the FastAPI lifespan on shutdown."""
    logger.info("scanner: starting up")

    # Lazy: the market client wraps app.state.http (created in lifespan).
    market = MarketClient(app.state.http)
    app.state.market = market

    # In-memory state mirrored from scanner2.
    seen_ids: set[str] = set()
    app.state.seen_ids = seen_ids
    app.state.alerted_ids = set()
    app.state.saved_groll_ids = await _seed_seen_ids()

    good_weapons, fast_weapons_list = await _load_settings_snapshot()
    iters_since_refresh = 0

    mode = "GROLL"
    first_run = True
    fast_idx = 0
    good_idx = 0
    written_to_db = 0
    last_api_update = time.monotonic()

    try:
        while True:
            # Periodic settings refresh — cheaper than touching the DB every loop.
            if iters_since_refresh >= SETTINGS_REFRESH_EVERY:
                good_weapons, fast_weapons_list = await _load_settings_snapshot()
                iters_since_refresh = 0
            iters_since_refresh += 1

            good_weapons_list = list(good_weapons)

            # Wrap indices.
            if fast_weapons_list and fast_idx >= len(fast_weapons_list):
                fast_idx = 0
            if good_weapons_list and good_idx >= len(good_weapons_list):
                good_idx = 0

            try:
                response: httpx.Response | None = None
                current_weapon: str | None = None

                if mode == "GROLL":
                    logger.info("scanner: GROLL fetch")
                    response = await market.get_groll()
                elif mode == "BASE_API":
                    logger.info("scanner: BASE_API fetch")
                    response = await market.get_base_api()
                    fast_idx = 0
                elif mode == "WEAPON_FAST_SEARCH":
                    if not fast_weapons_list:
                        # Nothing to scan — flip back to BASE_API.
                        mode = "BASE_API"
                        await asyncio.sleep(1.0)
                        continue
                    current_weapon = fast_weapons_list[fast_idx]
                    logger.info("scanner: WEAPON_FAST_SEARCH %s", current_weapon)
                    response = await market.get_by_weapon(current_weapon)
                    fast_idx += 1
                    if fast_idx >= len(fast_weapons_list):
                        fast_idx = 0
                elif mode == "WEAPON_FOR_DB_SEARCH":
                    if not good_weapons_list:
                        mode = "BASE_API"
                        await asyncio.sleep(1.0)
                        continue
                    current_weapon = good_weapons_list[good_idx]
                    logger.info("scanner: WEAPON_FOR_DB_SEARCH %s", current_weapon)
                    response = await market.get_by_weapon(current_weapon)
                    good_idx += 1
                    written_to_db += 1

                if response is None:
                    await asyncio.sleep(1.0)
                    continue

                if response.status_code != 200:
                    logger.warning(
                        "scanner: HTTP %s for mode=%s body=%s",
                        response.status_code,
                        mode,
                        response.text[:200],
                    )
                    await market.backoff()
                    continue

                payload = response.json().get("payload") or {}
                auctions = payload.get("auctions") or []

                # Persist weapon prices for the two weapon-mode fetches.
                if (
                    mode in {"WEAPON_FAST_SEARCH", "WEAPON_FOR_DB_SEARCH"}
                    and current_weapon
                ):
                    await _write_weapon_prices(auctions, current_weapon)

                new_count = await _handle_auctions(
                    app, auctions, good_weapons, seen_ids
                )

                # Mode-transition logic — mirrors scanner2 verbatim.
                if (
                    new_count > 0
                    and not first_run
                    and mode == "BASE_API"
                ):
                    logger.info(
                        "scanner: api update detected (%d new) → WEAPON_FOR_DB_SEARCH",
                        new_count,
                    )
                    app.state.api_update_count += 1
                    await _broadcast_stats(app)
                    mode = "WEAPON_FOR_DB_SEARCH"
                    last_api_update = time.monotonic()
                elif mode == "WEAPON_FOR_DB_SEARCH" and written_to_db > DB_WRITES_PER_CYCLE:
                    logger.info("scanner: WEAPON_FOR_DB_SEARCH cycle done → WEAPON_FAST_SEARCH")
                    mode = "WEAPON_FAST_SEARCH"
                    written_to_db = 0

                if (
                    time.monotonic() - last_api_update > BASE_API_RESET_SECONDS
                    and mode != "BASE_API"
                ):
                    logger.info("scanner: idle timeout → BASE_API")
                    mode = "BASE_API"

                if mode == "BASE_API":
                    first_run = False
                elif mode == "GROLL" and first_run:
                    mode = "BASE_API"
                elif mode == "GROLL":
                    logger.info("scanner: GROLL → WEAPON_FAST_SEARCH")
                    mode = "WEAPON_FAST_SEARCH"

            except asyncio.CancelledError:
                raise
            except httpx.HTTPError as exc:
                logger.warning("scanner: httpx error: %s", exc)
                await asyncio.sleep(5.0)
            except Exception as exc:  # noqa: BLE001 — must not kill the loop
                logger.exception("scanner: unexpected error: %s", exc)
                await asyncio.sleep(5.0)

    except asyncio.CancelledError:
        logger.info("scanner: cancellation received, shutting down")
        raise
