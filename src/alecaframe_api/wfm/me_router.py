"""Endpoints supporting frontend real-time wiring."""
from __future__ import annotations

from fastapi import APIRouter

from alecaframe_api.config import get_settings
from alecaframe_api.infra.push import CentrifugoPublisher

router = APIRouter()


@router.get(
    "/me/centrifugo-token",
    summary="Mint a short-lived JWT for the frontend Centrifugo client",
)
async def centrifugo_token() -> dict[str, str]:
    s = get_settings()
    # User id = the WFM username from agent meta (fallback: 'local').
    # We re-read it via the singleton bridge module.
    from alecaframe_api import main as _m
    meta = (_m.bridge.meta or {}).get("meta") or {} if hasattr(_m, "bridge") else {}
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
