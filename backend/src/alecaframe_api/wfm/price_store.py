"""In-memory price store — the global source of truth for slug -> PriceStats.

Populated by:
- /me/* endpoints (lazy: when a slug is requested and absent from the store,
  the calling endpoint may fetch and `set()` it).
- PricePoller background task (refreshes slugs whose Centrifugo channel has
  active subscribers).

Read by:
- /me/* endpoints (bulk_get for the entire composition).
- /prices snapshot endpoint (frontend cold-load bootstrap).

PriceStats is intentionally narrow — only what the UI needs to render a card
or set row. Full order books still live behind /wfm/orders/{slug} for deep
inspection. We do NOT persist this store to Redis: process restart triggers
a cold refetch on first /me/* hit, which finishes in single-digit seconds
thanks to parallel WFMClient + the Redis L1 cache it already uses.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PriceStats:
    """Snapshot of WFM order-book stats for a single slug."""
    slug: str
    sell_min: int | None
    sell_median: int | None
    sell_spread: int | None
    buy_max: int | None
    fetched_at: float           # unix timestamp; used by stale_slugs()
    stale: bool = False         # True if fetched_at is from a stale-fallback (WFM down)
    sell_min_max_rank: int | None = None
    buy_max_max_rank: int | None = None
    max_rank: int | None = None


class PriceStore:
    """Thread-safe-enough for asyncio: dict ops in CPython are atomic at the
    bytecode level, so we don't add a lock. The poller and request handlers
    coexist by serialising through the event loop — no true concurrency."""

    def __init__(self) -> None:
        self._map: dict[str, PriceStats] = {}

    def set(self, stats: PriceStats) -> None:
        self._map[stats.slug] = stats

    def get(self, slug: str) -> PriceStats | None:
        return self._map.get(slug)

    def bulk_get(self, slugs: Iterable[str]) -> dict[str, PriceStats]:
        out: dict[str, PriceStats] = {}
        for s in slugs:
            v = self._map.get(s)
            if v is not None:
                out[s] = v
        return out

    def snapshot(self) -> dict[str, PriceStats]:
        return dict(self._map)

    def stale_slugs(
        self,
        slugs: Iterable[str],
        *,
        max_age: float,
        now: float | None = None,
    ) -> set[str]:
        """Return the subset of `slugs` whose record is missing OR older than
        `max_age` seconds. Used by PricePoller to decide what to refetch."""
        t = now if now is not None else time.time()
        out: set[str] = set()
        for s in slugs:
            rec = self._map.get(s)
            if rec is None or (t - rec.fetched_at) > max_age:
                out.add(s)
        return out
