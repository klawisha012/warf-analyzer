import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import SetRowComp from "../components/SetRow";
import { fetchers, keys } from "../api/queries";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function Sets() {
  const [minMargin, setMinMargin] = createSignal(0);

  const sets = createQuery(() => ({
    queryKey: keys.meSetsProfit(minMargin()),
    queryFn:  () => fetchers.meSetsProfit(minMargin()),
  }));

  // Subscribe to every slug touched by the visible sets — set slug itself
  // plus every missing-part slug. On push we update the global price store
  // AND invalidate this query so the recomputed profit is correct.
  const visibleSlugs = createMemo(() => {
    const items = sets.data?.items ?? [];
    const out = new Set<string>();
    for (const r of items) {
      if (r.set_slug) out.add(r.set_slug);
      for (const partSlug of Object.keys(r.missing_parts ?? {})) out.add(partSlug);
      for (const partSlug of Object.keys(r.owned_parts ?? {})) out.add(partSlug);
    }
    return Array.from(out);
  });
  useSlugChannel(visibleSlugs);

  return (
    <div class="space-y-6">
      {/* Telemetry Filter Toolbar */}
      <header class="flex flex-wrap items-center justify-between gap-4 bg-slate-900/30 p-2.5 rounded-2xl border border-white/[0.02] backdrop-blur-md">
        <h1 class="text-xl font-bold tracking-tight text-slate-100 px-2 font-sans flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"></span>
          {t("sets.title")}
        </h1>
        {/* Min Margin Calibration Control */}
        <label class="text-xs font-semibold text-slate-400 flex items-center gap-2 font-mono uppercase tracking-wider bg-slate-950/60 p-1.5 rounded-xl border border-white/[0.02] px-3">
          {t("sets.minProfit")}
          <input
            type="number"
            min={0}
            step={1}
            value={minMargin()}
            onInput={(e) => setMinMargin(Math.max(0, +e.currentTarget.value || 0))}
            class="w-16 text-center py-0.5 rounded-md bg-slate-900 border border-white/[0.06] text-emerald-400 focus:outline-none focus:border-emerald-500/40 text-xs font-bold font-mono"
          />
        </label>
      </header>

      <Show
        when={!sets.isLoading}
        fallback={
          <Card class="flex items-center justify-center py-16">
            <div class="flex flex-col items-center gap-3">
              <div class="w-8 h-8 rounded-full border-2 border-emerald-500/20 border-t-emerald-400 animate-spin"></div>
              <span class="text-xs font-mono uppercase tracking-widest text-slate-500 animate-pulse">{t("common.loading")}</span>
            </div>
          </Card>
        }
      >
        <Show
          when={(sets.data?.items ?? []).length > 0}
          fallback={
            <EmptyState
              title={t("sets.empty")}
              hint={t("sets.emptyHint")}
            />
          }
        >
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <For each={sets.data!.items}>{(row) => <SetRowComp row={row} />}</For>
          </div>
        </Show>
      </Show>
    </div>
  );
}
