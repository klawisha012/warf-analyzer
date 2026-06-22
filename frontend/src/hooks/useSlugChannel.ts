import { createEffect, onCleanup } from "solid-js";
import { useQueryClient } from "@tanstack/solid-query";
import { getCentrifuge } from "../api/centrifuge";
import { setPrice } from "../lib/priceStore";
import type { PriceStats } from "../api/types";

/** Subscribe to wfm.orders.{slug} for each slug currently visible.
 *
 *  Centrifuge throws if you call `newSubscription(channel)` twice for the
 *  same channel — which happens when:
 *    a) two hook instances mount with overlapping slug lists (e.g. Dashboard
 *       + Inventory share kronen_prime_blade);
 *    b) the same hook re-runs its effect with a new slug list that overlaps
 *       the previous one (createEffect can fire before onCleanup tears down).
 *
 *  Strategy: always check `getSubscription(channel)` first and reuse if
 *  present. Attach a publication listener per hook-call; on cleanup detach
 *  only OUR listener — leave the subscription alive for any sibling hook.
 *  When no listeners remain we let centrifuge keep the sub idle — the cost
 *  is negligible and reclaim is automatic on full disconnect.
 *
 *  Publication payload (from PricePoller) carries the PriceStats fields
 *  directly; we update the global price store and Solid re-renders any
 *  component reading the slug. This is why we don't need to invalidate
 *  React Query: every component that displays a price reads from the store,
 *  not from query data.
 */
export function useSlugChannel(slugs: () => string[]): void {
  const qc = useQueryClient();
  createEffect(() => {
    const current = slugs();
    if (current.length === 0) return;
    let cancelled = false;
    const teardown: Array<() => void> = [];

    (async () => {
      const cf = await getCentrifuge();
      for (const slug of current) {
        if (cancelled) break;
        const channel = `wfm.orders.${slug}`;
        let sub = cf.getSubscription(channel);
        if (!sub) {
          sub = cf.newSubscription(channel);
          sub.subscribe();
        }
        const handler = (ctx: { data?: unknown }) => {
          const stats = parsePriceStats(slug, ctx?.data);
          if (stats) setPrice(stats);
          // Also invalidate any React Query that mentions this slug — covers
          // /me/sets-profit and other endpoints whose payload is computed
          // from this slug's floor price.
          qc.invalidateQueries({
            predicate: (q) => q.queryKey.some((p) => p === slug),
          });
        };
        sub.on("publication", handler);
        teardown.push(() => sub!.removeListener("publication", handler));
      }
    })().catch((err) => {
      // Swallow + log: a subscription failure shouldn't crash the page.
      console.warn("useSlugChannel: subscribe failed", err);
    });

    onCleanup(() => {
      cancelled = true;
      teardown.forEach((fn) => {
        try {
          fn();
        } catch {
          /* listener already gone */
        }
      });
    });
  });
}

function parsePriceStats(slug: string, data: unknown): PriceStats | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  // PricePoller payload shape; older consumer-emitted payloads only carry
  // `{slug}` — ignore those (the poller will produce a full stats payload
  // within one tick because the slug now has an active subscriber).
  if (!("sell_min" in d) && !("sell_median" in d) && !("buy_max" in d)) return null;
  return {
    slug: typeof d.slug === "string" ? d.slug : slug,
    sell_min: numOrNull(d.sell_min),
    sell_median: numOrNull(d.sell_median),
    sell_spread: numOrNull(d.sell_spread),
    buy_max: numOrNull(d.buy_max),
    fetched_at: typeof d.fetched_at === "number" ? d.fetched_at : Date.now() / 1000,
    stale: Boolean(d.stale),
  };
}

function numOrNull(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}
