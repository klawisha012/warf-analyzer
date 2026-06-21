import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import ItemRow from "../components/ItemRow";
import { fetchers, keys } from "../api/queries";
import { fmtPlat } from "../lib/format";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function PrimeParts() {
  const [minCount, setMinCount] = createSignal(1);
  const [q, setQ] = createSignal("");

  const parts = createQuery(() => ({
    queryKey: keys.mePrimeParts(minCount()),
    queryFn:  () => fetchers.mePrimeParts(minCount()),
  }));

  const filtered = createMemo(() => {
    const needle = q().toLowerCase().trim();
    const all = parts.data?.items ?? [];
    return needle ? all.filter((x) => x.name.toLowerCase().includes(needle)) : all;
  });

  const totalValue = createMemo(() =>
    filtered().reduce((sum, it) => sum + (it.estimated_value ?? 0), 0),
  );

  // Subscribe to every visible row, not just top-10: the page is fully
  // scrolled and a price update on row 25 needs to reach the UI too.
  useSlugChannel(() => filtered().map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      {/* High-Tech Diagnostic Telemetry Dashboards */}
      <section class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title={t("primeParts.portfolioTitle") ?? "Portfolio Valuation"} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-emerald-500/[0.02] blur-xl group-hover:bg-emerald-500/[0.04] transition-all duration-500"></div>
          <div class="flex items-baseline gap-2">
            <span class="text-3xl font-extrabold tracking-tight text-emerald-400 font-mono animated-pulse-glow drop-shadow-[0_0_12px_rgba(52,211,153,0.3)]">
              {fmtPlat(totalValue())}
            </span>
            <span class="text-xs font-semibold text-emerald-500/80 uppercase font-mono tracking-widest">{t("common.plat") ?? "Plat"}</span>
          </div>
          <div class="text-[11px] text-slate-500 font-mono mt-2 flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500/40"></span>
            <span>{t("primeParts.activeEstimates") ?? "Live value snapshot across visible inventory items"}</span>
          </div>
        </Card>

        <Card title={t("primeParts.inventoryMetrics") ?? "System Inventory Metrics"} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-teal-500/[0.02] blur-xl group-hover:bg-teal-500/[0.04] transition-all duration-500"></div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="text-2xl font-bold tracking-tight text-teal-300 font-mono">
                {filtered().length}
              </div>
              <div class="text-[10px] text-slate-500 font-mono uppercase tracking-wider mt-0.5">{t("primeParts.uniqueCount") ?? "Unique Items"}</div>
            </div>
            <div>
              <div class="text-2xl font-bold tracking-tight text-indigo-300 font-mono">
                {filtered().reduce((sum, it) => sum + (it.count ?? 0), 0)}
              </div>
              <div class="text-[10px] text-slate-500 font-mono uppercase tracking-wider mt-0.5">{t("primeParts.totalCount") ?? "Total Quantity"}</div>
            </div>
          </div>
        </Card>
      </section>

      {/* Control Panel Toolbar */}
      <header class="flex flex-wrap items-center justify-between gap-4 bg-slate-900/30 p-2.5 rounded-2xl border border-white/[0.02] backdrop-blur-md">
        <h1 class="text-xl font-bold tracking-tight text-slate-100 px-2 font-sans flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"></span>
          {t("primeParts.title")}
        </h1>
        <div class="flex flex-wrap items-center gap-4">
          {/* Min Quantity Calibration Dial */}
          <label class="text-xs font-semibold text-slate-400 flex items-center gap-2 font-mono uppercase tracking-wider bg-slate-950/60 p-1.5 rounded-xl border border-white/[0.02] px-3">
            {t("primeParts.minQty")}
            <input
              type="number"
              min={1}
              value={minCount()}
              onInput={(e) => setMinCount(Math.max(1, +e.currentTarget.value || 1))}
              class="w-12 text-center py-0.5 rounded-md bg-slate-900 border border-white/[0.06] text-emerald-400 focus:outline-none focus:border-emerald-500/40 text-xs font-bold font-mono"
            />
          </label>

          {/* Search Box */}
          <div class="relative w-full sm:w-60">
            <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <svg class="h-4 w-4 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
              </svg>
            </div>
            <input
              type="search"
              placeholder={t("common.filter")}
              value={q()}
              onInput={(e) => setQ(e.currentTarget.value)}
              class="w-full pl-9 pr-4 py-1.5 text-xs rounded-xl bg-slate-950/50 border border-white/[0.04] text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500/40 focus:ring-2 focus:ring-emerald-500/10 transition-all font-mono"
            />
          </div>
        </div>
      </header>

      {/* Spreadsheet List Card */}
      <Card>
        <Show
          when={!parts.isLoading}
          fallback={
            <div class="flex flex-col items-center justify-center py-16 gap-3">
              <div class="w-8 h-8 rounded-full border-2 border-emerald-500/20 border-t-emerald-400 animate-spin"></div>
              <span class="text-xs font-mono uppercase tracking-widest text-slate-500 animate-pulse">{t("common.loading")}</span>
            </div>
          }
        >
          <Show
            when={filtered().length > 0}
            fallback={<EmptyState title={t("primeParts.empty")} hint={t("primeParts.emptyHint")} />}
          >
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="text-left text-slate-400">
                  <tr class="border-b border-white/[0.03]">
                    <th class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400">{t("primeParts.col.item")}</th>
                    <th class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 text-right">{t("primeParts.col.qty")}</th>
                    <th class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 text-right">{t("primeParts.col.sell")}</th>
                    <th class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 text-right">{t("primeParts.col.buyMax")}</th>
                    <th class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 text-right">{t("primeParts.col.estValue")}</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-white/[0.01]">
                  <For each={filtered()}>{(it) => <ItemRow item={it} />}</For>
                </tbody>
              </table>
            </div>
          </Show>
        </Show>
      </Card>
    </div>
  );
}
