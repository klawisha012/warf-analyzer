import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import StatTile from "../components/StatTile";
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
  const totalQty = createMemo(() =>
    filtered().reduce((sum, it) => sum + (it.count ?? 0), 0),
  );

  useSlugChannel(() => filtered().map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      <PageHeader
        title={t("primeParts.title")}
        actions={
          <div class="flex flex-wrap items-center gap-3">
            <label class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sub">
              {t("primeParts.minQty")}
              <input
                type="number"
                min={1}
                value={minCount()}
                onInput={(e) => setMinCount(Math.max(1, +e.currentTarget.value || 1))}
                class="field w-16 text-center num"
              />
            </label>
            <input
              type="search"
              class="field sm:w-56"
              placeholder={t("common.filter")}
              value={q()}
              onInput={(e) => setQ(e.currentTarget.value)}
            />
          </div>
        }
      />

      <section class="grid grid-cols-1 sm:grid-cols-3 gap-[18px]">
        <StatTile label={t("common.value")} positive unit={t("common.plat")} value={<span class="num">{fmtPlat(totalValue())}</span>} />
        <StatTile label={t("common.unique")} value={<span class="num">{filtered().length}</span>} />
        <StatTile label={t("common.totalQty")} value={<span class="num">{totalQty()}</span>} />
      </section>

      <div class="surface overflow-hidden">
        <Show
          when={!parts.isLoading}
          fallback={
            <div class="flex flex-col items-center justify-center py-16 gap-3">
              <div class="w-8 h-8 rounded-full border-2 border-brand/20 border-t-brand-soft animate-spin"></div>
              <span class="text-xs uppercase tracking-widest text-dim animate-pulse">{t("common.loading")}</span>
            </div>
          }
        >
          <Show
            when={filtered().length > 0}
            fallback={<EmptyState title={t("primeParts.empty")} hint={t("primeParts.emptyHint")} />}
          >
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-line text-left">
                    <th class="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-sub">{t("primeParts.col.item")}</th>
                    <th class="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-sub text-right">{t("primeParts.col.qty")}</th>
                    <th class="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-sub text-right">{t("primeParts.col.sell")}</th>
                    <th class="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-sub text-right">{t("primeParts.col.buyMax")}</th>
                    <th class="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-sub text-right">{t("primeParts.col.estValue")}</th>
                  </tr>
                </thead>
                <tbody>
                  <For each={filtered()}>{(it) => <ItemRow item={it} />}</For>
                </tbody>
              </table>
            </div>
          </Show>
        </Show>
      </div>
    </div>
  );
}
