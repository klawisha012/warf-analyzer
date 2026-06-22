import { createEffect, onCleanup } from "solid-js";
import { getCentrifuge } from "../api/centrifuge";
import { pushAlert } from "../lib/rivenAlerts";

/** Subscribe to `rivens.{weapon_slug}` for each watched weapon.
 *
 *  Mirrors the structure of useSlugChannel — reuses one subscription per
 *  channel across hook calls. The publication payload is the outlier dict
 *  the backend AuctionPoller emits.
 */
export function useRivenAlerts(weapons: () => string[]): void {
  createEffect(() => {
    const current = weapons();
    if (current.length === 0) return;
    let cancelled = false;
    const teardown: Array<() => void> = [];

    (async () => {
      const cf = await getCentrifuge();
      for (const slug of current) {
        if (cancelled) break;
        const channel = `rivens.${slug}`;
        let sub = cf.getSubscription(channel);
        if (!sub) {
          sub = cf.newSubscription(channel);
          sub.subscribe();
        }
        const handler = (ctx: { data?: unknown }) => {
          const d = ctx?.data as Record<string, unknown> | undefined;
          if (!d || d.kind !== "outlier") return;
          pushAlert({
            weapon_slug: String(d.weapon_slug ?? slug),
            auction_id: String(d.auction_id ?? ""),
            tier: String(d.tier ?? "mid"),
            price: Number(d.price ?? 0),
            historical_median: Number(d.historical_median ?? 0),
            discount_pct: Number(d.discount_pct ?? 0),
            ts: Number(d.ts ?? Date.now() / 1000),
          });
        };
        sub.on("publication", handler);
        teardown.push(() => sub!.removeListener("publication", handler));
      }
    })().catch((err) => {
      console.warn("useRivenAlerts: subscribe failed", err);
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
