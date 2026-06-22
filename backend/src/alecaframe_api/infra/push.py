"""Centrifugo HTTP publisher + JWT minting for client connection tokens.

Centrifugo v6 server API:
- POST /api  with `{"method": "publish", "params": {"channel": "...", "data": {...}}}`
  authenticated by `X-API-Key` header.
- Clients connect with a JWT signed by `token_hmac_secret`, `sub` = user id,
  `exp` = expiry.

Publish failures are logged at WARNING and swallowed — the realtime pipeline
must never bring down the request path.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

log = logging.getLogger("alecaframe.infra.push")


@dataclass
class CentrifugoPublisher:
    api_url: str  # e.g. http://centrifugo:8000/api
    api_key: str
    token_hmac_secret: str
    timeout: float = 3.0

    def mint_user_token(self, user_id: str, *, ttl_seconds: int = 3600) -> str:
        now = int(time.time())
        payload = {"sub": str(user_id), "iat": now, "exp": now + ttl_seconds}
        return jwt.encode(payload, self.token_hmac_secret, algorithm="HS256")

    async def publish(self, channel: str, data: dict[str, Any]) -> None:
        body = {"method": "publish", "params": {"channel": channel, "data": data}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.post(
                    self.api_url,
                    json=body,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code >= 400:
                    log.warning(
                        "centrifugo publish %s status %d: %s",
                        channel,
                        resp.status_code,
                        resp.text[:200],
                    )
        except Exception as e:
            log.warning("centrifugo publish %s failed: %s", channel, e)

    async def list_channels(self, *, pattern: str = "") -> set[str]:
        """Return the set of active Centrifugo channels matching `pattern`.

        Used by PricePoller to discover which slugs the frontend is currently
        watching: an active `wfm.orders.{slug}` subscription means the slug
        is visible somewhere in the UI and should be kept fresh.

        Returns an empty set on any Centrifugo failure — the poller treats
        "no subscribers" the same as "nobody is watching", which is the safe
        fallback.
        """
        body = {"method": "channels", "params": {"pattern": pattern}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.post(
                    self.api_url,
                    json=body,
                    headers={
                        "X-API-Key": self.api_key,
                        "Content-Type": "application/json",
                    },
                )
                if resp.status_code >= 400:
                    log.warning(
                        "centrifugo channels status %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
                    return set()
                payload = resp.json()
        except Exception as e:
            log.warning("centrifugo channels failed: %s", e)
            return set()
        result = (payload.get("result") or {}).get("channels") or {}
        return set(result.keys())
