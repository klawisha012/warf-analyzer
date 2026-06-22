"""AuctionPoller — orchestration that ties client, analysis, repo, push."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.auction_poller import (
    RIVEN_CHANNEL_PREFIX,
    AuctionPoller,
)


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "test.db")
    await r.connect()
    yield r
    await r.close()


def _auc(aid: str, price: int) -> dict:
    return {
        "id": aid,
        "buyout_price": price,
        "starting_price": price // 2,
        "top_bid": None,
        "item": {
            "weapon_url_name": "tonkor",
            "polarity": "vazarin",
            "mod_rank": 8,
            "re_rolls": 0,
            "attributes": [
                {"url_name": "critical_damage", "value": 120, "positive": True}
            ],
        },
        "owner": {"ingame_name": "user", "status": "ingame", "platform": "pc"},
    }


@pytest.mark.asyncio
async def test_tick_with_empty_watchlist_does_nothing(repo: Repo) -> None:
    client = AsyncMock()
    publisher = AsyncMock()
    poller = AuctionPoller(repo=repo, client=client, publisher=publisher)
    await poller.tick()
    client.get_riven_auctions.assert_not_called()
    publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_tick_writes_snapshot_per_tier(repo: Repo) -> None:
    now = int(time.time())
    await repo.add_riven_watch("tonkor", ts=now)
    aucs = [_auc(f"a{i}", price=i * 10) for i in range(1, 13)]
    client = AsyncMock()
    client.get_riven_auctions = AsyncMock(return_value=aucs)
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    poller = AuctionPoller(repo=repo, client=client, publisher=publisher)
    await poller.tick(now=now)
    # Four snapshots written: god, mid, low, all
    for tier in ("god", "mid", "low", "all"):
        rows = await repo.riven_snapshot_history(
            weapon_slug="tonkor", tier=tier, since_ts=now - 10
        )
        assert len(rows) == 1, f"no snapshot for tier {tier}"


@pytest.mark.asyncio
async def test_tick_upserts_active_auctions_then_marks_disappeared_gone(
    repo: Repo,
) -> None:
    now = int(time.time())
    await repo.add_riven_watch("tonkor", ts=now)
    client = AsyncMock()
    publisher = AsyncMock()
    publisher.publish = AsyncMock()

    # First tick: 3 auctions present
    client.get_riven_auctions = AsyncMock(
        return_value=[_auc("a1", 100), _auc("a2", 200), _auc("a3", 300)]
    )
    poller = AuctionPoller(repo=repo, client=client, publisher=publisher)
    await poller.tick(now=now)
    active1 = {r["auction_id"] for r in await repo.active_riven_auctions("tonkor")}
    assert active1 == {"a1", "a2", "a3"}

    # Second tick: a2 disappeared, a4 new
    client.get_riven_auctions = AsyncMock(
        return_value=[_auc("a1", 100), _auc("a3", 300), _auc("a4", 400)]
    )
    await poller.tick(now=now + 60)
    active2 = {r["auction_id"] for r in await repo.active_riven_auctions("tonkor")}
    assert active2 == {"a1", "a3", "a4"}
    gone = await repo.recent_gone_riven_auctions("tonkor", since_ts=now)
    assert {r["auction_id"] for r in gone} == {"a2"}


@pytest.mark.asyncio
async def test_tick_publishes_outliers_when_history_exists(repo: Repo) -> None:
    now = int(time.time())
    await repo.add_riven_watch("tonkor", ts=now)
    # Seed historical mid-tier median = 500 (so anything ≤ 400 in mid is a >20% discount).
    for offset in range(1, 15):
        await repo.write_riven_snapshot(
            weapon_slug="tonkor",
            ts=now - offset * 3600,
            tier="mid",
            count=10,
            min_price=400,
            p25=450,
            median=500,
            p75=550,
            max_price=700,
        )
    # 12 auctions: prices placed so several land in the mid-quartile under cutoff.
    # Sorted prices: [200, 220, 250, 280, 300, 320, 400, 500, 600, 700, 800, 1000]
    # n=12 → low=[:3], mid=[3:9], god=[9:].
    # Mid quartile contains 280, 300, 320, 400, 500, 600 — first four are below 400 cutoff.
    aucs = [
        _auc(f"a{i}", price=p)
        for i, p in enumerate(
            [200, 220, 250, 280, 300, 320, 400, 500, 600, 700, 800, 1000]
        )
    ]
    client = AsyncMock()
    client.get_riven_auctions = AsyncMock(return_value=aucs)
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    poller = AuctionPoller(repo=repo, client=client, publisher=publisher)
    await poller.tick(now=now)
    # Should publish at least one outlier alert to rivens.tonkor.
    publishes = publisher.publish.await_args_list
    channels = {c.args[0] for c in publishes}
    assert f"{RIVEN_CHANNEL_PREFIX}tonkor" in channels


@pytest.mark.asyncio
async def test_tick_swallows_wfm_error(repo: Repo) -> None:
    """Client failure on one weapon must not abort the cycle."""
    from alecaframe_api.wfm.auctions_client import WFMAuctionError

    now = int(time.time())
    await repo.add_riven_watch("tonkor", ts=now)
    await repo.add_riven_watch("kuva_bramma", ts=now)
    client = AsyncMock()

    async def fake(slug: str, *, fresh: bool = False) -> list[dict]:
        if slug == "tonkor":
            raise WFMAuctionError("WFM down")
        return [_auc("ok1", 100), _auc("ok2", 200)]

    client.get_riven_auctions = AsyncMock(side_effect=fake)
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    poller = AuctionPoller(repo=repo, client=client, publisher=publisher)
    await poller.tick(now=now)
    # The healthy weapon still got a snapshot
    rows = await repo.riven_snapshot_history(
        weapon_slug="kuva_bramma", tier="all", since_ts=now - 10
    )
    assert len(rows) == 1
