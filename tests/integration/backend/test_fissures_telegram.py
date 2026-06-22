from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.telegram import TelegramBot, TelegramClient


@pytest.fixture
async def repo(tmp_path):
    r = Repo(db_path=tmp_path / "t.db")
    await r.connect()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_send_message_hits_correct_url(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://tg.test/botTOKEN/sendMessage",
        method="POST",
        json={"ok": True},
    )
    c = TelegramClient(token="TOKEN", base_url="https://tg.test")
    ok = await c.send_message(555, "hi")
    assert ok is True
    req = httpx_mock.get_request()
    import json as _j

    body = _j.loads(req.content)
    assert body == {"chat_id": 555, "text": "hi"}


@pytest.mark.asyncio
async def test_get_me_returns_username(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://tg.test/botTOKEN/getMe",
        method="GET",
        json={
            "ok": True,
            "result": {"id": 42, "is_bot": True, "username": "kirills_warframe_bot"},
        },
    )
    c = TelegramClient(token="TOKEN", base_url="https://tg.test")
    me = await c.get_me()
    assert me["username"] == "kirills_warframe_bot"


class _CapturingClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


@pytest.mark.asyncio
async def test_handle_updates_registers_on_start(repo: Repo) -> None:
    fake = _CapturingClient()
    bot = TelegramBot(client=fake, repo=repo)
    updates = [
        {
            "update_id": 10,
            "message": {"text": "/start", "chat": {"id": 777, "username": "bob"}},
        }
    ]
    await bot.handle_updates(updates, now=123)
    chats = await repo.list_telegram_chats()
    assert len(chats) == 1 and chats[0]["chat_id"] == 777
    assert fake.sent and fake.sent[0][0] == 777  # welcome message sent
    assert bot._offset == 11  # offset advanced past update_id


@pytest.mark.asyncio
async def test_handle_updates_ignores_non_start(repo: Repo) -> None:
    fake = _CapturingClient()
    bot = TelegramBot(client=fake, repo=repo)
    await bot.handle_updates(
        [{"update_id": 1, "message": {"text": "hello", "chat": {"id": 1}}}],
        now=1,
    )
    assert await repo.list_telegram_chats() == []
    assert fake.sent == []
