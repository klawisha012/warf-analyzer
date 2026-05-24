import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtPlat, spreadPct } from "../lib/format";

export default function PriceCell(props: { item: PricedItem }) {
  const sp = () => spreadPct(props.item.sell_min, props.item.sell_median);
  return (
    <div class="text-right font-mono">
      <Show
        when={props.item.sell_median != null}
        fallback={<span class="text-slate-500">—</span>}
      >
        <div class="text-slate-100">{fmtPlat(props.item.sell_median)}</div>
        <div class="text-xs text-slate-400">
          min {fmtPlat(props.item.sell_min)}
          <Show when={sp() != null}> · spread {sp()}%</Show>
        </div>
      </Show>
    </div>
  );
}
