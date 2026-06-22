"""Pure analysis helpers for riven auctions.

Everything in this module is a pure function (no I/O, no async) so the
poller and the request handlers can use the same logic and the tests stay
fast. Network access happens in `auctions_client.py`; persistence in
`db/repo.py`; orchestration in `auction_poller.py`.

Tier classification is data-driven: instead of a curated stat-to-tier
table per weapon (which would rot the moment WFM disposition changes), we
let the market tell us what's premium by splitting the live auction list
into price quartiles. The bottom 25% by buyout becomes "low" (cheap mods
people sell for kuva-rolling), the top 25% becomes "god" (premium stat
combos), and the middle 50% is "mid".

Outlier detection compares today's price to the rolling historical median
of the same tier. Anything below `threshold × median` is flagged — that's
a mod priced like a low-tier even though it's currently classified as mid
(or a god-tier mod priced like a mid-tier, etc.).
"""
from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class TierStats:
    """Distribution stats for one tier in one snapshot."""
    count: int
    min_price: int | None
    p25: int | None
    median: int | None
    p75: int | None
    max_price: int | None


@dataclass(frozen=True)
class Outlier:
    """An auction priced significantly below the historical median of its tier."""
    auction_id: str
    tier: str
    price: int
    historical_median: int
    discount_pct: int   # 100 * (1 - price/historical_median), rounded


# NOTE: keyed by the WFM attribute slug as it actually arrives on auctions
# (verified live: v1 /auctions/search returns v2-style slugs —
# base_damage_/_melee_damage, heat_damage, damage_vs_grineer,
# fire_rate_/_attack_speed, ...). The old bare spellings (damage, heat,
# damage_to_grineer) never matched real data, so the quality override was a
# no-op and everything fell back to raw price quartiles.

# Highly valued premium positive stats (rifles, pistols, shotguns, melee).
GOD_POSITIVES = {
    "multishot", "critical_damage", "critical_chance", "status_chance",
    "base_damage_/_melee_damage", "fire_rate_/_attack_speed",
    # Elements (viral/corrosive/heat combos)
    "toxin_damage", "cold_damage", "heat_damage", "electric_damage",
    # Faction damage — large multipliers, premium
    "damage_vs_grineer", "damage_vs_corpus", "damage_vs_infested",
    # Melee meta
    "range", "critical_chance_on_slide_attack", "slash_damage",
}

# Fatal negative curses that gut the build → demote to low regardless of price.
# A negative on a core damage/crit/status stat. Faction damage is left OUT
# (a −damage_vs_<one faction> is situational, not build-fatal).
FATAL_NEGATIVES = {
    "multishot", "critical_damage", "critical_chance", "status_chance",
    "base_damage_/_melee_damage", "fire_rate_/_attack_speed",
    "toxin_damage", "cold_damage", "heat_damage", "electric_damage",
    "range", "slash_damage",
}

# "Value-raising" negatives: a curse on a stat the build doesn't use. The curse
# itself boosts the two positives (~+24%) while costing nothing useful — this is
# exactly what makes a god roll. Dropping one of these is free.
HARMLESS_NEGATIVES = {
    "zoom", "ammo_maximum", "magazine_capacity", "recoil", "reload_speed",
    "projectile_speed", "punch_through", "status_duration",
    "impact_damage", "puncture_damage",
    # Melee utilities
    "finisher_damage", "combo_duration", "channeling_efficiency",
}


def _buyout(a: dict) -> int | None:
    v = a.get("buyout_price")
    return int(v) if isinstance(v, (int, float)) else None


def eval_riven_quality(a: dict) -> str | None:
    """Evaluate Riven attributes to detect 'god', 'mid', or 'low' characteristics.

    Returns:
      - 'low': fatal negative on a core stat, or zero premium positive stats.
      - 'god': 2+ premium positives AND a value-raising ("harmless") negative.
        The curse is REQUIRED — in-game it boosts the two positives (~+24%) while
        costing nothing the build uses, which is precisely what makes a god roll.
        A 2-positive roll with NO negative is strong but only mid (it leaves the
        free damage of a curse on the table).
      - None: standard mid-tier material → falls back to its price quartile.
    """
    item = a.get("item") or {}
    attributes = item.get("attributes") or []
    if not attributes:
        return None

    positives = []
    negatives = []
    for at in attributes:
        name = (at.get("url_name") or at.get("name") or "").lower().strip().replace(" ", "_").replace("-", "_")
        if bool(at.get("positive")):
            positives.append(name)
        else:
            negatives.append(name)

    # Fatal negative on a core stat → trash regardless of listing price.
    if any(neg in FATAL_NEGATIVES for neg in negatives):
        return "low"

    premium_pos_count = sum(1 for pos in positives if pos in GOD_POSITIVES)

    # No premium positive at all (only utility rolls like zoom/ammo) → low.
    if premium_pos_count == 0:
        return "low"

    # God tier: 2+ premium positives AND a value-raising negative present.
    has_value_raising_negative = any(neg in HARMLESS_NEGATIVES for neg in negatives)
    if premium_pos_count >= 2 and has_value_raising_negative:
        return "god"

    # Everything else (incl. strong 2-positive rolls with no curse) → price tier.
    return None


def classify_tiers(auctions: list[dict]) -> dict[str, list[dict]]:
    """Split auctions into god/mid/low buckets using a smart hybrid model.

    We combine:
    1. Market Price (buyout quartile splits).
    2. Stat Evaluation (demoting mods with fatal curses/negatives, promoting
       mods with ideal positive rolls + harmless negatives).

    This prevents troll/scam listings (e.g. a trash mod with -damage listed for 10000p)
    from skewing the 'god' tier stats, and accurately flags actual high-value items.
    """
    priced = [a for a in auctions if _buyout(a) is not None]
    priced.sort(key=lambda a: _buyout(a) or 0)
    n = len(priced)
    if n == 0:
        return {"god": [], "mid": [], "low": []}

    # 1. Base classification using price quartiles
    # This acts as our default fallback
    base_tiers: dict[str, list[dict]] = {"god": [], "mid": [], "low": []}
    if n < 4:
        base_tiers["low"] = priced[:1]
        base_tiers["mid"] = priced[1:-1]
        base_tiers["god"] = priced[-1:] if n > 1 else []
    else:
        q1 = n // 4
        q3 = (3 * n) // 4
        base_tiers["low"] = priced[:q1]
        base_tiers["mid"] = priced[q1:q3]
        base_tiers["god"] = priced[q3:]

    # 2. Refine based on Riven attribute quality (Smart Overrides)
    final_tiers: dict[str, list[dict]] = {"god": [], "mid": [], "low": []}

    for a in priced:
        quality = eval_riven_quality(a)
        if quality == "low":
            # Demote immediately to low tier regardless of listing price
            final_tiers["low"].append(a)
        elif quality == "god":
            # Promote to god tier if it has genuine god-roll stats
            final_tiers["god"].append(a)
        else:
            # Fallback to its price-based classification
            if a in base_tiers["low"]:
                final_tiers["low"].append(a)
            elif a in base_tiers["god"]:
                final_tiers["god"].append(a)
            else:
                final_tiers["mid"].append(a)

    return final_tiers


def compute_tier_stats(auctions: list[dict]) -> TierStats:
    prices = sorted(_buyout(a) for a in auctions if _buyout(a) is not None)
    if not prices:
        return TierStats(count=0, min_price=None, p25=None, median=None, p75=None, max_price=None)
    return TierStats(
        count=len(prices),
        min_price=prices[0],
        p25=_quantile(prices, 0.25),
        median=int(statistics.median(prices)),
        p75=_quantile(prices, 0.75),
        max_price=prices[-1],
    )


def _quantile(sorted_prices: list[int], q: float) -> int | None:
    if not sorted_prices:
        return None
    if len(sorted_prices) == 1:
        return sorted_prices[0]
    cuts = statistics.quantiles(sorted_prices, n=100, method="inclusive")
    idx = int(round(q * 100)) - 1
    idx = max(0, min(idx, len(cuts) - 1))
    return int(round(cuts[idx]))


def detect_outliers(
    auctions: list[dict], *, historical_median: int | None,
    threshold: float, tier: str,
) -> list[Outlier]:
    """Auctions in this tier whose price is below threshold × median.

    `threshold=0.8` means anything ≥20% cheaper than the historical median is
    flagged. `historical_median` is the value the poller computed from the
    last 7-30 days of `riven_snapshot` for the same weapon and tier — if no
    history yet, we return [] (we don't flag against the current snapshot,
    that would always self-flag the cheapest auction every poll).
    """
    if historical_median is None or historical_median <= 0:
        return []
    cutoff = threshold * historical_median
    out: list[Outlier] = []
    for a in auctions:
        price = _buyout(a)
        if price is None or price >= cutoff:
            continue
        out.append(Outlier(
            auction_id=str(a.get("id") or ""),
            tier=tier, price=price,
            historical_median=historical_median,
            discount_pct=int(round(100 * (1 - price / historical_median))),
        ))
    return out


def summarize_attributes(
    auctions: list[dict], *, top_n: int = 5,
) -> list[dict]:
    """Most common positive attribute names across `auctions` (typically the
    god-tier slice). Output: `[{name: 'critical_damage', count: 3, share: 1.0}]`
    sorted by count desc. Tells the user "the expensive mods on this weapon
    almost all have CD" without any per-weapon configuration.
    """
    counter: Counter[str] = Counter()
    total = 0
    for a in auctions:
        total += 1
        attrs = ((a.get("item") or {}).get("attributes") or [])
        seen: set[str] = set()
        for at in attrs:
            if not at.get("positive"):
                continue
            name = at.get("url_name") or at.get("name")
            if name and name not in seen:
                counter[name] += 1
                seen.add(name)
    if total == 0:
        return []
    rows = [
        {"name": name, "count": cnt, "share": round(cnt / total, 2)}
        for name, cnt in counter.most_common(top_n)
    ]
    return rows


def suggest_strategies(
    *, outliers: list[Outlier], god_tier_count: int,
    mid_tier_count: int, low_tier_count: int,
) -> list[dict]:
    """Translate the current market shape into actionable tips.

    Each tip is `{kind: short-id, ru: text, en: text, severity: info|warn|good}`.
    Frontend picks language. Kind is used as a stable key — UI may filter or
    icon them, and tests assert on it.
    """
    tips: list[dict] = []

    # Buy-and-flip when there's any current outlier
    if outliers:
        best = max(outliers, key=lambda o: o.discount_pct)
        tips.append({
            "kind": "buy_flip",
            "severity": "good",
            "ru": f"Возможность: лот за {best.price}p (на {best.discount_pct}% ниже median {best.historical_median}p в tier '{best.tier}'). Купи и перевыставь ближе к median.",
            "en": f"Opportunity: auction at {best.price}p ({best.discount_pct}% under tier '{best.tier}' median of {best.historical_median}p). Buy and relist near median.",
        })

    # Kuva-roll when the low-tier dominates the listing
    total = god_tier_count + mid_tier_count + low_tier_count
    if total > 0 and low_tier_count / total >= 0.4:
        tips.append({
            "kind": "kuva_roll",
            "severity": "info",
            "ru": "Много дешёвых лотов в low-tier → подходящее время купить под kuva-ролл (кува бесплатна, шанс попасть в god-tier стат).",
            "en": "Lots of low-tier listings right now → good moment to buy cheap and roll on kuva (free farm, chance to land god-tier stats).",
        })

    # Disposition / patience reminder when god-tier is very expensive
    if god_tier_count >= 3:
        tips.append({
            "kind": "watch_disposition",
            "severity": "warn",
            "ru": "Перед покупкой dorogого riven проверь disposition оружия — после nerf'а цены резко падают.",
            "en": "Before buying a high-tier riven check the weapon disposition — nerfs crash prices fast.",
        })

    # Always include one base educational tip so the panel never empties out.
    tips.append({
        "kind": "base_education",
        "severity": "info",
        "ru": "Stat-комбинации не равны: ищи аукционы с CD+MS+Dam для оружия с high disposition. Топ-стат у этого оружия показан выше.",
        "en": "Stat combos aren't equal: look for CD+MS+Dam on high-disposition weapons. Top stats for this weapon are shown above.",
    })

    return tips
