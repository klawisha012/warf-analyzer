"""Repo tests — snapshot insert + read, signal dedup, set compositions."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from alecaframe_api.db.repo import Repo


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "test.db")
    await r.connect()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_insert_and_query_snapshot(repo: Repo) -> None:
    now = int(time.time())
    await repo.insert_snapshot(
        slug="kronen_prime_blade",
        ts=now,
        side="sell",
        online_only=1,
        count_orders=3,
        min_price=35,
        p10=35,
        p25=36,
        median=36,
        p75=37,
        p90=38,
        max_price=38,
        volume_qty=4,
        top5=[35, 36, 36, 37, 38],
    )
    rows = await repo.history(
        slug="kronen_prime_blade", side="sell", online_only=1, since_ts=now - 60
    )
    assert len(rows) == 1
    assert rows[0]["min_price"] == 35
    assert rows[0]["top5"] == [35, 36, 36, 37, 38]


@pytest.mark.asyncio
async def test_insert_signal_event_dedup(repo: Repo) -> None:
    now = int(time.time())
    inserted_a = await repo.insert_signal_event(
        ts=now,
        slug="x",
        signal_type="undervalued_mine",
        payload={"diff": 5},
        dedup_key="undervalued_mine:x:2026-05-25",
    )
    inserted_b = await repo.insert_signal_event(
        ts=now + 1,
        slug="x",
        signal_type="undervalued_mine",
        payload={"diff": 6},
        dedup_key="undervalued_mine:x:2026-05-25",
    )
    assert inserted_a is True
    assert inserted_b is False  # second insert is a no-op


@pytest.mark.asyncio
async def test_set_compositions_roundtrip(repo: Repo) -> None:
    await repo.upsert_set_composition("kronen_prime_set", "kronen_prime_blade", 2)
    await repo.upsert_set_composition("kronen_prime_set", "kronen_prime_handle", 1)
    rows = await repo.read_set_compositions()
    by_set = {r["set_slug"]: r for r in rows}
    assert by_set["kronen_prime_set"]["parts"] == {
        "kronen_prime_blade": 2,
        "kronen_prime_handle": 1,
    }


@pytest.mark.asyncio
async def test_recent_signals_filtered(repo: Repo) -> None:
    now = int(time.time())
    await repo.insert_signal_event(now - 100, "x", "undervalued_mine", {}, "a")
    await repo.insert_signal_event(now - 50, "y", "competitor_undercut", {}, "b")
    await repo.insert_signal_event(now - 10, "z", "undervalued_mine", {}, "c")
    rows = await repo.recent_signals(types=["undervalued_mine"], limit=10)
    assert [r["slug"] for r in rows] == ["z", "x"]  # newest first
