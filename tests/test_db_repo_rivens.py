"""Repo tests for the rivens tables: watchlist, snapshots, auction tracking."""
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


# ----------------------------------------------------------- watchlist


@pytest.mark.asyncio
async def test_watchlist_add_list_remove(repo: Repo) -> None:
    now = int(time.time())
    await repo.add_riven_watch("tonkor", ts=now, notes=None)
    await repo.add_riven_watch("kuva_bramma", ts=now, notes="god disposition")
    rows = await repo.list_riven_watch()
    slugs = {r["weapon_slug"] for r in rows}
    assert slugs == {"tonkor", "kuva_bramma"}

    removed = await repo.remove_riven_watch("tonkor")
    assert removed is True
    rows = await repo.list_riven_watch()
    assert {r["weapon_slug"] for r in rows} == {"kuva_bramma"}


@pytest.mark.asyncio
async def test_watchlist_add_is_idempotent(repo: Repo) -> None:
    now = int(time.time())
    await repo.add_riven_watch("tonkor", ts=now)
    await repo.add_riven_watch("tonkor", ts=now + 1)
    rows = await repo.list_riven_watch()
    assert len(rows) == 1


# ----------------------------------------------------------- snapshot


@pytest.mark.asyncio
async def test_riven_snapshot_write_and_history(repo: Repo) -> None:
    base = int(time.time())
    for offset, median in [(0, 100), (60, 120), (120, 80)]:
        await repo.write_riven_snapshot(
            weapon_slug="tonkor", ts=base + offset, tier="all",
            count=10, min_price=20, p25=50, median=median, p75=150, max_price=500,
        )
    history = await repo.riven_snapshot_history(weapon_slug="tonkor", tier="all", since_ts=base)
    assert len(history) == 3
    # Ordered DESC.
    assert history[0]["median"] == 80
    assert history[-1]["median"] == 100


# ----------------------------------------------------------- per-auction tracking


@pytest.mark.asyncio
async def test_upsert_auction_inserts_then_updates(repo: Repo) -> None:
    now = int(time.time())
    await repo.upsert_riven_auction(
        auction_id="a1", weapon_slug="tonkor", seen_at=now,
        buyout_price=200, starting_price=50, top_bid=None,
        re_rolls=4, mod_rank=8, polarity="vazarin",
        attributes=[{"name": "critical_damage", "value": 121, "positive": True}],
        owner_name="user1", owner_status="ingame", tier="god",
    )
    # Second seen: price reduced, tier reclassified.
    await repo.upsert_riven_auction(
        auction_id="a1", weapon_slug="tonkor", seen_at=now + 60,
        buyout_price=150, starting_price=50, top_bid=120,
        re_rolls=4, mod_rank=8, polarity="vazarin",
        attributes=[{"name": "critical_damage", "value": 121, "positive": True}],
        owner_name="user1", owner_status="online", tier="mid",
    )
    rows = await repo.active_riven_auctions("tonkor")
    assert len(rows) == 1
    row = rows[0]
    assert row["first_seen"] == now
    assert row["last_seen"] == now + 60
    assert row["buyout_price"] == 150
    assert row["tier"] == "mid"
    assert row["status"] == "active"


@pytest.mark.asyncio
async def test_mark_gone_flips_status_and_records_ts(repo: Repo) -> None:
    now = int(time.time())
    await repo.upsert_riven_auction(
        auction_id="a1", weapon_slug="tonkor", seen_at=now,
        buyout_price=200, starting_price=50, top_bid=None,
        re_rolls=0, mod_rank=8, polarity=None, attributes=[],
        owner_name="user", owner_status="ingame", tier="god",
    )
    # Not present in next poll → mark gone
    n = await repo.mark_riven_auctions_gone(
        weapon_slug="tonkor", seen_ids=set(), at=now + 60,
    )
    assert n == 1
    rows = await repo.active_riven_auctions("tonkor")
    assert rows == []
    # Gone row still readable via direct query
    gone = await repo.recent_gone_riven_auctions("tonkor", since_ts=now)
    assert len(gone) == 1
    assert gone[0]["gone_at"] == now + 60
    assert gone[0]["status"] == "gone"


@pytest.mark.asyncio
async def test_mark_gone_leaves_still_seen_active(repo: Repo) -> None:
    now = int(time.time())
    for aid in ("a1", "a2"):
        await repo.upsert_riven_auction(
            auction_id=aid, weapon_slug="tonkor", seen_at=now,
            buyout_price=100, starting_price=50, top_bid=None,
            re_rolls=0, mod_rank=8, polarity=None, attributes=[],
            owner_name="u", owner_status="ingame", tier="mid",
        )
    n = await repo.mark_riven_auctions_gone(
        weapon_slug="tonkor", seen_ids={"a2"}, at=now + 60,
    )
    assert n == 1  # only a1 gone
    active = {r["auction_id"] for r in await repo.active_riven_auctions("tonkor")}
    assert active == {"a2"}
