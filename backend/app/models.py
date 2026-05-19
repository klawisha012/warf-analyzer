"""SQLAlchemy 2.0 ORM models — Postgres unified storage.

Tables (one-to-one mapping with the legacy stores):
    Auction            ← legacy SQLite ``rivens`` table
    WeaponPriceSample  ← legacy SQLite ``podroll.db`` per-weapon tables (unified)
    SavedGroll         ← legacy MongoDB ``groll_mods`` collection
    AppSetting         ← K/V store for ``good_weapons`` and ``fast_weapons_list``
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base for all ORM models."""


class Auction(Base):
    __tablename__ = "auctions"

    auction_id: Mapped[str] = mapped_column(String, primary_key=True)
    weapon: Mapped[str] = mapped_column(String, index=True)
    buyout_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    re_rolls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Comma-joined sorted list (matches legacy ``RivenDatabase.upsert_seen`` format)
    positive_stats: Mapped[str] = mapped_column(String)
    # Per-stat numeric values, e.g. {"critical_chance": 90.1, ...}
    stat_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    negative_stat: Mapped[str | None] = mapped_column(String, nullable=True)
    first_seen_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    disappeared: Mapped[bool] = mapped_column(Boolean, default=False)


class WeaponPriceSample(Base):
    __tablename__ = "weapon_price_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    weapon: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, server_default=func.now()
    )
    price1: Mapped[int] = mapped_column(Integer)
    price2: Mapped[int] = mapped_column(Integer)
    price3: Mapped[int] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_weapon_price_samples_weapon_ts", "weapon", "ts"),
    )


class SavedGroll(Base):
    __tablename__ = "saved_grolls"

    # auction_id == original Warframe Market "id" (matches legacy Mongo doc {"id": ...})
    auction_id: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppSetting(Base):
    """Single-row K/V store. Keys used: ``good_weapons``, ``fast_weapons_list``."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
