import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import ItemRow from "../components/ItemRow";
import { fetchers, keys } from "../api/queries";
import { fmtPlat } from "../lib/format";

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

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3 flex-wrap">
        <h1 class="text-2xl font-bold mr-auto">Prime parts</h1>
        <label class="text-sm text-slate-400 flex items-center gap-2">
          min&nbsp;qty
          <input
            type="number"
            min={1}
            value={minCount()}
            onInput={(e) => setMinCount(Math.max(1, +e.currentTarget.value || 1))}
            class="w-16 px-2 py-1 text-sm rounded-md bg-slate-900 border border-slate-800 text-slate-100"
          />
        </label>
        <input
          type="search"
          placeholder="Filter…"
          value={q()}
          onInput={(e) => setQ(e.currentTarget.value)}
          class="px-3 py-1 text-sm rounded-md bg-slate-900 border border-slate-800 text-slate-100 focus:outline-none focus:border-slate-600"
        />
      </header>

      <Card subtitle={`${filtered().length} rows · est. total ${fmtPlat(totalValue())}`}>
        <Show
          when={!parts.isLoading}
          fallback={<div class="text-slate-500">Loading…</div>}
        >
          <Show
            when={filtered().length > 0}
            fallback={<EmptyState title="No prime parts" hint="Lower min qty or refresh inventory." />}
          >
            <div class="overflow-auto">
              <table class="w-full text-sm">
                <thead class="text-left text-slate-400">
                  <tr class="border-b border-slate-800">
                    <th class="py-2 px-3">Item</th>
                    <th class="py-2 px-3 text-right">Qty</th>
                    <th class="py-2 px-3">Status</th>
                    <th class="py-2 px-3">Sell</th>
                    <th class="py-2 px-3 text-right">Buy max</th>
                    <th class="py-2 px-3 text-right">Est. value</th>
                  </tr>
                </thead>
                <tbody>
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
