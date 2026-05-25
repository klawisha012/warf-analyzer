import { For, Show, createSignal } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import SetRowComp from "../components/SetRow";
import { fetchers, keys } from "../api/queries";
import { t } from "../i18n";

export default function Sets() {
  const [minMargin, setMinMargin] = createSignal(0);

  const sets = createQuery(() => ({
    queryKey: keys.meSetsProfit(minMargin()),
    queryFn:  () => fetchers.meSetsProfit(minMargin()),
  }));

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3 flex-wrap">
        <h1 class="text-2xl font-bold mr-auto">{t("sets.title")}</h1>
        <label class="text-sm text-slate-400 flex items-center gap-2">
          {t("sets.minProfit")}
          <input
            type="number"
            min={0}
            step={1}
            value={minMargin()}
            onInput={(e) => setMinMargin(Math.max(0, +e.currentTarget.value || 0))}
            class="w-20 px-2 py-1 text-sm rounded-md bg-slate-900 border border-slate-800 text-slate-100"
          />
        </label>
      </header>

      <Show
        when={!sets.isLoading}
        fallback={<Card><div class="text-slate-500">{t("common.loading")}</div></Card>}
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
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <For each={sets.data!.items}>{(row) => <SetRowComp row={row} />}</For>
          </div>
        </Show>
      </Show>
    </div>
  );
}
