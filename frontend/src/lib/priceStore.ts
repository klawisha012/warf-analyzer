/** Global slug → PriceStats store.
 *
 *  Single source of truth for WFM order-book stats across every page. Filled
 *  lazily by Inventory/Sets/PrimeParts when they fetch /me/* (which embeds
 *  prices from the backend PriceStore), then kept fresh by Centrifugo push
 *  events on `wfm.orders.{slug}`.
 *
 *  Designed for Solid's fine-grained reactivity:
 *  - `priceFor(slug)` is a derived accessor — components read it inside JSX
 *    and Solid re-renders only the cells that change.
 *  - We use a SINGLE signal holding the whole map (not a signal per slug):
 *    Solid's createSignal compares by reference, and we replace the map
 *    instance on each update, so any component reading any slug re-evaluates.
 *    This is fine at the scale we operate on (a few hundred slugs at most).
 */
import { createSignal } from "solid-js";
import type { PriceStats } from "../api/types";

const [pricesMap, setPricesMap] = createSignal<Record<string, PriceStats>>({});

export function priceFor(slug: string | null | undefined): PriceStats | undefined {
  if (!slug) return undefined;
  return pricesMap()[slug];
}

export function setPrice(stats: PriceStats): void {
  setPricesMap((prev) => ({ ...prev, [stats.slug]: stats }));
}

export function setPrices(stats: PriceStats[] | Record<string, PriceStats>): void {
  setPricesMap((prev) => {
    const next = { ...prev };
    if (Array.isArray(stats)) {
      for (const s of stats) next[s.slug] = s;
    } else {
      for (const slug of Object.keys(stats)) {
        const v = stats[slug];
        if (v) next[slug] = v;
      }
    }
    return next;
  });
}

/** Test/debug only — wipe the entire store. */
export function clearPrices(): void {
  setPricesMap({});
}
