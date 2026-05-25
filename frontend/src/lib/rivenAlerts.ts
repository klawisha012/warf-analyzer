/** Global outlier-alert feed for rivens.
 *
 *  Filled by the Centrifugo subscription in useRivenAlerts; read by the
 *  Rivens page (badges on watchlist entries, banner on the open weapon).
 *
 *  Each alert is keyed by `${weapon_slug}:${auction_id}` so duplicate pushes
 *  for the same outlier just refresh the timestamp instead of stacking.
 */
import { createSignal } from "solid-js";

export type RivenAlert = {
  weapon_slug: string;
  auction_id: string;
  tier: string;
  price: number;
  historical_median: number;
  discount_pct: number;
  ts: number;
};

const [alertsMap, setAlertsMap] = createSignal<Record<string, RivenAlert>>({});

function key(a: { weapon_slug: string; auction_id: string }): string {
  return `${a.weapon_slug}:${a.auction_id}`;
}

export function pushAlert(a: RivenAlert): void {
  setAlertsMap((prev) => ({ ...prev, [key(a)]: a }));
}

export function alertsForWeapon(slug: string): RivenAlert[] {
  return Object.values(alertsMap())
    .filter((a) => a.weapon_slug === slug)
    .sort((a, b) => b.discount_pct - a.discount_pct);
}

export function alertCountByWeapon(): Record<string, number> {
  const out: Record<string, number> = {};
  for (const a of Object.values(alertsMap())) {
    out[a.weapon_slug] = (out[a.weapon_slug] ?? 0) + 1;
  }
  return out;
}

export function clearAlertsFor(slug: string): void {
  setAlertsMap((prev) => {
    const next: Record<string, RivenAlert> = {};
    for (const k of Object.keys(prev)) {
      const v = prev[k];
      if (v && v.weapon_slug !== slug) next[k] = v;
    }
    return next;
  });
}
