import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import ItemCard from "../components/ItemCard";
import { fetchers, keys } from "../api/queries";
import { useSlugChannel } from "../hooks/useSlugChannel";

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

  useSlugChannel(() => filtered().slice(0, 10).map((it) => it.slug).filter(Boolean) as string[]);

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3 flex-wrap">
        <h1 class="text-2xl font-bold mr-auto">Inventory</h1>
        <div class="flex gap-1">
          <For each={SLOTS}>
            {(s) => (
              <button
                type="button"
                onClick={() => setSlot(s)}
                class="px-3 py-1 text-sm rounded-md border"
                classList={{
                  "bg-slate-800 border-slate-700 text-slate-100": slot() === s,
                  "border-slate-800 text-slate-400 hover:text-slate-200": slot() !== s,
                }}
              >
                {s}
              </button>
            )}
          </For>
        </div>
        <input
          type="search"
          placeholder="Filter…"
          value={q()}
          onInput={(e) => setQ(e.currentTarget.value)}
          class="px-3 py-1 text-sm rounded-md bg-slate-900 border border-slate-800 text-slate-100 focus:outline-none focus:border-slate-600"
        />
      </header>

      <Show
        when={!items.isLoading}
        fallback={<Card><div class="text-slate-500">Loading…</div></Card>}
      >
        <Show
          when={filtered().length > 0}
          fallback={<EmptyState title="No items" hint="Try a different slot or clear the filter." />}
        >
          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <For each={filtered()}>{(it) => <ItemCard item={it} />}</For>
          </div>
        </Show>
      </Show>
    </div>
  );
}
