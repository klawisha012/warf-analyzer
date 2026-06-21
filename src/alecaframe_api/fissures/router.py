"""HTTP surface for Void Fissure subscriptions + Telegram registration."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from alecaframe_api.fissures.client import FissureClientError
from alecaframe_api.fissures.dependencies import FissureClientDep
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.schemas import (
    FissureMetaResponse, FissureRow, FissuresResponse,
    FissureSubscriptionCreate, FissureSubscriptionRow, FissureSubscriptionsResponse,
    TelegramChatRow, TelegramChatsResponse,
)
from alecaframe_api.wfm.dependencies import RepoDep

log = logging.getLogger("alecaframe.fissures.router")

router = APIRouter(prefix="/fissures", tags=["fissures"])

ERAS = ["Lith", "Meso", "Neo", "Axi", "Requiem", "Omnia"]
KNOWN_MISSION_TYPES = [
    "Alchemy", "Assault", "Capture", "Defection", "Defense", "Disruption",
    "Excavation", "Extermination", "Hijack", "Interception", "Mobile Defense",
    "Orphix", "Rescue", "Sabotage", "Skirmish", "Spy", "Survival",
    "Void Cascade", "Void Flood", "Volatile",
]


def _eta_seconds(expiry: str | None, now: float) -> int | None:
    if not expiry:
        return None
    try:
        dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int(dt.timestamp() - now))


def _to_row(f: Fissure, now: float) -> FissureRow:
    return FissureRow(
        id=f.id, era=f.era, mission_type=f.mission_type, node=f.node,
        planet=f.planet, enemy=f.enemy, is_hard=f.is_hard, is_storm=f.is_storm,
        expiry=f.expiry, eta_seconds=_eta_seconds(f.expiry, now),
    )


def _norm_sub(r: dict) -> dict:
    def _b(v) -> bool | None:
        return None if v is None else bool(v)
    return {
        "id": r["id"], "era": r["era"], "mission_type": r["mission_type"],
        "is_hard": _b(r["is_hard"]), "is_storm": _b(r["is_storm"]),
        "enabled": bool(r["enabled"]), "created_at": r["created_at"],
    }


@router.get("", response_model=FissuresResponse, summary="Current active Void Fissures")
async def list_fissures(client: FissureClientDep) -> FissuresResponse:
    try:
        fissures = await client.get_fissures()
    except FissureClientError as e:
        raise HTTPException(503, str(e)) from e
    now = time.time()
    rows = [_to_row(f, now) for f in fissures]
    rows.sort(key=lambda r: (r.is_storm, r.is_hard, r.era, r.mission_type))
    return FissuresResponse(total=len(rows), items=rows)


@router.get("/meta", response_model=FissureMetaResponse,
            summary="All possible fissure axes (eras + mission types)")
async def fissures_meta(client: FissureClientDep) -> FissureMetaResponse:
    live: set[str] = set()
    try:
        for f in await client.get_fissures():
            live.add(f.mission_type)
    except FissureClientError:
        pass
    return FissureMetaResponse(
        eras=ERAS, mission_types=sorted(set(KNOWN_MISSION_TYPES) | live),
    )


@router.get("/subscriptions", response_model=FissureSubscriptionsResponse)
async def list_subscriptions(repo: RepoDep) -> FissureSubscriptionsResponse:
    rows = await repo.list_fissure_subscriptions()
    items = [FissureSubscriptionRow(**_norm_sub(r)) for r in rows]
    return FissureSubscriptionsResponse(total=len(items), items=items)


@router.post("/subscriptions", response_model=FissureSubscriptionsResponse,
             status_code=status.HTTP_201_CREATED)
async def add_subscription(req: FissureSubscriptionCreate, repo: RepoDep) -> FissureSubscriptionsResponse:
    await repo.add_fissure_subscription(
        era=req.era or None, mission_type=req.mission_type or None,
        is_hard=req.is_hard, is_storm=req.is_storm, ts=int(time.time()),
    )
    rows = await repo.list_fissure_subscriptions()
    items = [FissureSubscriptionRow(**_norm_sub(r)) for r in rows]
    return FissureSubscriptionsResponse(total=len(items), items=items)


@router.delete("/subscriptions/{sub_id}")
async def remove_subscription(sub_id: int, repo: RepoDep) -> dict:
    if not await repo.remove_fissure_subscription(sub_id):
        raise HTTPException(404, f"subscription {sub_id} not found")
    return {"removed": sub_id}


@router.get("/telegram/chats", response_model=TelegramChatsResponse)
async def telegram_chats(repo: RepoDep) -> TelegramChatsResponse:
    from alecaframe_api.config import get_settings  # noqa: PLC0415
    rows = await repo.list_telegram_chats()
    items = [TelegramChatRow(**r) for r in rows]
    return TelegramChatsResponse(
        bot_enabled=bool(get_settings().tg_api_key), total=len(items), items=items,
    )


@router.post("/telegram/test")
async def telegram_test(repo: RepoDep) -> dict:
    from alecaframe_api.main import telegram_client  # noqa: PLC0415
    if telegram_client is None:
        raise HTTPException(503, "telegram disabled (TG_API_KEY not set)")
    chats = await repo.list_telegram_chats()
    sent = 0
    for chat in chats:
        if await telegram_client.send_message(int(chat["chat_id"]), "🔔 Тест: уведомления о разрывах работают."):
            sent += 1
    return {"sent": sent, "chats": len(chats)}
