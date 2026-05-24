import { For, Show } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, fmtInt } from "../lib/format";

export default function Dashboard() {
  const health = createQuery(() => ({
    queryKey: keys.healthz(),
    queryFn:  fetchers.healthz,
    refetchInterval: 5_000,
  }));
  const wtb = createQuery(() => ({
    queryKey: keys.meWtbMatches(15),
    queryFn:  () => fetchers.meWtbMatches(15),
  }));
  const sets = createQuery(() => ({
    queryKey: keys.meSetsProfit(10),
    queryFn:  () => fetchers.meSetsProfit(10),
  }));
  const nudges = createQuery(() => ({
    queryKey: keys.meRelistNudges(),
    queryFn:  fetchers.meRelistNudges,
  }));

  return (
    <div class="space-y-6">
      <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="Health">
          <div
            class="text-2xl font-semibold"
            classList={{
              "text-emerald-400": health.data?.ok === true,
              "text-rose-400": health.data?.ok === false,
              "text-slate-400": !health.data,
            }}
          >
            {health.isLoading ? "…" : health.data?.ok ? "online" : "offline"}
          </div>
        </Card>
        <Card title="WFM user">
          <div class="text-xl font-mono">{health.data?.wfm_username ?? "—"}</div>
        </Card>
        <Card title="AlecaFrame">
          <div class="text-xl font-mono">v{health.data?.aleca_version ?? "—"}</div>
        </Card>
      </section>

      <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title="Top WTB matches" subtitle="Buyers asking for what you own (≥15p)">
          <Show when={!wtb.isLoading} fallback={<div class="text-slate-500">Loading…</div>}>
            <Show
              when={(wtb.data?.items ?? []).length > 0}
              fallback={<EmptyState title="No live WTB matches" hint="Lower min_offer or come back later." />}
            >
              <ul class="space-y-2">
                <For each={wtb.data!.items.slice(0, 5)}>
                  {(m) => (
                    <li class="flex items-center justify-between gap-2 text-sm">
                      <div>
                        <div class="text-slate-100">{m.item_name}</div>
                        <div class="text-xs text-slate-500 font-mono">
                          {m.buyer} · {m.buyer_status} · rep {fmtInt(m.buyer_reputation)}
                        </div>
                      </div>
                      <Badge variant="good">{fmtPlat(m.offer_price)}</Badge>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </Show>
        </Card>

        <Card title="Top set profits" subtitle="Buyable sets with margin ≥10p">
          <Show when={!sets.isLoading} fallback={<div class="text-slate-500">Loading…</div>}>
            <Show
              when={(sets.data?.items ?? []).length > 0}
              fallback={<EmptyState title="No profitable sets" hint="Inventory + market mix doesn't open a gap right now." />}
            >
              <ul class="space-y-2">
                <For each={sets.data!.items.slice(0, 5)}>
                  {(s) => (
                    <li class="flex items-center justify-between gap-2 text-sm">
                      <div class="text-slate-100">{s.set_name}</div>
                      <Badge variant="good">+{fmtPlat(s.profit)}</Badge>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </Show>
        </Card>

        <Card title="Re-list nudges" subtitle="Listings off the top-5 / below median">
          <Show when={!nudges.isLoading} fallback={<div class="text-slate-500">Loading…</div>}>
            <Show
              when={(nudges.data?.items ?? []).length > 0}
              fallback={<EmptyState title="All competitive" hint="Your listings are still in the top of the book." />}
            >
              <ul class="space-y-2">
                <For each={nudges.data!.items.slice(0, 5)}>
                  {(n) => (
                    <li class="text-sm">
                      <div class="flex items-center justify-between">
                        <span class="text-slate-100">{n.item_name}</span>
                        <span class="font-mono text-slate-300">{fmtPlat(n.your_price)}</span>
                      </div>
                      <div class="text-xs text-amber-300">{n.suggestion}</div>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </Show>
        </Card>
      </section>
    </div>
  );
}
