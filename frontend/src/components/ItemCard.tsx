import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import Badge from "./Badge";
import { t } from "../i18n";

export default function ItemCard(props: { item: PricedItem }) {
  const it = () => props.item;
  const usedIn = () => it().used_in ?? [];
  return (
    <article class="rounded-3xl glass-panel glass-panel-hover p-5 shadow-[0_8px_30px_rgba(0,0,0,0.2)] transition-all duration-300 flex flex-col justify-between">
      <div>
        <header class="flex items-start justify-between gap-3 mb-3">
          <div>
            <h3 class="text-slate-100 font-semibold tracking-tight text-[15px]">{it().name}</h3>
            <Show when={it().slug}>
              <div class="text-[11px] text-slate-500 font-mono tracking-wide select-all mt-0.5">{it().slug}</div>
            </Show>
          </div>
          <Show when={it().vaulted}>
            <Badge variant="vaulted">{t("common.vaulted")}</Badge>
          </Show>
        </header>
      </div>

      <Show
        when={usedIn().length > 0}
        fallback={
          <div class="border-t border-white/[0.03] pt-3.5 mt-3.5">
            <p class="text-[11px] text-slate-500 italic font-mono">{t("inventory.finalProduct")}</p>
          </div>
        }
      >
        <div class="border-t border-white/[0.03] pt-3.5 mt-3.5">
          <div class="text-[10px] text-slate-400 font-mono uppercase tracking-wider mb-2">{t("inventory.usedIn")}</div>
          <ul class="flex flex-wrap gap-1.5">
            {usedIn().map((u) => (
              <li class="px-2.5 py-1 text-[11px] font-medium rounded-xl bg-slate-950/50 border border-white/[0.04] text-slate-300 hover:text-emerald-300 hover:border-emerald-500/20 hover:bg-emerald-500/[0.03] transition-all duration-300 font-mono">
                {u.count > 1 && <span class="text-emerald-400 font-semibold mr-0.5">{u.count}×</span>}
                {u.name}
              </li>
            ))}
          </ul>
        </div>
      </Show>
    </article>
  );
}
