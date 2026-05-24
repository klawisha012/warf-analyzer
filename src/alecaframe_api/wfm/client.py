"""WFM REST client — the single point of contact with api.warframe.market.

Owns:
- Auth header (JWT from decrypt-agent's /wfm-token)
- Rate limiting (aiolimiter, default 3 req/s)
- L1 cache (Redis, TTL per resource)
- Stale-while-error fallback

All public methods land in `wfm/client.py` part 2 (next task). This task adds
the `_request` plumbing and types only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx
from aiolimiter import AsyncLimiter

from alecaframe_api.infra.cache import Cache

log = logging.getLogger("alecaframe.wfm.client")


TokenProvider = Callable[[], Awaitable[str]]


class WFMError(RuntimeError):
    """Raised when a non-cached call to WFM fails irrecoverably."""


@dataclass
class WFMClient:
    """Rate-limited, cached async HTTP client for warframe.market."""

    cache: Cache
    base_url: str
    token_provider: TokenProvider
    platform: str = "pc"
    language: str = "en"
    rate_limit_per_second: int = 3
    request_timeout: float = 15.0

    _limiter: AsyncLimiter = field(init=False, repr=False)
    _http: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._limiter = AsyncLimiter(max_rate=self.rate_limit_per_second, time_period=1.0)

    @property
    def _cache(self) -> Cache:
        """Alias kept so tests can poke at the cache (`client._cache.delete(...)`)."""
        return self.cache

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.request_timeout,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ----------------------------------------------------------- request

    async def _request(
        self,
        method: str,
        path: str,
        *,
        cache_key: str,
        cache_ttl: int,
        fresh: bool = False,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cached, rate-limited, stale-on-error HTTP request returning parsed JSON."""
        if not fresh:
            cached = await self.cache.get_json(cache_key)
            if cached is not None:
                return cached

        token = await self.token_provider()
        headers = {
            "Authorization": f"JWT {token}",
            "Platform": self.platform,
            "Language": self.language,
            "Accept": "application/json",
        }

        try:
            async with self._limiter:
                client = await self._client()
                resp = await client.request(method, path, headers=headers, params=params)
                resp.raise_for_status()
                payload: dict[str, Any] = resp.json()
        except Exception as e:
            log.warning("wfm %s %s failed: %s; trying stale fallback", method, path, e)
            stale = await self.cache.get_json(cache_key)
            if stale is not None:
                stale = {**stale, "_stale": True}
                return stale
            raise WFMError(f"{method} {path} failed and no stale cache available: {e}") from e

        await self.cache.set_json(cache_key, payload, ttl_seconds=cache_ttl)
        return payload
