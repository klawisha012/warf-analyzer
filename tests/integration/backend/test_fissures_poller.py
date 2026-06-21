from __future__ import annotations

import pytest

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.fissures.poller import FissurePoller, format_message


@pytest.fixture
async def repo(tmp_path):
    r = Repo(db_path=tmp_path / "t.db")
    await r.connect()
    yield r
    await r.close()


def _f(fid: str, era: str, mt: str = "Survival", hard=False, storm=False) -> Fissure:
    return Fissure(id=fid, era=era, mission_type=mt, node="X (Eris)", planet="Eris",
                   enemy="Infested", is_hard=hard, is_storm=storm, activation=None, expiry=None)


class _FakeClient:
    def __init__(self, fissures: list[Fissure]) -> None:
        self.fissures = fissures

    async def get_fissures(self, *, now=None, fresh=False) -> list[Fissure]:
        return self.fissures


class _FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


@pytest.mark.asyncio
async def test_notify_then_dedup_then_new(repo: Repo) -> None:
    await repo.add_fissure_subscription(era="Axi", mission_type=None, is_hard=None, is_storm=None, ts=1)
    await repo.register_telegram_chat(chat_id=555, username=None, ts=1)
    client = _FakeClient([_f("a1", "Axi"), _f("l1", "Lith")])
    tg = _FakeTelegram()
    poller = FissurePoller(repo=repo, client=client, telegram=tg)

    await poller.tick(now=1000)
    assert len(tg.sent) == 1 and tg.sent[0][0] == 555  # only the Axi one matched

    await poller.tick(now=1001)
    assert len(tg.sent) == 1  # dedup: same fissure not re-sent

    client.fissures.append(_f("a2", "Axi"))
    await poller.tick(now=1002)
    assert len(tg.sent) == 2  # new Axi fissure fires once


@pytest.mark.asyncio
async def test_no_subscriptions_is_noop(repo: Repo) -> None:
    client = _FakeClient([_f("a1", "Axi")])
    tg = _FakeTelegram()
    poller = FissurePoller(repo=repo, client=client, telegram=tg)
    await poller.tick(now=1)
    assert tg.sent == []


def test_format_message_includes_axes() -> None:
    msg = format_message(_f("a1", "Axi", mt="Survival", hard=True))
    assert "Axi" in msg and "Survival" in msg


@pytest.mark.asyncio
async def test_node_filtered_subscription_only_fires_for_match(repo: Repo) -> None:
    await repo.add_fissure_subscription(
        era=None, mission_type=None, planet=None, node="Proteus",
        is_hard=None, is_storm=None, ts=1,
    )
    await repo.register_telegram_chat(chat_id=42, username=None, ts=1)
    f_match = Fissure(id="m1", era="Axi", mission_type="Survival",
                      node="Proteus (Neptune)", planet="Neptune", enemy=None,
                      is_hard=False, is_storm=False, activation=None, expiry=None)
    f_other = _f("o1", "Axi")  # node "X (Eris)"
    tg = _FakeTelegram()
    poller = FissurePoller(repo=repo, client=_FakeClient([f_match, f_other]), telegram=tg)

    await poller.tick(now=1000)
    assert len(tg.sent) == 1  # only the Proteus node matched
