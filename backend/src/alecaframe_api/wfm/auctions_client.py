"""WFM v1 auctions client — riven auction queries.

Lives separately from `WFMClient` (which is v2-only) because the auctions
endpoints were never migrated to v2: `/v2/auctions/*` returns 404 as of
2026-05. The v1 paths still respond and accept the same JWT bearer token
we already mint via decrypt-agent.

Reuses the same Redis L1 cache + stale-on-error pattern as WFMClient. The
two clients are intentionally NOT siblings of a shared base class — the
parallel structure is shallow enough that a base class would do more harm
than good (different response shapes, different TTLs, different paths).
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx
from aiolimiter import AsyncLimiter

from alecaframe_api.infra.cache import Cache

log = logging.getLogger("alecaframe.wfm.auctions_client")

_TTL_RIVEN_ITEMS = 24 * 3600     # catalogue of riven-capable weapons rarely changes
_TTL_AUCTIONS_SEARCH = 60        # auction list churn — refresh fast
_TTL_AUCTION_ENTRY = 120         # per-auction detail


TokenProvider = Callable[[], Awaitable[str]]


class WFMAuctionError(RuntimeError):
    """Raised when a non-cached auctions call fails irrecoverably."""


@dataclass
class WFMAuctionClient:
    cache: Cache
    base_url: str
    token_provider: TokenProvider
    platform: str = "pc"
    language: str = "en"
    rate_limit_per_second: int = 5
    request_timeout: float = 15.0

    _limiter: AsyncLimiter = field(init=False, repr=False)
    _http: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _cached_token: str | None = field(default=None, init=False, repr=False)
    _token_expires_at: float = field(default=0.0, init=False, repr=False)
    _token_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self._limiter = AsyncLimiter(max_rate=self.rate_limit_per_second, time_period=1.0)

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=self.request_timeout)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _get_token(self) -> str:
        now = _time.time()
        if self._cached_token and self._token_expires_at - now > 30:
            return self._cached_token
        async with self._token_lock:
            now = _time.time()
            if self._cached_token and self._token_expires_at - now > 30:
                return self._cached_token
            token = await self.token_provider()
            self._cached_token = token
            # We don't parse the JWT exp here — auctions client lives next
            # to WFMClient which already does that on the same token, so by
            # the time we get one we know it's fresh enough; just refresh
            # every 5 minutes to be safe.
            self._token_expires_at = now + 300
            return token

    async def _request(
        self, method: str, path: str, *,
        cache_key: str, cache_ttl: int, fresh: bool = False,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not fresh:
            cached = await self.cache.get_json(cache_key)
            if cached is not None:
                return cached

        try:
            token = await self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
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
            log.warning("wfm-auctions %s %s failed: %s; trying stale fallback", method, path, e)
            stale = await self.cache.get_json(cache_key)
            if stale is not None:
                return {**stale, "_stale": True}
            raise WFMAuctionError(f"{method} {path} failed and no stale cache: {e}") from e

        await self.cache.set_json(cache_key, payload, ttl_seconds=cache_ttl)
        return payload

    # ------------------------------------------------------------- typed methods

    async def get_riven_auctions(
        self, weapon_slug: str, *, fresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Return current public riven auctions for `weapon_slug`, sorted by price asc.

        v1 path: `/v1/auctions/search?type=riven&weapon_url_name={slug}&sort_by=price_asc`
        Response: `{"payload": {"auctions": [<auction>, ...]}}`. Each auction
        carries `{id, buyout_price, starting_price, top_bid, item: {...attributes},
        owner, visible, private, is_direct_sell, created, updated}`.

        Stale-fallback flag: if `_stale=True` appears in the wrapper, the
        auctions list is the last good snapshot.
        """
        payload = await self._request(
            "GET", "/auctions/search",
            cache_key=f"auctions:search:{weapon_slug}",
            cache_ttl=_TTL_AUCTIONS_SEARCH,
            fresh=fresh,
            params={"type": "riven", "weapon_url_name": weapon_slug, "sort_by": "price_asc"},
        )
        return list((payload.get("payload") or {}).get("auctions") or [])

    async def get_auction_entry(
        self, auction_id: str, *, fresh: bool = False,
    ) -> dict[str, Any]:
        """Full detail for a single auction.

        v1 path: `/v1/auctions/entry/{id}`. Returns `{"payload": {"auction": {...}}}`.
        """
        payload = await self._request(
            "GET", f"/auctions/entry/{auction_id}",
            cache_key=f"auctions:entry:{auction_id}",
            cache_ttl=_TTL_AUCTION_ENTRY,
            fresh=fresh,
        )
        return dict((payload.get("payload") or {}).get("auction") or {})

    def _v2_url(self, path: str) -> str:
        """Absolute v2 URL from the v1 base (the riven catalogue migrated to v2;
        auctions are still v1). httpx uses an absolute URL as-is over base_url."""
        base = self.base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3] + "/v2"
        return f"{base}{path}"

    @staticmethod
    def _map_v2_weapon(it: dict[str, Any]) -> dict[str, Any]:
        """Map a v2 `/riven/weapons` item to the v1 `/riven/items` shape the rest
        of the code consumes (url_name/item_name/icon/riven_disposition/...)."""
        en = (it.get("i18n") or {}).get("en") or {}
        return {
            "url_name": it.get("slug"),
            "item_name": en.get("name") or it.get("slug"),
            "icon": en.get("icon"),
            "thumb": en.get("thumb"),
            "riven_disposition": it.get("disposition"),
            "riven_type": it.get("rivenType"),
            "group": it.get("group"),
            "mastery_level": it.get("reqMasteryRank"),
        }

    async def get_riven_weapons(self, *, fresh: bool = False) -> list[dict[str, Any]]:
        """Catalogue of weapons that can carry a riven (with disposition).

        The catalogue migrated to v2: `/v1/riven/items` now 404s/errors, the data
        lives at `/v2/riven/weapons` with a new shape (`{data: [{slug, rivenType,
        disposition, i18n:{en:{name,icon}}}]}`). Mapped back to the v1 keys so
        callers are unaffected. Cached 24h — disposition changes once or twice a year.
        """
        payload = await self._request(
            "GET", self._v2_url("/riven/weapons"),
            cache_key="riven_weapons_v2",
            cache_ttl=_TTL_RIVEN_ITEMS,
            fresh=fresh,
        )
        return [self._map_v2_weapon(it) for it in (payload.get("data") or [])]
