export function fmtPlat(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n.toLocaleString("en-US")}p`;
}

export function fmtInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US");
}

export function fmtRelTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const dt = Date.now() - then;
  const s = Math.round(dt / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function spreadPct(min: number | null, median: number | null): number | null {
  if (min == null || median == null || median === 0) return null;
  return Math.round(((median - min) / median) * 100);
}
