"""PriceStore tests — in-memory map of slug -> PriceStats with staleness."""
from __future__ import annotations

import time

import pytest

from alecaframe_api.wfm.price_store import PriceStats, PriceStore


def test_set_and_get_roundtrip() -> None:
    store = PriceStore()
    stats = PriceStats(
        slug="kronen_prime_blade",
        sell_min=30, sell_median=35, sell_spread=10, buy_max=28,
        fetched_at=time.time(),
    )
    store.set(stats)
    got = store.get("kronen_prime_blade")
    assert got == stats


def test_get_missing_returns_none() -> None:
    assert PriceStore().get("unknown_slug") is None


def test_bulk_get_returns_only_known() -> None:
    store = PriceStore()
    s1 = PriceStats(slug="a", sell_min=1, sell_median=2, sell_spread=0, buy_max=1, fetched_at=time.time())
    store.set(s1)
    out = store.bulk_get(["a", "b"])
    assert out == {"a": s1}


def test_snapshot_returns_copy() -> None:
    store = PriceStore()
    s = PriceStats(slug="x", sell_min=1, sell_median=2, sell_spread=0, buy_max=1, fetched_at=time.time())
    store.set(s)
    snap = store.snapshot()
    assert snap == {"x": s}
    # Mutating snapshot must not affect store.
    snap.pop("x")
    assert store.get("x") == s


def test_stale_slugs_filters_by_age() -> None:
    store = PriceStore()
    now = time.time()
    fresh = PriceStats(slug="fresh", sell_min=1, sell_median=2, sell_spread=0, buy_max=1, fetched_at=now)
    old = PriceStats(slug="old", sell_min=1, sell_median=2, sell_spread=0, buy_max=1, fetched_at=now - 30)
    store.set(fresh)
    store.set(old)
    # threshold=10s: only "old" is stale, "fresh" is not
    assert store.stale_slugs(["fresh", "old", "missing"], max_age=10.0, now=now) == {"old", "missing"}


def test_stale_slugs_includes_missing() -> None:
    """Slugs absent from the store are always considered stale (need fetch)."""
    store = PriceStore()
    assert store.stale_slugs(["a", "b"], max_age=10.0) == {"a", "b"}


def test_set_overwrites_previous() -> None:
    store = PriceStore()
    s1 = PriceStats(slug="x", sell_min=10, sell_median=12, sell_spread=2, buy_max=8, fetched_at=1.0)
    s2 = PriceStats(slug="x", sell_min=20, sell_median=22, sell_spread=2, buy_max=18, fetched_at=2.0)
    store.set(s1)
    store.set(s2)
    assert store.get("x") == s2
