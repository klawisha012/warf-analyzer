import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtInt, fmtPlat } from "../lib/format";
import { priceFor } from "../lib/priceStore";
import Badge from "./Badge";
import PriceCell from "./PriceCell";
import { t } from "../i18n";

export default function ItemRow(props: { item: PricedItem }) {
  const live = () => priceFor(props.item.slug);
  const buyMax = () => live()?.buy_max ?? props.item.buy_max;
  const sellMedian = () => live()?.sell_median ?? props.item.sell_median;
  const estValue = () => {
    const med = sellMedian();
    const count = props.item.count ?? 0;
    return med != null ? med * count : props.item.estimated_value;
  };
  const stale = () => live()?.stale ?? props.item.stale;
  return (
    <tr class="border-b border-slate-800 hover:bg-slate-900/60">
      <td class="py-2 px-3">
        <div class="text-slate-100">{props.item.name}</div>
        <Show when={props.item.slug}>
          <a
            href={`https://warframe.market/items/${props.item.slug}`}
            target="_blank"
            class="text-xs text-slate-500 hover:text-slate-300 font-mono"
          >
            {props.item.slug}
          </a>
        </Show>
      </td>
      <td class="py-2 px-3 text-right font-mono">{fmtInt(props.item.count)}</td>
      <td class="py-2 px-3">
        <Show when={props.item.vaulted}>
          <Badge variant="vaulted">{t("common.vaulted")}</Badge>
        </Show>
        <Show when={stale()}>
          <Badge variant="warn">{t("common.stale")}</Badge>
        </Show>
      </td>
      <td class="py-2 px-3"><PriceCell item={props.item} /></td>
      <td class="py-2 px-3 text-right font-mono text-slate-300">
        {fmtPlat(buyMax())}
      </td>
      <td class="py-2 px-3 text-right font-mono text-slate-100">
        {fmtPlat(estValue())}
      </td>
    </tr>
  );
}
