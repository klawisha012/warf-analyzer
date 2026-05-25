import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtInt, fmtPlat } from "../lib/format";
import Badge from "./Badge";
import { t } from "../i18n";

export default function ItemCard(props: { item: PricedItem }) {
  const it = () => props.item;
  return (
    <article class="rounded-xl bg-slate-900 border border-slate-800 p-3 hover:border-slate-700 transition-colors">
      <header class="flex items-start justify-between gap-2 mb-2">
        <div>
          <div class="text-slate-100 font-medium">{it().name}</div>
          <Show when={it().slug}>
            <div class="text-xs text-slate-500 font-mono">{it().slug}</div>
          </Show>
        </div>
        <Show when={it().vaulted}>
          <Badge variant="vaulted">{t("common.vaulted")}</Badge>
        </Show>
      </header>
      <dl class="grid grid-cols-2 gap-y-1 text-sm">
        <dt class="text-slate-400">{t("item.qty")}</dt>
        <dd class="text-right font-mono text-slate-100">{fmtInt(it().count)}</dd>
        <dt class="text-slate-400">{t("item.sellMedian")}</dt>
        <dd class="text-right font-mono text-slate-100">{fmtPlat(it().sell_median)}</dd>
        <dt class="text-slate-400">{t("item.sellMin")}</dt>
        <dd class="text-right font-mono text-slate-300">{fmtPlat(it().sell_min)}</dd>
        <dt class="text-slate-400">{t("item.buyMax")}</dt>
        <dd class="text-right font-mono text-slate-300">{fmtPlat(it().buy_max)}</dd>
        <dt class="text-slate-400">{t("item.estValue")}</dt>
        <dd class="text-right font-mono text-emerald-300">{fmtPlat(it().estimated_value)}</dd>
      </dl>
    </article>
  );
}
