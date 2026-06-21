"""Endpoints supporting frontend real-time wiring."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from alecaframe_api.bridge import AlecaBridge
from alecaframe_api.config import get_settings
from alecaframe_api.infra.push import CentrifugoPublisher


router = APIRouter()


def _get_bridge() -> AlecaBridge:
    # Lazy import at request time — same pattern wfm/router.py uses to break
    # the cycle with main.py.
    from alecaframe_api.main import bridge
    return bridge


BridgeDep = Annotated[AlecaBridge, Depends(_get_bridge)]


@router.get(
    "/me/centrifugo-token",
    summary="Mint a short-lived JWT for the frontend Centrifugo client",
)
async def centrifugo_token(br: BridgeDep) -> dict[str, str]:
    s = get_settings()
    meta = (br.meta or {}).get("meta") or {}
    user = meta.get("wfm_username") or "local"
    pub = CentrifugoPublisher(
        api_url=s.centrifugo_api,
        api_key=s.centrifugo_api_key,
        token_hmac_secret=s.centrifugo_token_hmac_secret,
    )
    return {
        "token": pub.mint_user_token(user, ttl_seconds=s.centrifugo_token_ttl_seconds),
        "user": user,
    }
