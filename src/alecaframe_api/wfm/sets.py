"""Set composition + profit calculator.

A `SetComposition` describes how many of each part go into a set. The profit
helper walks every registered set, computes the buy-side cost of completing
it (only what the user doesn't already own), and subtracts a flat WFM tax
estimate (~0.1p per part traded, rounded up).

Set compositions for B.1a come from a hardcoded list. B.2 will read them from
the AlecaFrame `cachedData/json/` files at startup.
"""
from __future__ import annotations

from dataclasses import dataclass


# WFM trade tax: 1% of plat traded + ducats. As a first approximation we
# model it as 0.1p per part times the number of parts in the set, rounded up.
def _tax_estimate(parts_count: int) -> int:
    raw = 0.1 * parts_count
    # Always at least 1p — WFM takes a minimum cut and we don't want to
    # over-promise profit by 0.4p.
    return max(1, int(round(raw)))


@dataclass(frozen=True)
class SetComposition:
    set_slug: str
    set_name: str
    parts: dict[str, int]   # part_slug -> required quantity


@dataclass(frozen=True)
class SetProfitRow:
    set_slug: str
    set_name: str
    set_price: int
    parts_cost: int
    tax_estimate: int
    profit: int
    missing_parts: dict[str, int]   # what you'd need to buy to complete
    owned_parts: dict[str, int]     # what you already have (subset of parts)


class SetIndex:
    """In-memory registry of set compositions, keyed by set_slug."""

    def __init__(self) -> None:
        self._sets: dict[str, SetComposition] = {}

    def register(self, comp: SetComposition) -> None:
        self._sets[comp.set_slug] = comp

    def get(self, set_slug: str) -> SetComposition | None:
        return self._sets.get(set_slug)

    def all_sets(self) -> list[SetComposition]:
        return list(self._sets.values())


def compute_set_profits(
    *,
    index: SetIndex,
    inventory: dict[str, int],           # part_slug -> qty owned
    part_floor_prices: dict[str, int | None],
    set_prices: dict[str, int | None],   # set_slug -> WFM floor for full set
    min_margin: int = 0,
) -> list[SetProfitRow]:
    """Return profit rows for every registered set, sorted by profit desc."""
    rows: list[SetProfitRow] = []
    for comp in index.all_sets():
        set_price = set_prices.get(comp.set_slug)
        if set_price is None:
            continue   # can't compute without set floor
        # Verify every required part has a floor price.
        if any(part_floor_prices.get(p) is None for p in comp.parts):
            continue

        missing: dict[str, int] = {}
        owned: dict[str, int] = {}
        cost = 0
        for part_slug, required_qty in comp.parts.items():
            owned_qty = int(inventory.get(part_slug, 0))
            if owned_qty:
                owned[part_slug] = min(owned_qty, required_qty)
            need = max(0, required_qty - owned_qty)
            if need:
                missing[part_slug] = need
                floor = part_floor_prices[part_slug]
                assert floor is not None  # checked above
                cost += need * floor

        total_parts = sum(comp.parts.values())
        tax = _tax_estimate(total_parts)
        profit = set_price - cost - tax
        if profit < min_margin:
            continue

        rows.append(SetProfitRow(
            set_slug=comp.set_slug, set_name=comp.set_name,
            set_price=set_price, parts_cost=cost, tax_estimate=tax,
            profit=profit, missing_parts=missing, owned_parts=owned,
        ))

    rows.sort(key=lambda r: (-r.profit, r.set_slug))
    return rows
