import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import StatTile from "../components/StatTile";
import EmptyState from "../components/EmptyState";
import ValuationCard from "../components/ValuationCard";
import { fetchers, keys } from "../api/queries";
import { fmtPlat } from "../lib/format";
import { priceFor } from "../lib/priceStore";
import { useItemThumbs } from "../lib/itemImages";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

const SORT_FIELDS = [
  { field: "est_value",          label: "Est. value" },
  { field: "name",               label: "Name" },
  { field: "count",              label: "Qty" },
  { field: "sell_min",           label: "Sell (0)" },
  { field: "sell_min_max_rank",  label: "Sell (Max)" },
  { field: "buy_max",            label: "Buy (0)" },
  { field: "buy_max_max_rank",   label: "Buy (Max)" },
] as const;

export default function Mods() {
  const [minCount, setMinCount] = createSignal(1);
  const [q, setQ] = createSignal("");
  const [sortBy, setSortBy] = createSignal<string>("est_value");
  const [sortDir, setSortDir] = createSignal<"asc" | "desc">("desc");
  const thumbOf = useItemThumbs();

  const mods = createQuery(() => ({
    queryKey: keys.meMods(minCount()),
    queryFn:  () => fetchers.meMods(minCount()),
  }));

  const filtered = createMemo(() => {
    const needle = q().toLowerCase().trim();
    const all = mods.data?.items ?? [];
    return needle ? all.filter((x) => x.name.toLowerCase().includes(needle)) : all;
  });

  const sorted = createMemo(() => {
    const items = [...filtered()];
    const dir = sortDir() === "asc" ? 1 : -1;
    const field = sortBy();
    items.sort((a, b) => {
      if (field === "name") return a.name.toLowerCase().localeCompare(b.name.toLowerCase()) * dir;
      const pick = (x: typeof a): number =>
        field === "count" ? (x.count ?? 0)
        : field === "sell_min" ? (x.sell_min ?? 0)
        : field === "sell_min_max_rank" ? (x.sell_min_max_rank ?? 0)
        : field === "buy_max" ? (x.buy_max ?? 0)
        : field === "buy_max_max_rank" ? (x.buy_max_max_rank ?? 0)
        : (x.estimated_value ?? 0);
      const va = pick(a), vb = pick(b);
      return (va > vb ? 1 : va < vb ? -1 : 0) * dir;
    });
    return items;
  });

  const totalValue = createMemo(() => filtered().reduce((s, it) => s + (it.estimated_value ?? 0), 0));
  const totalQty = createMemo(() => filtered().reduce((s, it) => s + (it.count ?? 0), 0));

  useSlugChannel(() => sorted().map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      <PageHeader
        title={t("mods.title")}
        actions={
          <div class="flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-1.5">
              <select value={sortBy()} onChange={(e) => setSortBy(e.currentTarget.value)} class="field w-auto pr-2">
                <For each={SORT_FIELDS}>{(f) => <option value={f.field}>{f.label}</option>}</For>
              </select>
              <button
                type="button"
                class="btn-ghost px-3"
                title={sortDir() === "asc" ? "Ascending" : "Descending"}
                onClick={() => setSortDir(sortDir() === "asc" ? "desc" : "asc")}
              >
                {sortDir() === "asc" ? "↑" : "↓"}
              </button>
            </div>
            <label class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-sub">
              {t("primeParts.minQty")}
              <input type="number" min={1} value={minCount()} onInput={(e) => setMinCount(Math.max(1, +e.currentTarget.value || 1))} class="field w-16 text-center num" />
            </label>
            <input type="search" class="field sm:w-48" placeholder={t("common.filter")} value={q()} onInput={(e) => setQ(e.currentTarget.value)} />
          </div>
        }
      />

      <section class="grid grid-cols-1 sm:grid-cols-3 gap-[18px]">
        <StatTile label={t("mods.portfolioTitle")} positive unit={t("common.plat")} value={<span class="num">{fmtPlat(totalValue())}</span>} />
        <StatTile label={t("common.unique")} value={<span class="num">{filtered().length}</span>} />
        <StatTile label={t("common.totalQty")} value={<span class="num">{totalQty()}</span>} />
      </section>

      <Show
        when={!mods.isLoading}
        fallback={
          <div class="surface flex flex-col items-center justify-center py-16 gap-3">
            <div class="w-8 h-8 rounded-full border-2 border-brand/20 border-t-brand-soft animate-spin"></div>
            <span class="text-xs uppercase tracking-widest text-dim animate-pulse">{t("common.loading")}</span>
          </div>
        }
      >
        <Show when={sorted().length > 0} fallback={<EmptyState title={t("common.notFound")} hint={t("common.notFoundHint")} />}>
          <div class="grid grid-cols-1 xl:grid-cols-2 gap-3">
            <For each={sorted()}>
              {(it) => {
                const live = () => priceFor(it.slug);
                const sell = () => live()?.sell_min ?? it.sell_min;
                const buy = () => live()?.buy_max ?? it.buy_max;
                return (
                  <ValuationCard
                    name={it.name}
                    slug={it.slug}
                    thumb={thumbOf(it.slug)}
                    rank={it.max_rank}
                    stats={[
                      { label: "Sell 0", value: fmtPlat(sell()), tone: "fg" },
                      { label: "Sell Max", value: fmtPlat(it.sell_min_max_rank), tone: "mint" },
                      { label: "Buy 0", value: fmtPlat(buy()), tone: "sub" },
                      { label: "Buy Max", value: fmtPlat(it.buy_max_max_rank), tone: "cyan" },
                    ]}
                    primary={{ label: t("primeParts.col.estValue"), value: fmtPlat(it.estimated_value) }}
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
