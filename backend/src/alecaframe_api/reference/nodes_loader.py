"""Star-chart node catalogue (planet -> mission nodes) from WFCD worldstate data.

WFCD publishes solNodes.json: {SolNodeN: {value: "<Node> (<Planet>)", enemy, type}}.
We group node display names by planet so the UI can offer a planet-scoped node
picker — letting a user subscribe to a node before any fissure is live there.
Data: https://github.com/WFCD/warframe-worldstate-data (MIT)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger("alecaframe.reference.nodes_loader")

_WFCD_SOLNODES_URL = (
    "https://raw.githubusercontent.com/WFCD/warframe-worldstate-data/master/data/solNodes.json"
)


def _planet_of(value: str) -> str | None:
    """`"Kappa (Sedna)"` -> `"Sedna"`. None if no parenthesised tail."""
    lo = value.rfind("(")
    hi = value.rfind(")")
    if lo != -1 and hi != -1 and hi > lo:
        return value[lo + 1 : hi].strip() or None
    return None


def build_nodes_by_planet(sol_nodes: dict[str, Any]) -> dict[str, list[str]]:
    """Group node display names by planet. Pure (no network). Entries without a
    parenthesised planet (unmapped SolNodeN placeholders) are skipped; each
    planet's list is sorted and deduped."""
    grouped: dict[str, set[str]] = {}
    for entry in sol_nodes.values():
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if not isinstance(value, str):
            continue
        planet = _planet_of(value)
        if not planet:
            continue
        grouped.setdefault(planet, set()).add(value)
    return {planet: sorted(nodes) for planet, nodes in sorted(grouped.items())}


@dataclass
class NodeCatalog:
    """Fetches the WFCD solNodes catalogue once and caches it in-process. On a
    fetch error it returns the last good value (or {}), so callers degrade to
    live nodes rather than failing."""
    url: str = _WFCD_SOLNODES_URL
    timeout: float = 15.0
    cache_ttl: float = 24 * 3600.0
    _cache: tuple[float, dict[str, list[str]]] | None = field(default=None, init=False, repr=False)

    async def get(self, *, now: float | None = None) -> dict[str, list[str]]:
        t = now if now is not None else time.time()
        if self._cache is not None and (t - self._cache[0]) < self.cache_ttl:
            return self._cache[1]
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as c:
                resp = await c.get(self.url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001 — any failure degrades gracefully
            log.warning("solNodes fetch failed: %s", e)
            return self._cache[1] if self._cache is not None else {}
        result = build_nodes_by_planet(data if isinstance(data, dict) else {})
        self._cache = (t, result)
        return result
