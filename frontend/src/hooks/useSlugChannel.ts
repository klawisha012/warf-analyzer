import { createEffect, onCleanup } from "solid-js";
import { useQueryClient } from "@tanstack/solid-query";
import { getCentrifuge } from "../api/centrifuge";

/** Subscribe to wfm.orders.{slug} for each slug currently visible.
 *  On every event, invalidate the relevant query so TanStack refetches. */
export function useSlugChannel(slugs: () => string[]): void {
  const qc = useQueryClient();
  createEffect(() => {
    const current = slugs();
    if (current.length === 0) return;
    let mounted = true;
    const subs: { unsubscribe(): void }[] = [];
    (async () => {
      const cf = await getCentrifuge();
      for (const slug of current) {
        if (!mounted) break;
        const sub = cf.newSubscription(`wfm.orders.${slug}`);
        sub.on("publication", () => {
          qc.invalidateQueries({
            predicate: (q) => q.queryKey.some((p) => p === slug),
          });
        });
        sub.subscribe();
        subs.push(sub);
      }
    })();
    onCleanup(() => {
      mounted = false;
      subs.forEach((s) => s.unsubscribe());
    });
  });
}
