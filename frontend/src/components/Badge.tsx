import type { JSX } from "solid-js";

type Variant = "neutral" | "good" | "warn" | "bad" | "vaulted" | "info";

const VARIANT: Record<Variant, string> = {
  neutral: "bg-slate-800 text-slate-300 border-slate-700",
  good:    "bg-emerald-900/40 text-emerald-300 border-emerald-800",
  warn:    "bg-amber-900/40 text-amber-200 border-amber-800",
  bad:     "bg-rose-900/40 text-rose-300 border-rose-800",
  vaulted: "bg-indigo-900/40 text-indigo-300 border-indigo-800",
  info:    "bg-sky-900/40 text-sky-300 border-sky-800",
};

export default function Badge(props: { variant?: Variant; children: JSX.Element }) {
  const cls = VARIANT[props.variant ?? "neutral"];
  return (
    <span class={`inline-flex items-center text-xs px-2 py-0.5 rounded-md border ${cls}`}>
      {props.children}
    </span>
  );
}
