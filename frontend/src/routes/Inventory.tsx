import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import ItemCard from "../components/ItemCard";
import PagerControl from "../components/Pager";
import { fetchers, keys } from "../api/queries";
import { createPager } from "../lib/pagination";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

const SLOTS = ["warframe", "primary", "secondary", "melee", "all"] as const;
type Slot = (typeof SLOTS)[number];

export default function Inventory() {
  const [slot, setSlot] = createSignal<Slot>("warframe");
  const [q, setQ] = createSignal("");
  const [craftOnly, setCraftOnly] = createSignal(false);
  const [limit] = createSignal(50);

  const items = createQuery(() => ({
    queryKey: keys.meInventory(slot(), limit()),
    queryFn:  () => fetchers.meInventory(slot(), limit()),
  }));

  const filtered = createMemo(() => {
    const needle = q().toLowerCase().trim();
    let all = items.data?.items ?? [];
    if (needle) all = all.filter((x) => x.name.toLowerCase().includes(needle));
    // "Used in crafting" hides final-product placeholders (no crafting use).
    if (craftOnly()) all = all.filter((x) => (x.used_in?.length ?? 0) > 0);
    return all;
  });

  const pager = createPager(filtered, 24);

  // Subscribe to every visible row so a push for any visible slug updates
  // the price store and re-renders that card.
  useSlugChannel(() => filtered().map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      <PageHeader
        title={t("inventory.title")}
        actions={
          <div class="flex flex-wrap items-center gap-3">
            <label class="flex items-center gap-2 text-xs font-medium text-sub cursor-pointer select-none">
              <input type="checkbox" checked={craftOnly()} onChange={(e) => setCraftOnly(e.currentTarget.checked)} class="accent-[var(--indigo)] w-4 h-4" />
              {t("inventory.craftOnly")}
            </label>
            <div class="seg">
              <For each={SLOTS}>
                {(s) => (
                  <button type="button" class="seg-btn" classList={{ active: slot() === s }} onClick={() => setSlot(s)}>
                    {t(`inventory.slot.${s}`)}
                  </button>
                )}
              </For>
            </div>
            <input
              type="search"
              class="field sm:w-48"
              placeholder={t("common.filter")}
              value={q()}
              onInput={(e) => setQ(e.currentTarget.value)}
            />
          </div>
        }
      />

      <Show
        when={!items.isLoading}
        fallback={
          <div class="surface flex flex-col items-center justify-center py-16 gap-3">
            <div class="w-8 h-8 rounded-full border-2 border-brand/20 border-t-brand-soft animate-spin"></div>
            <span class="text-xs uppercase tracking-widest text-dim animate-pulse">{t("common.loading")}</span>
          </div>
        }
      >
        <Show
          when={filtered().length > 0}
          fallback={<EmptyState title={t("inventory.empty")} hint={t("inventory.emptyHint")} />}
        >
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-start">
            <For each={pager.pageItems()}>{(it) => <ItemCard item={it} />}</For>
          </div>
          <PagerControl page={pager.page()} totalPages={pager.totalPages()} total={pager.total()} onPage={pager.setPage} />
        </Show>
      </Show>
    </div>
  );
}
