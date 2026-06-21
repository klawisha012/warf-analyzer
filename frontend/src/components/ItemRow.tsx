import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtInt, fmtPlat } from "../lib/format";
import { priceFor } from "../lib/priceStore";
import PriceCell from "./PriceCell";

export default function ItemRow(props: { item: PricedItem }) {
  const live = () => priceFor(props.item.slug);
  const buyMax = () => live()?.buy_max ?? props.item.buy_max;
  // Estimated value uses sell_min × count so it matches the price shown in
  // the Sell column (the practical floor) rather than a median that may not
  // actually be hit.
  const estValue = () => {
    const minP = live()?.sell_min ?? props.item.sell_min;
    const count = props.item.count ?? 0;
    return minP != null ? minP * count : props.item.estimated_value;
  };
  return (
    <tr class="border-b border-white/[0.02] hover:bg-white/[0.01] hover:shadow-[inset_0_0_15px_rgba(255,255,255,0.01)] transition-all duration-300 group">
      <td class="py-3.5 px-4">
        <div class="text-slate-200 font-semibold tracking-tight text-[13px] group-hover:text-emerald-300 transition-colors">{props.item.name}</div>
        <Show when={props.item.slug}>
          <a
            href={`https://warframe.market/items/${props.item.slug}`}
            target="_blank"
            class="text-[10px] text-slate-500 hover:text-emerald-400 font-mono tracking-wider inline-flex items-center gap-1 mt-0.5 transition-colors group/link"
          >
            {props.item.slug}
            <svg class="w-2.5 h-2.5 opacity-0 group-hover/link:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>
            </svg>
          </a>
        </Show>
      </td>
      <td class="py-3.5 px-4 text-right font-mono text-[13px] text-slate-300 font-medium">{fmtInt(props.item.count)}</td>
      <td class="py-3.5 px-4 text-right"><PriceCell item={props.item} /></td>
      <td class="py-3.5 px-4 text-right font-mono text-[13px] text-teal-400/90 font-medium">
        {fmtPlat(buyMax())}
      </td>
      <td class="py-3.5 px-4 text-right font-mono text-[13px] text-emerald-400 font-bold">
        {fmtPlat(estValue())}
      </td>
    </tr>
  );
}
