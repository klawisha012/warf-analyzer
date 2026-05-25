import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
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
      <p class="text-sm text-slate-400">{t("inventory.builtNotCraftable")}</p>
    </article>
  );
}
