import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtPlat } from "../lib/format";
import { priceFor } from "../lib/priceStore";
import { t } from "../i18n";

export default function PriceCell(props: { item: PricedItem }) {
  // Live price wins over the backend snapshot; we show the minimum sell
  // offer as the primary number — that's the price you'd actually pay or
  // need to undercut on WFM.
  const sellMin = () => priceFor(props.item.slug)?.sell_min ?? props.item.sell_min;
  return (
    <div class="text-right font-mono">
      <Show
        when={sellMin() != null}
        fallback={<span class="text-slate-500">{t("common.dash")}</span>}
      >
        <div class="text-slate-100">{fmtPlat(sellMin())}</div>
      </Show>
    </div>
  );
}
