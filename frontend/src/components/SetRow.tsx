import { For, Show } from "solid-js";
import type { SetProfitRow } from "../api/types";
import { fmtPlat, prettySlug, wfmUrl } from "../lib/format";
import Badge from "./Badge";
import { t } from "../i18n";

export default function SetRowComp(props: { row: SetProfitRow }) {
  const profitVariant = () =>
    props.row.profit >= 30 ? "good" : props.row.profit >= 10 ? "info" : "neutral";
  const missing = () => Object.entries(props.row.missing_parts ?? {});

  const ownedCount = () => Object.values(props.row.owned_parts ?? {}).reduce((sum, qty) => sum + qty, 0);
  const missingCount = () => Object.values(props.row.missing_parts ?? {}).reduce((sum, qty) => sum + qty, 0);
  const totalParts = () => ownedCount() + missingCount();
  const pct = () => totalParts() > 0 ? Math.round((ownedCount() / totalParts()) * 100) : 0;

  const partsList = () => {
    const list: { slug: string; owned: boolean; qty: number }[] = [];
    for (const [slug, qty] of Object.entries(props.row.owned_parts ?? {})) {
      list.push({ slug, owned: true, qty });
    }
    for (const [slug, qty] of Object.entries(props.row.missing_parts ?? {})) {
      list.push({ slug, owned: false, qty });
    }
    return list;
  };

  return (
    <article class="surface p-5 transition-all duration-300 hover:-translate-y-0.5 hover:border-line-strong flex flex-col justify-between">
      <div>
        <header class="flex items-start justify-between gap-3 mb-3">
          <div class="min-w-0">
            <a
              href={wfmUrl(props.row.set_slug)}
              target="_blank"
              rel="noopener noreferrer"
              class="text-fg font-bold tracking-tight hover:text-brand-soft transition-colors text-[15px] block"
            >
              {props.row.set_name}
            </a>
            <div class="text-[11px] text-dim tracking-wide mt-0.5 select-all">{props.row.set_slug}</div>
          </div>
          <Badge variant={profitVariant() as never}>{t("sets.profitBadge", { plat: fmtPlat(props.row.profit) })}</Badge>
        </header>

        <dl class="grid grid-cols-2 gap-3 text-xs mb-3 border-t border-line pt-3">
          <div>
            <dt class="text-dim uppercase tracking-wider mb-0.5">{t("sets.setPrice")}</dt>
            <dd class="num text-fg font-bold text-[13px]">{fmtPlat(props.row.set_price)}</dd>
          </div>
          <div>
            <dt class="text-dim uppercase tracking-wider mb-0.5">{t("sets.partsCost")}</dt>
            <dd class="num text-fg font-bold text-[13px]">{fmtPlat(props.row.parts_cost)}</dd>
          </div>
        </dl>

        {/* completeness segment gauges */}
        <div class="border-t border-line pt-3.5 mt-3">
          <div class="flex items-center justify-between text-[10px] mb-1.5">
            <span class="text-sub uppercase tracking-wider">{t("sets.completeness") ?? "Completeness"}</span>
            <span class="text-mint font-bold num">{ownedCount()} / {totalParts()} <span class="text-dim text-[9px]">({pct()}%)</span></span>
          </div>
          <div class="h-2 w-full rounded-full overflow-hidden border border-line p-0.5 flex gap-1 bg-surface2">
            <For each={partsList()}>
              {(part) => (
                <div
                  class="h-full rounded-full transition-all duration-500 flex-1"
                  classList={{
                    "bg-mint shadow-[0_0_8px_rgba(52,211,153,0.5)]": part.owned,
                    "bg-white/[0.06]": !part.owned,
                  }}
                  title={`${part.qty}x ${prettySlug(part.slug)} (${part.owned ? "Owned" : "Missing"})`}
                ></div>
              )}
            </For>
          </div>
        </div>
      </div>

      <Show when={missing().length > 0}>
        <div class="border-t border-line pt-3.5 mt-3.5">
          <div class="text-[10px] text-sub uppercase tracking-wider mb-2">{t("sets.toBuy")}</div>
          <ul class="flex flex-wrap gap-1.5">
            <For each={missing()}>
              {([slug, qty]) => (
                <li>
                  <a
                    href={wfmUrl(slug)}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-[11px] font-medium px-2.5 py-1 rounded-lg bg-surface2 border border-line text-sub hover:text-brand-soft hover:border-brand/30 transition-colors duration-200 inline-block"
                  >
                    <span class="text-rose-400 font-semibold mr-0.5 num">{qty}×</span> {prettySlug(slug)}
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
