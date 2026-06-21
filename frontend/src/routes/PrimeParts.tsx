import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import StatTile from "../components/StatTile";
import EmptyState from "../components/EmptyState";
import ValuationCard from "../components/ValuationCard";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, fmtInt } from "../lib/format";
import { priceFor } from "../lib/priceStore";
import { useItemThumbs } from "../lib/itemImages";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function PrimeParts() {
  const [minCount, setMinCount] = createSignal(1);
  const [q, setQ] = createSignal("");
  const thumbOf = useItemThumbs();

  const parts = createQuery(() => ({
    queryKey: keys.mePrimeParts(minCount()),
    queryFn:  () => fetchers.mePrimeParts(minCount()),
  }));

  const filtered = createMemo(() => {
    const needle = q().toLowerCase().trim();
    const all = parts.data?.items ?? [];
    return needle ? all.filter((x) => x.name.toLowerCase().includes(needle)) : all;
  });

  const totalValue = createMemo(() => filtered().reduce((s, it) => s + (it.estimated_value ?? 0), 0));
  const totalQty = createMemo(() => filtered().reduce((s, it) => s + (it.count ?? 0), 0));

  useSlugChannel(() => filtered().map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      <PageHeader
        title={t("primeParts.title")}
        actions={
          <div class="flex flex-wrap items-center gap-3">
            <label class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sub">
              {t("primeParts.minQty")}
              <input type="number" min={1} value={minCount()} onInput={(e) => setMinCount(Math.max(1, +e.currentTarget.value || 1))} class="field w-16 text-center num" />
            </label>
            <input type="search" class="field sm:w-56" placeholder={t("common.filter")} value={q()} onInput={(e) => setQ(e.currentTarget.value)} />
          </div>
        }
      />

      <section class="grid grid-cols-1 sm:grid-cols-3 gap-[18px]">
        <StatTile label={t("common.value")} positive unit={t("common.plat")} value={<span class="num">{fmtPlat(totalValue())}</span>} />
        <StatTile label={t("common.unique")} value={<span class="num">{filtered().length}</span>} />
        <StatTile label={t("common.totalQty")} value={<span class="num">{totalQty()}</span>} />
      </section>

      <Show
        when={!parts.isLoading}
        fallback={
          <div class="surface flex flex-col items-center justify-center py-16 gap-3">
            <div class="w-8 h-8 rounded-full border-2 border-brand/20 border-t-brand-soft animate-spin"></div>
            <span class="text-xs uppercase tracking-widest text-dim animate-pulse">{t("common.loading")}</span>
          </div>
        }
      >
        <Show when={filtered().length > 0} fallback={<EmptyState title={t("primeParts.empty")} hint={t("primeParts.emptyHint")} />}>
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <For each={filtered()}>
              {(it) => {
                const live = () => priceFor(it.slug);
                const sell = () => live()?.sell_min ?? it.sell_min;
                const buy = () => live()?.buy_max ?? it.buy_max;
                const est = () => {
                  const s = sell();
                  return s != null && it.count != null ? s * it.count : it.estimated_value;
                };
                return (
                  <ValuationCard
                    name={it.name}
                    slug={it.slug}
                    thumb={thumbOf(it.slug)}
                    stats={[
                      { label: t("primeParts.col.qty"), value: fmtInt(it.count), tone: "fg" },
                      { label: t("primeParts.col.sell"), value: fmtPlat(sell()), tone: "fg" },
                      { label: t("primeParts.col.buyMax"), value: fmtPlat(buy()), tone: "cyan" },
                    ]}
                    primary={{ label: t("primeParts.col.estValue"), value: fmtPlat(est()) }}
                  />
                );
              }}
            </For>
          </div>
        </Show>
      </Show>
    </div>
  );
}
