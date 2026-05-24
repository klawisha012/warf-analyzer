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
from alecaframe_api.wfm.slugs import ItemRef

log = logging.getLogger("alecaframe.wfm.client")

# Per-resource TTLs (seconds). Adjust if WFM rate limits or product needs change.
_TTL_ITEMS = 24 * 3600       # 24h — catalogue is stable
_TTL_ORDERS = 60             # 60s — order book churn
_TTL_PROFILE = 300           # 5min
_TTL_STATISTICS = 300        # 5min


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

    # ----------------------------------------------------------- typed methods

    async def get_items(self) -> list[ItemRef]:
        payload = await self._request(
            "GET", "/items",
            cache_key="items",
            cache_ttl=_TTL_ITEMS,
        )
        items = payload.get("payload", {}).get("items", [])
        return [
            ItemRef(
                slug=it["url_name"],
                item_name=it["item_name"],
                thumb_url=it.get("thumb"),
                vaulted=bool(it.get("vaulted", False)),
                wfm_id=it["id"],
            )
            for it in items
        ]

    async def get_orders(
        self,
        slug: str,
        *,
        include_item_info: bool = False,
        fresh: bool = False,
    ) -> dict[str, Any]:
        params = {"include": "item"} if include_item_info else None
        return await self._request(
            "GET",
            f"/items/{slug}/orders",
            cache_key=f"orders:{slug}:{int(include_item_info)}",
            cache_ttl=_TTL_ORDERS,
            fresh=fresh,
            params=params,
        )

    async def get_profile(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/profile/{username}",
            cache_key=f"profile:{username}",
            cache_ttl=_TTL_PROFILE,
            fresh=fresh,
        )

    async def get_profile_orders(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/profile/{username}/orders",
            cache_key=f"profile-orders:{username}",
            cache_ttl=_TTL_ORDERS,
            fresh=fresh,
        )

    async def get_statistics(self, slug: str, *, fresh: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/items/{slug}/statistics",
            cache_key=f"statistics:{slug}",
            cache_ttl=_TTL_STATISTICS,
            fresh=fresh,
        )
