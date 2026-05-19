"""Async CRUD helpers — replace the legacy ``db.py`` sync classes.

All helpers take an ``AsyncSession`` and never open one themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, Auction, SavedGroll, WeaponPriceSample


# ---------------------------------------------------------------------------
# Auctions (mirrors RivenDatabase.upsert_seen)
# ---------------------------------------------------------------------------

async def upsert_auction(
    session: AsyncSession,
    auction: dict[str, Any],
    positive_stats: list[str],
) -> None:
    """Insert a freshly seen auction or bump ``last_seen_ts``/``buyout_price``."""
    item = auction["item"]
    now = datetime.now(timezone.utc)

    positives: dict[str, Any] = {}
    negative: str | None = None
    for attr in item.get("attributes", []):
        if attr.get("positive"):
            positives[attr["url_name"]] = attr["value"]
        else:
            negative = attr["url_name"]

    stmt = pg_insert(Auction).values(
        auction_id=auction["id"],
        weapon=item.get("weapon_url_name"),
        buyout_price=auction.get("buyout_price"),
        re_rolls=item.get("re_rolls"),
        positive_stats=",".join(sorted(positive_stats)),
        stat_values=positives,
        negative_stat=negative,
        first_seen_ts=now,
        last_seen_ts=now,
        disappeared=False,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["auction_id"],
        set_={
            "last_seen_ts": stmt.excluded.last_seen_ts,
            "buyout_price": stmt.excluded.buyout_price,
        },
    )
    await session.execute(stmt)
    await session.commit()


# ---------------------------------------------------------------------------
# Weapon price samples (mirrors PodRollDB.insert_prices / get_prices)
# ---------------------------------------------------------------------------

async def insert_price_sample(
    session: AsyncSession,
    weapon: str,
    p1: int,
    p2: int,
    p3: int,
    ts: datetime | None = None,
) -> None:
    sample = WeaponPriceSample(
        weapon=weapon,
        ts=ts or datetime.now(timezone.utc),
        price1=p1,
        price2=p2,
        price3=p3,
    )
    session.add(sample)
    await session.commit()


async def get_price_history(
    session: AsyncSession,
    weapon: str,
) -> list[tuple[int, int, int, int]]:
    """Return ``[(ts_epoch_seconds, p1, p2, p3), ...]`` ordered ascending."""
    stmt = (
        select(
            WeaponPriceSample.ts,
            WeaponPriceSample.price1,
            WeaponPriceSample.price2,
            WeaponPriceSample.price3,
        )
        .where(WeaponPriceSample.weapon == weapon)
        .order_by(WeaponPriceSample.ts.asc())
    )
    result = await session.execute(stmt)
    return [(int(ts.timestamp()), p1, p2, p3) for ts, p1, p2, p3 in result.all()]


async def get_latest_price_sample(
    session: AsyncSession,
    weapon: str,
) -> tuple[int, int, int, int] | None:
    """Most recent sample for one weapon. Returns ``(ts_epoch, p1, p2, p3)`` or None."""
    stmt = (
        select(
            WeaponPriceSample.ts,
            WeaponPriceSample.price1,
            WeaponPriceSample.price2,
            WeaponPriceSample.price3,
        )
        .where(WeaponPriceSample.weapon == weapon)
        .order_by(WeaponPriceSample.ts.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    ts, p1, p2, p3 = row
    return (int(ts.timestamp()), p1, p2, p3)


# ---------------------------------------------------------------------------
# AppSetting K/V (good_weapons, fast_weapons_list)
# ---------------------------------------------------------------------------

async def get_setting(session: AsyncSession, key: str) -> Any | None:
    stmt = select(AppSetting.value).where(AppSetting.key == key)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def set_setting(session: AsyncSession, key: str, value: Any) -> None:
    stmt = pg_insert(AppSetting).values(
        key=key,
        value=value,
        updated_at=datetime.now(timezone.utc),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={
            "value": stmt.excluded.value,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await session.execute(stmt)
    await session.commit()


# ---------------------------------------------------------------------------
# Saved grolls (mirrors MongoDBManager)
# ---------------------------------------------------------------------------

async def add_saved_groll(session: AsyncSession, auction: dict[str, Any]) -> bool:
    """Insert one saved groll. Returns False on duplicate, True on insert."""
    auction_id = auction.get("id") or auction.get("auction_id")
    if not auction_id:
        raise ValueError("auction must contain 'id' (warframe.market auction id)")

    stmt = pg_insert(SavedGroll).values(
        auction_id=auction_id,
        payload=auction,
        saved_at=datetime.now(timezone.utc),
    )
    # Mongo behavior: silent no-op on duplicate (the legacy code prints + returns False)
    stmt = stmt.on_conflict_do_nothing(index_elements=["auction_id"])
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0


async def list_saved_groll_ids(session: AsyncSession) -> list[str]:
    stmt = select(SavedGroll.auction_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def delete_saved_groll(session: AsyncSession, auction_id: str) -> bool:
    stmt = delete(SavedGroll).where(SavedGroll.auction_id == auction_id)
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0
