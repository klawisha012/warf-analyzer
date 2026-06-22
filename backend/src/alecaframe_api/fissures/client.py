"""HTTP client for warframestat.us /fissures with a small in-process TTL cache
shared by the poller and the HTTP route (so a page load doesn't re-hit the
upstream more than once per `cache_ttl`)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from alecaframe_api.fissures.models import PLATFORM_MAP, Fissure, parse_fissure

log = logging.getLogger("alecaframe.fissures.client")
_UA = "alecaframe-api fissure-poller"


class FissureClientError(RuntimeError):
    pass


@dataclass
class FissureClient:
    base_url: str = "https://api.warframestat.us"
    platform: str = "pc"
    timeout: float = 10.0
    cache_ttl: float = 30.0
    _cache: tuple[float, list[Fissure]] | None = field(
        default=None, init=False, repr=False
    )

    def _url(self) -> str:
        seg = PLATFORM_MAP.get(self.platform, "pc")
        return f"{self.base_url.rstrip('/')}/{seg}/fissures"

    async def get_fissures(
        self, *, now: float | None = None, fresh: bool = False
    ) -> list[Fissure]:
        t = now if now is not None else time.time()
        if (
            not fresh
            and self._cache is not None
            and (t - self._cache[0]) < self.cache_ttl
        ):
            return self._cache[1]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.get(
                    self._url(),
                    headers={"User-Agent": _UA, "Accept": "application/json"},
                )
        except httpx.HTTPError as e:
            raise FissureClientError(f"fissures fetch failed: {e}") from e
        if resp.status_code >= 400:
            raise FissureClientError(f"fissures fetch status {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise FissureClientError(f"fissures bad json: {e}") from e
        if not isinstance(data, list):
            raise FissureClientError("fissures payload is not a list")
        out: list[Fissure] = []
        for raw in data:
            if isinstance(raw, dict):
                f = parse_fissure(raw)
                if f is not None:
                    out.append(f)
        self._cache = (t, out)
        return out
