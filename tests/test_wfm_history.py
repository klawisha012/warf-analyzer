"""history.write_snapshot orchestration tests."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.history import write_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "wfm_orders_kronen_prime_blade.json"


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "h.db")
    await r.connect()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_write_snapshot_writes_4_rows(repo: Repo) -> None:
    """One snapshot writes (sell, buy) × (online_only=1, =0) = 4 rows."""
    orders = json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]
    ts = int(time.time())
    await write_snapshot(repo=repo, slug="kronen_prime_blade", orders=orders, ts=ts)
    # Verify 4 keys: sell-online, sell-all, buy-online, buy-all.
    sells_online = await repo.history(slug="kronen_prime_blade", side="sell",
                                      online_only=1, since_ts=ts - 60)
    sells_all = await repo.history(slug="kronen_prime_blade", side="sell",
                                   online_only=0, since_ts=ts - 60)
    buys_online = await repo.history(slug="kronen_prime_blade", side="buy",
                                     online_only=1, since_ts=ts - 60)
    buys_all = await repo.history(slug="kronen_prime_blade", side="buy",
                                  online_only=0, since_ts=ts - 60)
    assert len(sells_online) == 1
    assert len(sells_all) == 1
    assert len(buys_online) == 1
    assert len(buys_all) == 1
    # Sanity: online sell median is 36 (from prices test)
    assert sells_online[0]["median"] == 36


@pytest.mark.asyncio
async def test_write_snapshot_idempotent_at_same_ts(repo: Repo) -> None:
    """INSERT OR REPLACE means same ts produces same row count."""
    orders = json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]
    ts = int(time.time())
    await write_snapshot(repo=repo, slug="kronen_prime_blade", orders=orders, ts=ts)
    await write_snapshot(repo=repo, slug="kronen_prime_blade", orders=orders, ts=ts)
    rows = await repo.history(slug="kronen_prime_blade", side="sell", online_only=1,
                              since_ts=ts - 60)
    assert len(rows) == 1
