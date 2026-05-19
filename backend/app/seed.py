"""One-shot seeder: import the legacy ``settings.json`` into ``AppSetting``.

Usage::

    cd backend && uv run python -m app.seed

Idempotent — re-running just upserts the same values back. Reads the file
from the repo root by default; pass ``--file <path>`` to override.

Anti-pattern note: this is the ONLY place that reads ``settings.json`` at
runtime. The worker / routes always go through ``AppSetting`` via
``settings_store``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from app import settings_store
from app.db import async_session

logger = logging.getLogger(__name__)


def _default_settings_path() -> Path:
    # backend/app/seed.py → repo root is two parents up.
    return Path(__file__).resolve().parents[2] / "settings.json"


async def seed(path: Path) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    good_weapons = data.get("good_weapons") or {}
    fast_weapons_list = data.get("fast_weapons_list") or []

    if not isinstance(good_weapons, dict):
        raise ValueError("settings.json: 'good_weapons' must be an object")
    if not isinstance(fast_weapons_list, list):
        raise ValueError("settings.json: 'fast_weapons_list' must be an array")

    # Coerce so we get an early failure if shape is bad.
    good_weapons = {str(k): int(v) for k, v in good_weapons.items()}
    fast_weapons_list = [str(w) for w in fast_weapons_list]

    async with async_session() as session:
        await settings_store.set_good_weapons(session, good_weapons)
        await settings_store.set_fast_weapons_list(session, fast_weapons_list)

    logger.info(
        "seeded AppSetting: %d good_weapons, %d fast_weapons_list",
        len(good_weapons),
        len(fast_weapons_list),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Seed AppSetting from legacy settings.json")
    parser.add_argument(
        "--file",
        type=Path,
        default=_default_settings_path(),
        help="Path to legacy settings.json (default: repo-root settings.json)",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.file))


if __name__ == "__main__":
    main()
