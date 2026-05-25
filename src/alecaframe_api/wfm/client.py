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

        try:
            token = await self.token_provider()
            headers = {
                "Authorization": f"JWT {token}",
                "Platform": self.platform,
                "Language": self.language,
                "Accept": "application/json",
            }
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
        """Fetch the WFM v2 item catalogue and project into ItemRef.

        v2 listing shape: `{apiVersion, data: [{id, slug, gameRef, tags,
        i18n: {en: {name, icon, thumb}}}]}`. Fields `vaulted`, `ducats`,
        `reqMasteryRank` are only on the per-item `/v2/items/{slug}` endpoint,
        not the bulk listing.
        """
        payload = await self._request(
            "GET", "/items",
            cache_key="items",
            cache_ttl=_TTL_ITEMS,
        )
        items = payload.get("data") or []
        out: list[ItemRef] = []
        for it in items:
            en = (it.get("i18n") or {}).get(self.language) or (it.get("i18n") or {}).get("en") or {}
            out.append(
                ItemRef(
                    slug=it["slug"],
                    item_name=en.get("name") or it["slug"],
                    thumb_url=en.get("thumb"),
                    vaulted=None,  # not in v2 listing; resolve per-item if needed
                    wfm_id=it["id"],
                )
            )
        return out

    async def get_orders(
        self,
        slug: str,
        *,
        include_item_info: bool = False,  # legacy kwarg, no v2 equivalent
        fresh: bool = False,
    ) -> dict[str, Any]:
        """Fetch all live orders for a slug.

        v2 endpoint: `/v2/orders/item/{slug}` (was `/v1/items/{slug}/orders`).
        v2 response: `{apiVersion, data: [{id, type, platinum, quantity,
        perTrade, visible, createdAt, updatedAt, itemId, user: {id,
        ingameName, slug, avatar, reputation, platform, crossplay, locale,
        status, activity, lastSeen}}]}`.

        Returned shape is normalised to `{"data": [...]}` so callers can do
        `payload.get("data") or []` consistently.
        """
        # include_item_info kept for backwards-compat; v2 always includes itemId
        # but not the embedded item dict — we drop the kwarg silently.
        del include_item_info
        return await self._request(
            "GET",
            f"/orders/item/{slug}",
            cache_key=f"orders:{slug}",
            cache_ttl=_TTL_ORDERS,
            fresh=fresh,
        )

    async def get_profile(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        """NOT MIGRATED to v2 yet — /v2/profile/{user} returns 404.

        Callers should expect WFMError; routers that depend on this should
        raise 503 with a clear message until the v2 path is published.
        """
        raise WFMError(
            "WFM /profile not migrated to v2 yet; tracked as follow-up. "
            "Original v1 path is dead."
        )

    async def get_profile_orders(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        """NOT MIGRATED to v2 yet — see get_profile."""
        raise WFMError(
            "WFM /profile/{user}/orders not migrated to v2 yet; tracked as "
            "follow-up. Original v1 path is dead."
        )

    async def get_statistics(self, slug: str, *, fresh: bool = False) -> dict[str, Any]:
        """NOT MIGRATED to v2 yet — /v2/items/{slug}/statistics returns 404.

        The 90-day OHLCV statistics endpoint may have been removed or moved;
        no public v2 path was found. B.2a's history table replaces most of
        what this endpoint provided.
        """
        raise WFMError(
            "WFM /items/{slug}/statistics not available in v2; use the "
            "B.2a SQLite history table via /history/{slug} instead."
        )
