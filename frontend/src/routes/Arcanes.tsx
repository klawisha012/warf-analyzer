import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, fmtInt } from "../lib/format";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function Arcanes() {
  const [minCount, setMinCount] = createSignal(1);
  const [q, setQ] = createSignal("");
  const [sortBy, setSortBy] = createSignal<string>("est_value");
  const [sortDir, setSortDir] = createSignal<"asc" | "desc">("desc");

  const arcanes = createQuery(() => ({
    queryKey: keys.meArcanes(minCount()),
    queryFn:  () => fetchers.meArcanes(minCount()),
  }));

  const filtered = createMemo(() => {
    const needle = q().toLowerCase().trim();
    const all = arcanes.data?.items ?? [];
    return needle ? all.filter((x) => x.name.toLowerCase().includes(needle)) : all;
  });

  const sorted = createMemo(() => {
    const items = [...filtered()];
    const dir = sortDir() === "asc" ? 1 : -1;
    const field = sortBy();

    items.sort((a, b) => {
      let valA: any = "";
      let valB: any = "";

      if (field === "name") {
        valA = a.name.toLowerCase();
        valB = b.name.toLowerCase();
        return valA.localeCompare(valB) * dir;
      } else if (field === "count") {
        valA = a.count ?? 0;
        valB = b.count ?? 0;
      } else if (field === "sell_min") {
        valA = a.sell_min ?? 0;
        valB = b.sell_min ?? 0;
      } else if (field === "sell_min_max_rank") {
        valA = a.sell_min_max_rank ?? 0;
        valB = b.sell_min_max_rank ?? 0;
      } else if (field === "buy_max") {
        valA = a.buy_max ?? 0;
        valB = b.buy_max ?? 0;
      } else if (field === "buy_max_max_rank") {
        valA = a.buy_max_max_rank ?? 0;
        valB = b.buy_max_max_rank ?? 0;
      } else if (field === "est_value") {
        valA = a.estimated_value ?? 0;
        valB = b.estimated_value ?? 0;
      }

      return (valA > valB ? 1 : valA < valB ? -1 : 0) * dir;
    });

    return items;
  });

  const totalValue = createMemo(() =>
    filtered().reduce((sum, it) => sum + (it.estimated_value ?? 0), 0),
  );

  // Subscribe to visible slugs
  useSlugChannel(() => sorted().map((it) => it.slug).filter(Boolean) as string[]);

  const toggleSort = (field: string) => {
    if (sortBy() === field) {
      setSortDir(sortDir() === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("desc");
    }
  };

  return (
    <div class="space-y-6">
      {/* High-Tech Diagnostic Telemetry Dashboards */}
      <section class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card title={t("arcanes.portfolioTitle") ?? "Arcanes Valuation"} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-emerald-500/[0.02] blur-xl group-hover:bg-emerald-500/[0.04] transition-all duration-500"></div>
          <div class="flex items-baseline gap-2">
            <span class="text-3xl font-extrabold tracking-tight text-emerald-400 font-mono animated-pulse-glow drop-shadow-[0_0_12px_rgba(52,211,153,0.3)]">
              {fmtPlat(totalValue())}
            </span>
            <span class="text-xs font-semibold text-emerald-500/80 uppercase font-mono tracking-widest">{t("common.plat") ?? "Plat"}</span>
          </div>
          <div class="text-[11px] text-slate-500 font-mono mt-2 flex items-center gap-2">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-500/40"></span>
            <span>Live value snapshot across visible arcanes and cosmetic enhancers</span>
          </div>
        </Card>

        <Card title={t("arcanes.inventoryMetrics") ?? "Arcane Inventory Metrics"} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-teal-500/[0.02] blur-xl group-hover:bg-teal-500/[0.04] transition-all duration-500"></div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="text-2xl font-bold tracking-tight text-teal-300 font-mono">
                {filtered().length}
              </div>
              <div class="text-[10px] text-slate-500 font-mono uppercase tracking-wider mt-0.5">Unique Arcanes</div>
            </div>
            <div>
              <div class="text-2xl font-bold tracking-tight text-indigo-300 font-mono">
                {filtered().reduce((sum, it) => sum + (it.count ?? 0), 0)}
              </div>
              <div class="text-[10px] text-slate-500 font-mono uppercase tracking-wider mt-0.5">Total Quantity</div>
            </div>
          </div>
        </Card>
      </section>

      {/* Control Panel Toolbar */}
      <header class="flex flex-wrap items-center justify-between gap-4 bg-slate-900/30 p-2.5 rounded-2xl border border-white/[0.02] backdrop-blur-md">
        <h1 class="text-xl font-bold tracking-tight text-slate-100 px-2 font-sans flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"></span>
          {t("arcanes.title") ?? "Arcanes Inventory"}
        </h1>
        <div class="flex flex-wrap items-center gap-4">
          <label class="text-xs font-semibold text-slate-400 flex items-center gap-2 font-mono uppercase tracking-wider bg-slate-950/60 p-1.5 rounded-xl border border-white/[0.02] px-3">
            {t("primeParts.minQty") ?? "Min Qty"}
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
          when={!arcanes.isLoading}
          fallback={
            <div class="flex flex-col items-center justify-center py-16 gap-3">
              <div class="w-8 h-8 rounded-full border-2 border-emerald-500/20 border-t-emerald-400 animate-spin"></div>
              <span class="text-xs font-mono uppercase tracking-widest text-slate-500 animate-pulse">{t("common.loading")}</span>
            </div>
          }
        >
          <Show
            when={sorted().length > 0}
            fallback={<EmptyState title="No arcanes found" hint="Try adjusting your filter or minimum quantity" />}
          >
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead class="text-left text-slate-400">
                  <tr class="border-b border-white/[0.03]">
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none"
                      onClick={() => toggleSort("name")}
                    >
                      <div class="flex items-center gap-1">
                        Arcane
                        <Show when={sortBy() === "name"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none text-right"
                      onClick={() => toggleSort("count")}
                    >
                      <div class="flex items-center justify-end gap-1">
                        Qty
                        <Show when={sortBy() === "count"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none text-right"
                      onClick={() => toggleSort("sell_min")}
                    >
                      <div class="flex items-center justify-end gap-1">
                        Sell (0)
                        <Show when={sortBy() === "sell_min"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none text-right"
                      onClick={() => toggleSort("sell_min_max_rank")}
                    >
                      <div class="flex items-center justify-end gap-1">
                        Sell (Max)
                        <Show when={sortBy() === "sell_min_max_rank"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none text-right"
                      onClick={() => toggleSort("buy_max")}
                    >
                      <div class="flex items-center justify-end gap-1">
                        Buy Max (0)
                        <Show when={sortBy() === "buy_max"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none text-right"
                      onClick={() => toggleSort("buy_max_max_rank")}
                    >
                      <div class="flex items-center justify-end gap-1">
                        Buy Max (Max)
                        <Show when={sortBy() === "buy_max_max_rank"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                    <th 
                      class="py-3 px-4 text-xs font-bold uppercase tracking-wider font-mono text-slate-400 cursor-pointer hover:text-emerald-300 transition-colors select-none text-right"
                      onClick={() => toggleSort("est_value")}
                    >
                      <div class="flex items-center justify-end gap-1">
                        Est. Value
                        <Show when={sortBy() === "est_value"}>
                          <span class="text-[10px] text-emerald-400">{sortDir() === "asc" ? "▲" : "▼"}</span>
                        </Show>
                      </div>
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-white/[0.01]">
                  <For each={sorted()}>
                    {(it) => (
                      <tr class="border-b border-white/[0.02] hover:bg-white/[0.01] hover:shadow-[inset_0_0_15px_rgba(255,255,255,0.01)] transition-all duration-300 group">
                        <td class="py-3.5 px-4">
                          <div class="text-slate-200 font-semibold tracking-tight text-[13px] group-hover:text-emerald-300 transition-colors">
                            {it.name}
                            <span class="text-[9px] text-slate-500 font-mono ml-2 px-1.5 py-0.2 rounded bg-slate-950/40 border border-slate-800/50 uppercase tracking-widest">
                              Max Rank {it.max_rank}
                            </span>
                          </div>
                          <Show when={it.slug}>
                            <a
                              href={`https://warframe.market/items/${it.slug}`}
                              target="_blank"
                              class="text-[10px] text-slate-500 hover:text-emerald-400 font-mono tracking-wider inline-flex items-center gap-1 mt-0.5 transition-colors group/link"
                            >
                              {it.slug}
                              <svg class="w-2.5 h-2.5 opacity-0 group-hover/link:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path>
                              </svg>
                            </a>
                          </Show>
                        </td>
                        <td class="py-3.5 px-4 text-right font-mono text-[13px] text-slate-300 font-medium">{fmtInt(it.count)}</td>
                        {/* Base Sell Price */}
                        <td class="py-3.5 px-4 text-right font-mono text-[13px] text-slate-200 font-semibold">
                          <Show when={it.sell_min != null} fallback={<span class="text-slate-600">—</span>}>
                            {fmtPlat(it.sell_min)}
                          </Show>
                        </td>
                        {/* Max Sell Price */}
                        <td class="py-3.5 px-4 text-right font-mono text-[13px] text-emerald-400/90 font-bold">
                          <Show when={it.sell_min_max_rank != null} fallback={<span class="text-slate-600">—</span>}>
                            {fmtPlat(it.sell_min_max_rank)}
                          </Show>
                        </td>
                        {/* Base Buy Price */}
                        <td class="py-3.5 px-4 text-right font-mono text-[13px] text-slate-300">
                          <Show when={it.buy_max != null} fallback={<span class="text-slate-600">—</span>}>
                            {fmtPlat(it.buy_max)}
                          </Show>
                        </td>
                        {/* Max Buy Price */}
                        <td class="py-3.5 px-4 text-right font-mono text-[13px] text-teal-400/90 font-semibold">
                          <Show when={it.buy_max_max_rank != null} fallback={<span class="text-slate-600">—</span>}>
                            {fmtPlat(it.buy_max_max_rank)}
                          </Show>
                        </td>
                        {/* Estimated Value (Base Rank) */}
                        <td class="py-3.5 px-4 text-right font-mono text-[13px] text-emerald-400 font-extrabold">
                          <Show when={it.estimated_value != null} fallback={<span class="text-slate-600">—</span>}>
                            {fmtPlat(it.estimated_value)}
                          </Show>
                        </td>
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
          </Show>
        </Show>
      </Card>
    </div>
  );
}
