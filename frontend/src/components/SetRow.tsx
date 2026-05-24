import { For, Show } from "solid-js";
import type { SetProfitRow } from "../api/types";
import { fmtPlat } from "../lib/format";
import Badge from "./Badge";

export default function SetRowComp(props: { row: SetProfitRow }) {
  const profitVariant = () =>
    props.row.profit >= 30 ? "good" : props.row.profit >= 10 ? "info" : "neutral";
  const missing = () => Object.entries(props.row.missing_parts ?? {});
  return (
    <article class="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <header class="flex items-center justify-between gap-3 mb-2">
        <div>
          <div class="text-slate-100 font-semibold">{props.row.set_name}</div>
          <div class="text-xs text-slate-500 font-mono">{props.row.set_slug}</div>
        </div>
        <Badge variant={profitVariant() as never}>+{fmtPlat(props.row.profit)} profit</Badge>
      </header>
      <dl class="grid grid-cols-3 gap-2 text-sm mb-2">
        <div>
          <dt class="text-slate-400 text-xs">Set price</dt>
          <dd class="font-mono text-slate-100">{fmtPlat(props.row.set_price)}</dd>
        </div>
        <div>
          <dt class="text-slate-400 text-xs">Parts cost</dt>
          <dd class="font-mono text-slate-100">{fmtPlat(props.row.parts_cost)}</dd>
        </div>
        <div>
          <dt class="text-slate-400 text-xs">Tax (est.)</dt>
          <dd class="font-mono text-slate-300">{fmtPlat(props.row.tax_estimate)}</dd>
        </div>
      </dl>
      <Show when={missing().length > 0}>
        <div>
          <div class="text-xs text-slate-400 mb-1">To buy:</div>
          <ul class="flex flex-wrap gap-1">
            <For each={missing()}>
              {([slug, qty]) => (
                <li class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                  {qty}× {slug}
                </li>
              )}
            </For>
          </ul>
        </div>
      </Show>
    </article>
  );
}
