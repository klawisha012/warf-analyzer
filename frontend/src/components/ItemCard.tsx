import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import Badge from "./Badge";
import { t } from "../i18n";

export default function ItemCard(props: { item: PricedItem }) {
  const it = () => props.item;
  const usedIn = () => it().used_in ?? [];
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
      <Show
        when={usedIn().length > 0}
        fallback={
          <p class="text-sm text-slate-500 italic">{t("inventory.finalProduct")}</p>
        }
      >
        <div class="text-sm">
          <div class="text-slate-400 mb-1">{t("inventory.usedIn")}</div>
          <ul class="flex flex-wrap gap-1">
            {usedIn().map((u) => (
              <li class="px-2 py-0.5 rounded bg-slate-800 text-slate-200 text-xs">
                {u.count > 1 ? `${u.count}× ` : ""}{u.name}
              </li>
            ))}
          </ul>
        </div>
      </Show>
    </article>
  );
}
