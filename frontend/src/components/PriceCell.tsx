import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtPlat, spreadPct } from "../lib/format";
import { priceFor } from "../lib/priceStore";
import { t } from "../i18n";

export default function PriceCell(props: { item: PricedItem }) {
  // Prefer live prices from the global store (kept fresh by Centrifugo push
  // updates). Fall back to the snapshot the backend embedded in the row.
  const live = () => priceFor(props.item.slug);
  const sellMin = () => live()?.sell_min ?? props.item.sell_min;
  const sellMedian = () => live()?.sell_median ?? props.item.sell_median;
  const sp = () => spreadPct(sellMin(), sellMedian());
  return (
    <div class="text-right font-mono">
      <Show
        when={sellMedian() != null}
        fallback={<span class="text-slate-500">{t("common.dash")}</span>}
      >
        <div class="text-slate-100">{fmtPlat(sellMedian())}</div>
        <div class="text-xs text-slate-400">
          {t("item.minPrefix")} {fmtPlat(sellMin())}
          <Show when={sp() != null}> · {t("item.spread")} {sp()}%</Show>
        </div>
      </Show>
    </div>
  );
}
