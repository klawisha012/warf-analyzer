import { For, Show } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, fmtInt } from "../lib/format";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

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

  useSlugChannel(() => [
    ...(wtb.data?.items ?? []).map((m) => m.slug),
    ...(nudges.data?.items ?? []).map((n) => n.slug),
  ].filter(Boolean) as string[]);

  return (
    <div class="space-y-6">
      <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title={t("dashboard.healthTitle")}>
          <div
            class="text-2xl font-semibold"
            classList={{
              "text-emerald-400": health.data?.ok === true,
              "text-rose-400": health.data?.ok === false,
              "text-slate-400": !health.data,
            }}
          >
            {health.isLoading ? "…" : health.data?.ok ? t("common.online") : t("common.offline")}
          </div>
        </Card>
        <Card title={t("dashboard.wfmUserTitle")}>
          <div class="text-xl font-mono">{health.data?.wfm_username ?? t("common.dash")}</div>
        </Card>
        <Card title={t("dashboard.alecaTitle")}>
          <div class="text-xl font-mono">v{health.data?.aleca_version ?? t("common.dash")}</div>
        </Card>
      </section>

      <section class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card title={t("dashboard.wtbTitle")} subtitle={t("dashboard.wtbSubtitle")}>
          <Show when={!wtb.isLoading} fallback={<div class="text-slate-500">{t("common.loading")}</div>}>
            <Show
              when={(wtb.data?.items ?? []).length > 0}
              fallback={<EmptyState title={t("dashboard.wtbEmpty")} hint={t("dashboard.wtbEmptyHint")} />}
            >
              <ul class="space-y-2">
                <For each={wtb.data!.items.slice(0, 5)}>
                  {(m) => (
                    <li class="flex items-center justify-between gap-2 text-sm">
                      <div>
                        <div class="text-slate-100">{m.item_name}</div>
                        <div class="text-xs text-slate-500 font-mono">
                          {m.buyer} · {m.buyer_status} · {t("dashboard.rep")} {fmtInt(m.buyer_reputation)}
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

        <Card title={t("dashboard.setsTitle")} subtitle={t("dashboard.setsSubtitle")}>
          <Show when={!sets.isLoading} fallback={<div class="text-slate-500">{t("common.loading")}</div>}>
            <Show
              when={(sets.data?.items ?? []).length > 0}
              fallback={<EmptyState title={t("dashboard.setsEmpty")} hint={t("dashboard.setsEmptyHint")} />}
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

        <Card title={t("dashboard.nudgesTitle")} subtitle={t("dashboard.nudgesSubtitle")}>
          <Show when={!nudges.isLoading} fallback={<div class="text-slate-500">{t("common.loading")}</div>}>
            <Show
              when={(nudges.data?.items ?? []).length > 0}
              fallback={<EmptyState title={t("dashboard.nudgesEmpty")} hint={t("dashboard.nudgesEmptyHint")} />}
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
