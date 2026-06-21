import type { JSX } from "solid-js";

type Variant = "neutral" | "good" | "warn" | "bad" | "vaulted" | "info";

const VARIANT: Record<Variant, string> = {
  neutral: "bg-slate-900/40 text-slate-300 border-slate-800 shadow-[0_0_10px_rgba(0,0,0,0.05)]",
  good:    "bg-emerald-950/20 text-emerald-400 border-emerald-500/15 shadow-[0_0_12px_rgba(16,185,129,0.06)]",
  warn:    "bg-amber-950/20 text-amber-300 border-amber-500/15 shadow-[0_0_12px_rgba(245,158,11,0.06)]",
  bad:     "bg-rose-950/20 text-rose-400 border-rose-500/15 shadow-[0_0_12px_rgba(239,68,68,0.06)]",
  vaulted: "bg-indigo-950/20 text-indigo-300 border-indigo-500/15 shadow-[0_0_12px_rgba(99,102,241,0.06)]",
  info:    "bg-sky-950/20 text-sky-300 border-sky-500/15 shadow-[0_0_12px_rgba(14,165,233,0.06)]",
};

export default function Badge(props: { variant?: Variant; children: JSX.Element }) {
  const cls = VARIANT[props.variant ?? "neutral"];
  return (
    <span class={`inline-flex items-center text-[11px] font-semibold tracking-wide px-3 py-0.5 rounded-full border ${cls}`}>
      {props.children}
    </span>
  );
}
