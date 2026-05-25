import { createEffect, onCleanup } from "solid-js";
import { useQueryClient } from "@tanstack/solid-query";
import { getCentrifuge } from "../api/centrifuge";

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
        const handler = () => {
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
        try { fn(); } catch { /* listener already gone */ }
      });
    });
  });
}
