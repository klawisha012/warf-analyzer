import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import EmptyState from "../components/EmptyState";
import SetRowComp from "../components/SetRow";
import { fetchers, keys } from "../api/queries";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function Sets() {
  const [minMargin, setMinMargin] = createSignal(0);

  const sets = createQuery(() => ({
    queryKey: keys.meSetsProfit(minMargin()),
    queryFn: () => fetchers.meSetsProfit(minMargin()),
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
  // eslint-disable-next-line solid/reactivity -- visibleSlugs Accessor is tracked inside useSlugChannel's createEffect
  useSlugChannel(visibleSlugs);

  return (
    <div class="space-y-6">
      <PageHeader
        title={t("sets.title")}
        actions={
          <label class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sub">
            {t("sets.minProfit")}
            <input
              type="number"
              min={0}
              step={1}
              value={minMargin()}
              onInput={(e) => setMinMargin(Math.max(0, +e.currentTarget.value || 0))}
              class="field w-20 text-center num"
            />
          </label>
        }
      />

      <Show
        when={!sets.isLoading}
        fallback={
          <div class="surface flex flex-col items-center justify-center py-16 gap-3">
            <div class="w-8 h-8 rounded-full border-2 border-brand/20 border-t-brand-soft animate-spin" />
            <span class="text-xs uppercase tracking-widest text-dim animate-pulse">
              {t("common.loading")}
            </span>
          </div>
        }
      >
        <Show
          when={(sets.data?.items ?? []).length > 0}
          fallback={<EmptyState title={t("sets.empty")} hint={t("sets.emptyHint")} />}
        >
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <For each={sets.data!.items}>{(row) => <SetRowComp row={row} />}</For>
          </div>
        </Show>
      </Show>
    </div>
  );
}
