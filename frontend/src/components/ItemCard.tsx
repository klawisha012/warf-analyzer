import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import Badge from "./Badge";
import ItemThumb from "./ItemThumb";
import { useItemThumbs, warframestatImg } from "../lib/itemImages";
import { t } from "../i18n";

export default function ItemCard(props: { item: PricedItem }) {
  const it = () => props.item;
  const usedIn = () => it().used_in ?? [];
  const thumbOf = useItemThumbs();
  return (
    <article class="surface p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-line-strong">
      <header class="flex items-center gap-3">
        <ItemThumb src={thumbOf(it().slug)} fallback={warframestatImg(it().image_name)} name={it().name} size={44} />
        <div class="min-w-0 flex-1">
          <h3 class="text-fg font-semibold tracking-tight text-[15px] truncate">{it().name}</h3>
          <Show when={it().slug}>
            <div class="text-[11px] text-dim tracking-wide select-all mt-0.5">{it().slug}</div>
          </Show>
        </div>
        <Show when={it().vaulted}>
          <Badge variant="vaulted">{t("common.vaulted")}</Badge>
        </Show>
      </header>

      <Show when={usedIn().length > 0}>
        <div class="border-t border-line pt-3.5 mt-3.5">
          <div class="text-[10px] text-sub uppercase tracking-wider mb-2">{t("inventory.usedIn")}</div>
          <ul class="flex flex-wrap gap-1.5">
            {usedIn().map((u) => (
              <li class="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-surface2 border border-line text-sub hover:text-brand-soft hover:border-brand/30 transition-colors duration-200">
                {u.count > 1 && <span class="text-mint font-semibold mr-0.5 num">{u.count}×</span>}
                {u.name}
              </li>
            ))}
          </ul>
        </div>
      </Show>
    </article>
  );
}
