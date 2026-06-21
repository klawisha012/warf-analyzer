"""Telegram Bot API: outbound sendMessage + inbound long-poll getUpdates.

Webhook is intentionally NOT used — the app runs locally without a public
HTTPS endpoint, so long-poll is the only viable inbound channel."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from alecaframe_api.db.repo import Repo

log = logging.getLogger("alecaframe.fissures.telegram")

WELCOME_TEXT = "✅ Подписка активна. Сюда будут приходить уведомления о разрывах Бездны."


class TelegramError(RuntimeError):
    pass


@dataclass
class TelegramClient:
    token: str
    base_url: str = "https://api.telegram.org"
    timeout: float = 30.0

    def _url(self, method: str) -> str:
        return f"{self.base_url.rstrip('/')}/bot{self.token}/{method}"

    async def send_message(self, chat_id: int, text: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.post(self._url("sendMessage"), json={"chat_id": chat_id, "text": text})
        except httpx.HTTPError as e:
            log.warning("telegram sendMessage failed: %s", e)
            return False
        if resp.status_code >= 400:
            log.warning("telegram sendMessage status %d: %s", resp.status_code, resp.text[:200])
            return False
        return True

    async def get_updates(self, *, offset: int | None = None, timeout: int = 25) -> list[dict]:
        params: dict = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        # client timeout must outlast the server-side long-poll window.
        async with httpx.AsyncClient(timeout=timeout + 10) as c:
            resp = await c.get(self._url("getUpdates"), params=params)
        if resp.status_code >= 400:
            raise TelegramError(f"getUpdates status {resp.status_code}")
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(f"getUpdates not ok: {str(data)[:200]}")
        return data.get("result") or []

    async def get_me(self) -> dict:
        """Bot's own info (getMe) — used to surface its public @username so the
        UI can link to https://t.me/<username>."""
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            resp = await c.get(self._url("getMe"))
        if resp.status_code >= 400:
            raise TelegramError(f"getMe status {resp.status_code}")
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(f"getMe not ok: {str(data)[:200]}")
        return data.get("result") or {}


@dataclass
class TelegramBot:
    client: TelegramClient
    repo: Repo
    poll_timeout: int = 25
    _offset: int | None = field(default=None, init=False)

    async def handle_updates(self, updates: list[dict], *, now: int) -> None:
        for u in updates:
            uid = u.get("update_id")
            if isinstance(uid, int):
                self._offset = max(self._offset or 0, uid + 1)
            msg = u.get("message") or u.get("edited_message") or {}
            text = (msg.get("text") or "").strip()
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None or not text:
                continue
            # first token, stripped of any @botname suffix
            if text.split()[0].split("@")[0] == "/start":
                username = chat.get("username") or chat.get("first_name")
                await self.repo.register_telegram_chat(chat_id=int(chat_id), username=username, ts=now)
                await self.client.send_message(int(chat_id), WELCOME_TEXT)

    async def run(self) -> None:
        log.info("telegram bot starting (long-poll)")
        while True:
            try:
                updates = await self.client.get_updates(offset=self._offset, timeout=self.poll_timeout)
                await self.handle_updates(updates, now=int(time.time()))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("telegram poll failed: %s", e)
                await asyncio.sleep(5)
