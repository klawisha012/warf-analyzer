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

import asyncio
import base64
import json
import logging
import time as _time
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
    # JWT cache so concurrent callers don't all hammer decrypt-agent's
    # /wfm-token endpoint. Refreshed when within 30s of expiry; lock dedupes
    # parallel misses.
    _cached_token: str | None = field(default=None, init=False, repr=False)
    _token_expires_at: float = field(default=0.0, init=False, repr=False)
    _token_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

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

    # ----------------------------------------------------------- auth

    async def _get_token(self) -> str:
        """Cached JWT accessor. Refreshes 30s before expiry; concurrent-safe."""
        now = _time.time()
        if self._cached_token and self._token_expires_at - now > 30:
            return self._cached_token
        async with self._token_lock:
            # Re-check under lock: a concurrent caller may have just refreshed.
            now = _time.time()
            if self._cached_token and self._token_expires_at - now > 30:
                return self._cached_token
            token = await self.token_provider()
            self._cached_token = token
            self._token_expires_at = _extract_jwt_exp(token, default_ttl=300)
            return token

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
            token = await self._get_token()
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
        """Fetch the authenticated user's profile.

        v2 dropped the public `/profile/{username}` route — `/v2/me` is the
        replacement and requires the JWT we already send. Response shape:
        `{apiVersion, data: {...}, error}`. The `username` argument is kept
        for API compatibility but ignored — the endpoint always returns the
        token's owner.
        """
        del username  # unused — v2 doesn't accept a username
        return await self._request(
            "GET",
            "/me",
            cache_key="me:profile",
            cache_ttl=_TTL_PROFILE,
            fresh=fresh,
        )

    async def get_profile_orders(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        """Fetch the authenticated user's listed orders (was profile/{user}/orders).

        v2 endpoint: `/v2/me/orders`. Response shape:
        `{apiVersion, data: [<order>...], error}` where each order has
        `{id, type, platinum, quantity, perTrade, visible, itemId, ...}` —
        same per-order shape as `/v2/orders/item/{slug}` minus the `user`
        block (it's me).
        """
        del username  # unused — v2 doesn't accept a username
        return await self._request(
            "GET",
            "/me/orders",
            cache_key="me:orders",
            cache_ttl=_TTL_ORDERS,
            fresh=fresh,
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


# --------------------------------------------------------------- jwt helpers


def _extract_jwt_exp(token: str, *, default_ttl: int) -> float:
    """Read the `exp` claim from a JWT without verifying its signature.

    decrypt-agent is the local trusted minter, so signature verification adds
    no value here — we only need the expiry to decide when to refresh.
    Returns a Unix timestamp; falls back to now + default_ttl on any parse
    failure so a malformed token still gets cached briefly instead of being
    re-fetched on every call.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return _time.time() + default_ttl
        # JWT uses URL-safe base64 without padding; restore it.
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if isinstance(exp, (int, float)) and exp > 0:
            return float(exp)
    except Exception as e:
        log.warning("can't parse JWT exp (%s); using default TTL", e)
    return _time.time() + default_ttl
