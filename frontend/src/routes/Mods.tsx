import { For, Show, createSignal, createMemo, type JSX } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import StatTile from "../components/StatTile";
import EmptyState from "../components/EmptyState";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, fmtInt } from "../lib/format";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function Mods() {
  const [minCount, setMinCount] = createSignal(1);
  const [q, setQ] = createSignal("");
  const [sortBy, setSortBy] = createSignal<string>("est_value");
  const [sortDir, setSortDir] = createSignal<"asc" | "desc">("desc");

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

  const toggleSort = (field: string) => {
    if (sortBy() === field) setSortDir(sortDir() === "asc" ? "desc" : "asc");
    else { setSortBy(field); setSortDir("desc"); }
  };

  const Th = (p: { field: string; label: string; align?: "right" }) => (
    <th
      class="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-sub cursor-pointer hover:text-brand-soft transition-colors select-none"
      classList={{ "text-right": p.align === "right" }}
      onClick={() => toggleSort(p.field)}
    >
      <div class="flex items-center gap-1" classList={{ "justify-end": p.align === "right" }}>
        {p.label}
        <Show when={sortBy() === p.field}><span class="text-[10px] text-brand-soft">{sortDir() === "asc" ? "▲" : "▼"}</span></Show>
      </div>
    </th>
  );

  const Cell = (p: { v: number | null | undefined; class?: string }): JSX.Element => (
    <td class={`py-3.5 px-4 text-right num text-[13px] ${p.class ?? "text-sub"}`}>
      <Show when={p.v != null} fallback={<span class="text-dim">—</span>}>{fmtPlat(p.v)}</Show>
    </td>
  );

  return (
    <div class="space-y-6">
      <PageHeader
        title={t("mods.title")}
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
        <StatTile label={t("mods.portfolioTitle")} positive unit={t("common.plat")} value={<span class="num">{fmtPlat(totalValue())}</span>} />
        <StatTile label={t("common.unique")} value={<span class="num">{filtered().length}</span>} />
        <StatTile label={t("common.totalQty")} value={<span class="num">{totalQty()}</span>} />
      </section>

      <div class="surface overflow-hidden">
        <Show
          when={!mods.isLoading}
          fallback={
            <div class="flex flex-col items-center justify-center py-16 gap-3">
              <div class="w-8 h-8 rounded-full border-2 border-brand/20 border-t-brand-soft animate-spin"></div>
              <span class="text-xs uppercase tracking-widest text-dim animate-pulse">{t("common.loading")}</span>
            </div>
          }
        >
          <Show when={sorted().length > 0} fallback={<EmptyState title={t("common.notFound")} hint={t("common.notFoundHint")} />}>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="border-b border-line text-left">
                    <Th field="name" label="Mod" />
                    <Th field="count" label={t("primeParts.col.qty")} align="right" />
                    <Th field="sell_min" label="Sell (0)" align="right" />
                    <Th field="sell_min_max_rank" label="Sell (Max)" align="right" />
                    <Th field="buy_max" label="Buy (0)" align="right" />
                    <Th field="buy_max_max_rank" label="Buy (Max)" align="right" />
                    <Th field="est_value" label={t("primeParts.col.estValue")} align="right" />
                  </tr>
                </thead>
                <tbody>
                  <For each={sorted()}>
                    {(it) => (
                      <tr class="border-b border-line hover:bg-white/[0.03] transition-colors duration-200 group">
                        <td class="py-3.5 px-4">
                          <div class="text-fg font-semibold tracking-tight text-[13px] group-hover:text-brand-soft transition-colors">
                            {it.name}
                            <span class="text-[9px] text-dim num ml-2 px-1.5 py-0.5 rounded bg-surface2 border border-line uppercase tracking-widest">R{it.max_rank}</span>
                          </div>
                          <Show when={it.slug}>
                            <a href={`https://warframe.market/items/${it.slug}`} target="_blank" class="text-[10px] text-dim hover:text-brand-soft tracking-wide inline-flex items-center gap-1 mt-0.5 transition-colors">{it.slug}</a>
                          </Show>
                        </td>
                        <td class="py-3.5 px-4 text-right num text-[13px] text-sub">{fmtInt(it.count)}</td>
                        <Cell v={it.sell_min} class="text-fg font-semibold" />
                        <Cell v={it.sell_min_max_rank} class="text-mint font-bold" />
                        <Cell v={it.buy_max} class="text-sub" />
                        <Cell v={it.buy_max_max_rank} class="text-cyan" />
                        <Cell v={it.estimated_value} class="text-mint font-bold" />
                      </tr>
                    )}
                  </For>
                </tbody>
              </table>
            </div>
          </Show>
        </Show>
      </div>
    </div>
  );
}
