import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import ItemCard from "../components/ItemCard";
import { fetchers, keys } from "../api/queries";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

const SLOTS = ["warframe", "primary", "secondary", "melee", "all"] as const;
type Slot = (typeof SLOTS)[number];

export default function Inventory() {
  const [slot, setSlot] = createSignal<Slot>("warframe");
  const [q, setQ] = createSignal("");
  const [limit] = createSignal(50);

  const items = createQuery(() => ({
    queryKey: keys.meInventory(slot(), limit()),
    queryFn:  () => fetchers.meInventory(slot(), limit()),
  }));

  const filtered = createMemo(() => {
    const needle = q().toLowerCase().trim();
    const all = items.data?.items ?? [];
    return needle ? all.filter((x) => x.name.toLowerCase().includes(needle)) : all;
  });

  // Subscribe to every visible row so a push for any visible slug updates
  // the price store and re-renders that card.
  useSlugChannel(() => filtered().map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      {/* Sci-Fi Navigation & Filter Panel */}
      <header class="flex flex-wrap items-center justify-between gap-4 bg-slate-900/30 p-2.5 rounded-2xl border border-white/[0.02] backdrop-blur-md">
        <h1 class="text-xl font-bold tracking-tight text-slate-100 px-2 font-sans flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]"></span>
          {t("inventory.title")}
        </h1>
        <div class="flex flex-wrap items-center gap-3">
          {/* Segmented Category Buttons */}
          <div class="flex bg-slate-950/60 p-1 rounded-xl border border-white/[0.02] gap-1">
            <For each={SLOTS}>
              {(s) => (
                <button
                  type="button"
                  onClick={() => setSlot(s)}
                  class="px-3.5 py-1.5 text-[10px] font-bold uppercase tracking-wider rounded-lg transition-all duration-300 font-mono"
                  classList={{
                    "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-[0_0_12px_rgba(16,185,129,0.1)]": slot() === s,
                    "text-slate-400 hover:text-slate-200 border border-transparent": slot() !== s,
                  }}
                >
                  {t(`inventory.slot.${s}`)}
                </button>
              )}
            </For>
          </div>

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

      {/* Main Grid View */}
      <Show
        when={!items.isLoading}
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
          when={filtered().length > 0}
          fallback={<EmptyState title={t("inventory.empty")} hint={t("inventory.emptyHint")} />}
        >
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <For each={filtered()}>{(it) => <ItemCard item={it} />}</For>
          </div>
        </Show>
      </Show>
    </div>
  );
}
