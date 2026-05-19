/**
 * Weapon-specific synergy bands: per-stat [min, max] percentages.
 * Copied verbatim from backend/app/alert_rules.py — the source of truth.
 * Used by AlertCard to compute per-stat percentages for the StatBar fills.
 */
export const SYNERGIES: Record<string, Record<string, [number, number]>> = {
  torid: {
    multishot: [98.7, 120.7],
    critical_damage: [131.6, 160.7],
    critical_chance: [164.5, 201.1],
  },
  dual_toxocyst: {
    multishot: [136.3, 166.6],
    critical_damage: [102.5, 125.3],
    critical_chance: [170.9, 208.8],
  },
  burston: {
    multishot: [110.1, 134.6],
    critical_damage: [146.8, 179.4],
    critical_chance: [183.5, 224.3],
  },
  latron: {
    multishot: [106.3, 129.9],
    critical_damage: [141.7, 173.2],
    critical_chance: [177.2, 216.6],
  },
}

/** Human label for a stat url_name (best-effort title case). */
export function statLabel(urlName: string): string {
  return urlName
    .split('_')
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(' ')
}
