from __future__ import annotations

import pytest

from alecaframe_api.db.repo import Repo


@pytest.fixture
async def repo(tmp_path):
    r = Repo(db_path=tmp_path / "t.db")
    await r.connect()
    yield r
    await r.close()


async def test_subscription_crud(repo: Repo) -> None:
    sub_id = await repo.add_fissure_subscription(
        era="Axi", mission_type=None, is_hard=True, is_storm=None, ts=100,
    )
    assert isinstance(sub_id, int)
    rows = await repo.list_fissure_subscriptions()
    assert len(rows) == 1
    assert rows[0]["era"] == "Axi"
    assert rows[0]["mission_type"] is None
    assert rows[0]["is_hard"] == 1
    assert rows[0]["is_storm"] is None
    assert rows[0]["enabled"] == 1
    assert await repo.remove_fissure_subscription(sub_id) is True
    assert await repo.remove_fissure_subscription(sub_id) is False
    assert await repo.list_fissure_subscriptions() == []


async def test_enabled_only_filter(repo: Repo) -> None:
    await repo.add_fissure_subscription(era="Lith", mission_type=None, is_hard=None, is_storm=None, ts=1)
    rows = await repo.list_fissure_subscriptions(enabled_only=True)
    assert len(rows) == 1


async def test_register_telegram_chat_idempotent(repo: Repo) -> None:
    await repo.register_telegram_chat(chat_id=555, username="alice", ts=10)
    await repo.register_telegram_chat(chat_id=555, username="alice2", ts=20)
    chats = await repo.list_telegram_chats()
    assert len(chats) == 1
    assert chats[0]["chat_id"] == 555
    assert chats[0]["username"] == "alice2"  # username updated, row not duplicated


async def test_notification_dedup_and_prune(repo: Repo) -> None:
    assert await repo.record_fissure_notification(subscription_id=1, fissure_id="f1", ts=100) is True
    assert await repo.record_fissure_notification(subscription_id=1, fissure_id="f1", ts=200) is False
    assert await repo.record_fissure_notification(subscription_id=1, fissure_id="f2", ts=100) is True
    pruned = await repo.prune_fissure_notifications(older_than=150)
    assert pruned == 2  # f1@100 and f2@100 removed; none left below 150
