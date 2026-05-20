"""warframe.market HTTP wrapper around a long-lived ``httpx.AsyncClient``.

The client itself is created in the FastAPI lifespan and stored on
``app.state.http`` (per Phase 2 plan + httpx docs: don't open a client per
request). This module wraps that client with the application-level rate
limiter and the URL builders ported from ``scanner2.py``.

Cooldowns mirror the legacy worker:
    * ``get_groll``       — 7s
    * ``get_base_api``    — 2s
    * ``get_by_weapon``   — 7s
    * ``get_similar``     — 7s
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.rate_limiter import AsyncRateLimiter

# Default cooldowns (seconds) per endpoint group. Mirror scanner2.py.
GROLL_COOLDOWN = 7.0
BASE_API_COOLDOWN = 2.0
WEAPON_COOLDOWN = 7.0
SIMILAR_COOLDOWN = 7.0

# Backoff applied after an HTTP error (scanner2 used 15s here).
ERROR_BACKOFF = 15.0

HEADERS = {"accept": "application/json", "platform": "pc"}


def build_similar_url(attributes: list[dict[str, Any]], weapon: str) -> str:
    """Port of ``scanner2.build_URL``.

    Builds the search URL for "auctions with the same positive stats + same
    negative as this riven" — used for the price-history sampling path.
    """
    base = f"{settings.WARFRAME_API_BASE}/auctions/search?type=riven&positive_stats="
    pos_count = len(attributes)
    has_neg = False
    if attributes and attributes[-1].get("positive", True) is False:
        pos_count -= 1
        has_neg = True

    pos_names = [attributes[i].get("url_name", "") for i in range(pos_count)]
    url = base + ",".join(pos_names)
    if has_neg:
        url += "&negative_stats=" + attributes[-1].get("url_name", "")
    url += "&sort_by=price_asc&weapon_url_name=" + weapon
    return url


class MarketClient:
    """Stateful wrapper: one ``httpx.AsyncClient`` + one ``AsyncRateLimiter``."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._limiter = AsyncRateLimiter(cooldown=BASE_API_COOLDOWN)

    @property
    def limiter(self) -> AsyncRateLimiter:
        return self._limiter

    async def _request(self, url: str, cooldown: float) -> httpx.Response:
        self._limiter.set_interval(cooldown)
        await self._limiter.wait()
        try:
            response = await self._client.get(url, headers=HEADERS)
        finally:
            self._limiter.stamp()
        return response

    # ------------------------------------------------------------------
    # Endpoint methods. Each returns the parsed JSON payload (dict).
    # The caller handles error status codes.
    # ------------------------------------------------------------------

    async def get_groll(self) -> httpx.Response:
        """Wide-net GROLL search: 3 god rolls with zoom-negative."""
        url = (
            f"{settings.WARFRAME_API_BASE}/auctions/search"
            "?type=riven"
            "&positive_stats=multishot,critical_chance,critical_damage"
            "&negative_stats=zoom"
            "&sort_by=price_asc"
        )
        return await self._request(url, GROLL_COOLDOWN)

    async def get_base_api(self) -> httpx.Response:
        """The base ``/auctions`` polling endpoint."""
        url = f"{settings.WARFRAME_API_BASE}/auctions"
        return await self._request(url, BASE_API_COOLDOWN)

    async def get_by_weapon(self, weapon_url_name: str) -> httpx.Response:
        """`/auctions/search?type=riven&sort_by=price_asc&weapon_url_name=...`."""
        url = (
            f"{settings.WARFRAME_API_BASE}/auctions/search"
            f"?type=riven&sort_by=price_asc&weapon_url_name={weapon_url_name}"
        )
        return await self._request(url, WEAPON_COOLDOWN)

    async def get_similar(
        self,
        attributes: list[dict[str, Any]],
        weapon_url_name: str,
    ) -> httpx.Response:
        """Search for auctions with the same stats as ``attributes`` for the weapon."""
        url = build_similar_url(attributes, weapon_url_name)
        return await self._request(url, SIMILAR_COOLDOWN)

    async def backoff(self) -> None:
        """Apply the post-error backoff (matches scanner2's set_interval(15)+wait)."""
        self._limiter.set_interval(ERROR_BACKOFF)
        await self._limiter.wait()
        # restore to the more aggressive default so subsequent calls can pick
        # a per-endpoint interval.
        self._limiter.set_interval(BASE_API_COOLDOWN)
