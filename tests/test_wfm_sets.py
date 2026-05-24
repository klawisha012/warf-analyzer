"""Tests for set composition + profit calculator."""
from __future__ import annotations

import pytest

from alecaframe_api.wfm.sets import SetIndex, SetComposition, compute_set_profits, SetProfitRow


@pytest.fixture
def index() -> SetIndex:
    idx = SetIndex()
    idx.register(SetComposition(
        set_slug="kronen_prime_set",
        set_name="Kronen Prime Set",
        parts={
            "kronen_prime_blade": 2,
            "kronen_prime_handle": 1,
            "kronen_prime_blueprint": 1,
        },
    ))
    idx.register(SetComposition(
        set_slug="mag_prime_set",
        set_name="Mag Prime Set",
        parts={
            "mag_prime_neuroptics_blueprint": 1,
            "mag_prime_chassis_blueprint": 1,
            "mag_prime_systems_blueprint": 1,
            "mag_prime_blueprint": 1,
        },
    ))
    return idx


def test_register_and_lookup(index: SetIndex) -> None:
    s = index.get("kronen_prime_set")
    assert s is not None and s.set_name == "Kronen Prime Set"
    assert sum(s.parts.values()) == 4  # 2 blades + 1 handle + 1 blueprint


def test_compute_set_profits_buyable_and_owned(index: SetIndex) -> None:
    """User owns 1 of each Kronen part except blades; needs to buy 2 blades.

    Sell price for the whole set = 100p (provided externally).
    Floor prices: blade=35, handle=20, bp=24.
    Tax: 0.1p per part = 0.4p ~ 1p rounded.
    Cost to complete = 2*35 = 70. Sell = 100. Profit = 100 - 70 - 1 = 29.
    """
    inventory_counts = {
        "kronen_prime_handle": 1,
        "kronen_prime_blueprint": 1,
        "kronen_prime_blade": 0,
    }
    floor_prices = {
        "kronen_prime_blade": 35,
        "kronen_prime_handle": 20,
        "kronen_prime_blueprint": 24,
    }
    set_floor_prices = {"kronen_prime_set": 100, "mag_prime_set": None}

    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_floor_prices,
    )

    kronen = next(r for r in rows if r.set_slug == "kronen_prime_set")
    assert kronen.set_price == 100
    assert kronen.parts_cost == 70    # buy 2 blades @35 each
    assert kronen.tax_estimate == 1   # rounded from 0.4
    assert kronen.profit == 100 - 70 - 1
    assert kronen.missing_parts == {"kronen_prime_blade": 2}


def test_compute_set_profits_skipped_when_no_set_price(index: SetIndex) -> None:
    """If set price is unknown (set_prices[slug] is None), skip the row."""
    inventory_counts = {}
    floor_prices = {"mag_prime_blueprint": 30}
    set_prices = {"mag_prime_set": None}
    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_prices,
    )
    assert all(r.set_slug != "mag_prime_set" for r in rows)


def test_compute_set_profits_skipped_when_a_part_has_no_floor(index: SetIndex) -> None:
    """If any required part has no floor price, we can't compute — skip."""
    inventory_counts = {}
    floor_prices = {"kronen_prime_blade": 35, "kronen_prime_handle": 20}  # missing bp
    set_prices = {"kronen_prime_set": 100}
    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_prices,
    )
    assert all(r.set_slug != "kronen_prime_set" for r in rows)


def test_compute_set_profits_filters_by_min_margin(index: SetIndex) -> None:
    """Pass min_margin=50 — Kronen yields only 29 so it should be filtered out."""
    inventory_counts = {}
    floor_prices = {
        "kronen_prime_blade": 35, "kronen_prime_handle": 20, "kronen_prime_blueprint": 24,
    }
    set_prices = {"kronen_prime_set": 100}
    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_prices, min_margin=50,
    )
    assert rows == []


def test_compute_set_profits_sorted_by_profit_desc(index: SetIndex) -> None:
    """Two sets with different profits — higher profit first."""
    idx = SetIndex()
    idx.register(SetComposition("a_set", "A Set", {"a_part": 1}))
    idx.register(SetComposition("b_set", "B Set", {"b_part": 1}))
    rows = compute_set_profits(
        index=idx, inventory={},
        part_floor_prices={"a_part": 10, "b_part": 30},
        set_prices={"a_set": 50, "b_set": 80},
    )
    # a_set: 50-10-1 = 39, b_set: 80-30-1 = 49 → b_set first
    assert rows[0].set_slug == "b_set"
    assert rows[1].set_slug == "a_set"
