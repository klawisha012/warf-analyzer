import { For, Show } from "solid-js";
import type { SetProfitRow } from "../api/types";
import { fmtPlat, prettySlug, wfmUrl } from "../lib/format";
import Badge from "./Badge";
import { t } from "../i18n";

export default function SetRowComp(props: { row: SetProfitRow }) {
  const profitVariant = () =>
    props.row.profit >= 30 ? "good" : props.row.profit >= 10 ? "info" : "neutral";
  const missing = () => Object.entries(props.row.missing_parts ?? {});
  return (
    <article class="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <header class="flex items-center justify-between gap-3 mb-2">
        <div>
          <a
            href={wfmUrl(props.row.set_slug)}
            target="_blank"
            rel="noopener noreferrer"
            class="text-slate-100 font-semibold hover:text-emerald-300 transition-colors"
          >
            {props.row.set_name}
          </a>
          <div class="text-xs text-slate-500 font-mono">{props.row.set_slug}</div>
        </div>
        <Badge variant={profitVariant() as never}>{t("sets.profitBadge", { plat: fmtPlat(props.row.profit) })}</Badge>
      </header>
      <dl class="grid grid-cols-3 gap-2 text-sm mb-2">
        <div>
          <dt class="text-slate-400 text-xs">{t("sets.setPrice")}</dt>
          <dd class="font-mono text-slate-100">{fmtPlat(props.row.set_price)}</dd>
        </div>
        <div>
          <dt class="text-slate-400 text-xs">{t("sets.partsCost")}</dt>
          <dd class="font-mono text-slate-100">{fmtPlat(props.row.parts_cost)}</dd>
        </div>
        <div>
          <dt class="text-slate-400 text-xs">{t("sets.taxEst")}</dt>
          <dd class="font-mono text-slate-300">{fmtPlat(props.row.tax_estimate)}</dd>
        </div>
      </dl>
      <Show when={missing().length > 0}>
        <div>
          <div class="text-xs text-slate-400 mb-1">{t("sets.toBuy")}</div>
          <ul class="flex flex-wrap gap-1">
            <For each={missing()}>
              {([slug, qty]) => (
                <li>
                  <a
                    href={wfmUrl(slug)}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 hover:text-emerald-300 hover:bg-slate-700 transition-colors inline-block"
                  >
                    {qty}× {prettySlug(slug)}
                  </a>
                </li>
              )}
            </For>
          </ul>
        </div>
      </Show>
    </article>
  );
}
