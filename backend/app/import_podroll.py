"""One-shot importer: legacy ``podroll.db`` SQLite → Postgres ``weapon_price_samples``.

Legacy layout (``db.PodRollDB``): one table per weapon (normalized name), columns
``(timestamp INTEGER, price1 INTEGER, price2 INTEGER, price3 INTEGER)`` where
``timestamp`` is unix seconds. Table names already match ``weapon_url_name`` —
``_normalize_table_name`` only lowercases / underscores spaces & hyphens, and
``weapon_url_name`` values never contained either.

Idempotent: for each weapon, fetches the set of already-stored ``ts`` values
from Postgres and skips any SQLite row whose timestamp matches. Safe to re-run.

Run inside the backend container:
    docker compose cp ~/Downloads/podroll.db backend:/tmp/podroll.db
    docker compose exec backend uv run python -m app.import_podroll /tmp/podroll.db
"""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db import async_session
from app.models import WeaponPriceSample

BATCH = 1000


async def import_weapon(
    sqlite_conn: sqlite3.Connection,
    weapon: str,
) -> tuple[int, int]:
    """Returns (inserted, skipped) for one weapon."""
    rows = sqlite_conn.execute(
        f'SELECT timestamp, price1, price2, price3 FROM "{weapon}" ORDER BY timestamp'
    ).fetchall()
    if not rows:
        return 0, 0

    async with async_session() as session:
        # Pull the set of ts values already in Postgres for this weapon (as
        # epoch seconds) so we can dedupe in-process — cheaper than 30k
        # individual SELECTs.
        existing_dts = (
            await session.execute(
                select(WeaponPriceSample.ts).where(WeaponPriceSample.weapon == weapon)
            )
        ).scalars().all()
        existing_epochs = {int(dt.timestamp()) for dt in existing_dts}

        to_insert: list[dict] = []
        skipped = 0
        for ts_epoch, p1, p2, p3 in rows:
            if ts_epoch in existing_epochs:
                skipped += 1
                continue
            to_insert.append(
                {
                    "weapon": weapon,
                    "ts": datetime.fromtimestamp(ts_epoch, tz=timezone.utc),
                    "price1": int(p1),
                    "price2": int(p2),
                    "price3": int(p3),
                }
            )

        inserted = 0
        for i in range(0, len(to_insert), BATCH):
            chunk = to_insert[i : i + BATCH]
            await session.execute(pg_insert(WeaponPriceSample).values(chunk))
            inserted += len(chunk)
        await session.commit()
        return inserted, skipped


async def main(sqlite_path: Path) -> None:
    if not sqlite_path.exists():
        print(f"error: file not found: {sqlite_path}", file=sys.stderr)
        sys.exit(2)

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    try:
        tables = [
            r[0]
            for r in sqlite_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        print(f"source: {sqlite_path}")
        print(f"tables: {len(tables)} → {tables}")

        total_inserted = 0
        total_skipped = 0
        for weapon in tables:
            inserted, skipped = await import_weapon(sqlite_conn, weapon)
            total_inserted += inserted
            total_skipped += skipped
            print(f"  {weapon:>16}: +{inserted:>6} inserted, {skipped:>6} skipped")

        print(f"done: {total_inserted} inserted, {total_skipped} skipped")
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m app.import_podroll <path/to/podroll.db>", file=sys.stderr)
        sys.exit(2)
    asyncio.run(main(Path(sys.argv[1])))
