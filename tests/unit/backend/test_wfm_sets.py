"""Tests for set composition + profit calculator."""

from __future__ import annotations

import pytest

from alecaframe_api.wfm.sets import (
    SetComposition,
    SetIndex,
    compute_set_profits,
)


@pytest.fixture
def index() -> SetIndex:
    """Test catalogue with REAL WFM v2 `quantityInSet` values per part.

    Kronen Prime Set: 2 blades + 2 handles + 1 blueprint (5 parts total).
    Source: api.warframe.market/v2/items/{slug}.quantityInSet.
    """
    idx = SetIndex()
    idx.register(
        SetComposition(
            set_slug="kronen_prime_set",
            set_name="Kronen Prime Set",
            parts={
                "kronen_prime_blade": 2,
                "kronen_prime_handle": 2,
                "kronen_prime_blueprint": 1,
            },
        )
    )
    idx.register(
        SetComposition(
            set_slug="mag_prime_set",
            set_name="Mag Prime Set",
            parts={
                "mag_prime_neuroptics_blueprint": 1,
                "mag_prime_chassis_blueprint": 1,
                "mag_prime_systems_blueprint": 1,
                "mag_prime_blueprint": 1,
            },
        )
    )
    return idx


def test_register_and_lookup(index: SetIndex) -> None:
    s = index.get("kronen_prime_set")
    assert s is not None and s.set_name == "Kronen Prime Set"
    assert sum(s.parts.values()) == 5  # 2 blades + 2 handles + 1 blueprint


def test_compute_set_profits_buyable_and_owned(index: SetIndex) -> None:
    """User owns 1 handle + 1 blueprint; needs 2 blades + 1 more handle.

    Sell price for the whole set = 100p (provided externally).
    Floor prices: blade=35, handle=20, bp=24.
    Tax is no longer deducted (it was always a flat 1p and distorted readings
    at small parts counts more than it informed them).
    Cost = 2*35 + 1*20 = 90. Sell = 100. Profit = 100 - 90 = 10.
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
        index=index,
        inventory=inventory_counts,
        part_floor_prices=floor_prices,
        set_prices=set_floor_prices,
    )

    kronen = next(r for r in rows if r.set_slug == "kronen_prime_set")
    assert kronen.set_price == 100
    assert kronen.parts_cost == 90  # 2 blades @35 + 1 handle @20
    assert kronen.tax_estimate == 0
    assert kronen.profit == 100 - 90
    assert kronen.missing_parts == {"kronen_prime_blade": 2, "kronen_prime_handle": 1}


def test_compute_set_profits_missing_when_user_has_zero_of_multi_qty_part(
    index: SetIndex,
) -> None:
    """Regression for #handle-quantity bug: when a multi-qty part isn't owned at
    all, `missing_parts` must equal `required_qty`, not `required_qty - 1`.
    """
    inventory_counts: dict[str, int] = {}  # user owns nothing
    floor_prices = {
        "kronen_prime_blade": 35,
        "kronen_prime_handle": 20,
        "kronen_prime_blueprint": 24,
    }
    set_prices = {"kronen_prime_set": 200}  # high enough not to be filtered

    rows = compute_set_profits(
        index=index,
        inventory=inventory_counts,
        part_floor_prices=floor_prices,
        set_prices=set_prices,
    )

    kronen = next(r for r in rows if r.set_slug == "kronen_prime_set")
    # Critical: handle must show 2 missing (not 1) since required=2, owned=0.
    assert kronen.missing_parts == {
        "kronen_prime_blade": 2,
        "kronen_prime_handle": 2,
        "kronen_prime_blueprint": 1,
    }


def test_compute_set_profits_skipped_when_no_set_price(index: SetIndex) -> None:
    """If set price is unknown (set_prices[slug] is None), skip the row."""
    inventory_counts = {}
    floor_prices = {"mag_prime_blueprint": 30}
    set_prices = {"mag_prime_set": None}
    rows = compute_set_profits(
        index=index,
        inventory=inventory_counts,
        part_floor_prices=floor_prices,
        set_prices=set_prices,
    )
    assert all(r.set_slug != "mag_prime_set" for r in rows)


def test_compute_set_profits_skipped_when_a_part_has_no_floor(index: SetIndex) -> None:
    """If any required part has no floor price, we can't compute — skip."""
    inventory_counts = {}
    floor_prices = {"kronen_prime_blade": 35, "kronen_prime_handle": 20}  # missing bp
    set_prices = {"kronen_prime_set": 100}
    rows = compute_set_profits(
        index=index,
        inventory=inventory_counts,
        part_floor_prices=floor_prices,
        set_prices=set_prices,
    )
    assert all(r.set_slug != "kronen_prime_set" for r in rows)


def test_compute_set_profits_filters_by_min_margin(index: SetIndex) -> None:
    """Pass min_margin=50 — Kronen yields only 29 so it should be filtered out."""
    inventory_counts = {}
    floor_prices = {
        "kronen_prime_blade": 35,
        "kronen_prime_handle": 20,
        "kronen_prime_blueprint": 24,
    }
    set_prices = {"kronen_prime_set": 100}
    rows = compute_set_profits(
        index=index,
        inventory=inventory_counts,
        part_floor_prices=floor_prices,
        set_prices=set_prices,
        min_margin=50,
    )
    assert rows == []


def test_compute_set_profits_sorted_by_profit_desc(index: SetIndex) -> None:
    """Two sets with different profits — higher profit first."""
    idx = SetIndex()
    idx.register(SetComposition("a_set", "A Set", {"a_part": 1}))
    idx.register(SetComposition("b_set", "B Set", {"b_part": 1}))
    rows = compute_set_profits(
        index=idx,
        inventory={},
        part_floor_prices={"a_part": 10, "b_part": 30},
        set_prices={"a_set": 50, "b_set": 80},
    )
    # a_set: 50-10-1 = 39, b_set: 80-30-1 = 49 → b_set first
    assert rows[0].set_slug == "b_set"
    assert rows[1].set_slug == "a_set"
