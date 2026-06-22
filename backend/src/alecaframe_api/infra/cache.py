"""Async Redis cache wrapper.

Thin convenience layer on top of `redis.asyncio.Redis` so callers don't
sprinkle JSON-serialisation boilerplate everywhere. Every key is prefixed
to isolate logical namespaces (e.g. `wfm` vs `signals`).

Designed for `dict[str, Any]` payloads — anything else, use the client directly.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol


class _RedisLike(Protocol):
    """Just the redis.asyncio.Redis methods we touch."""

    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> Any: ...
    async def delete(self, *keys: str) -> int: ...
    async def ttl(self, key: str) -> int: ...


@dataclass
class Cache:
    """Async JSON-aware Redis cache with mandatory key prefix."""

    client: _RedisLike
    key_prefix: str

    def _k(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    async def get_json(self, key: str) -> dict[str, Any] | None:
        raw = await self.client.get(self._k(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            await self.client.delete(self._k(key))
            return None

    async def set_json(
        self, key: str, value: dict[str, Any], *, ttl_seconds: int
    ) -> None:
        await self.client.set(
            self._k(key), json.dumps(value, ensure_ascii=False), ex=ttl_seconds
        )

    async def delete(self, key: str) -> None:
        await self.client.delete(self._k(key))

    async def ttl_seconds(self, key: str) -> int | None:
        v = await self.client.ttl(self._k(key))
        # redis returns -2 for missing, -1 for no expiry; both surface as None
        return v if v >= 0 else None

    async def get_or_set_json(
        self,
        key: str,
        *,
        ttl_seconds: int,
        loader: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        fresh = await loader()
        await self.set_json(key, fresh, ttl_seconds=ttl_seconds)
        return fresh
