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

  useSlugChannel(() => {
    const out = new Set<string>();
    for (const m of wtb.data?.items ?? []) if (m.slug) out.add(m.slug);
    for (const n of nudges.data?.items ?? []) if (n.slug) out.add(n.slug);
    for (const s of sets.data?.items ?? []) {
      if (s.set_slug) out.add(s.set_slug);
      for (const p of Object.keys(s.missing_parts ?? {})) out.add(p);
    }
    return Array.from(out);
  });

  return (
    <div class="space-y-6">
      {/* High-Tech Diagnostic Telemetry Cards */}
      <section class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title={t("dashboard.healthTitle")} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-emerald-500/[0.02] blur-xl group-hover:bg-emerald-500/[0.04] transition-all duration-500"></div>
          <div class="flex items-center gap-3">
            <span 
              class="w-3.5 h-3.5 rounded-full relative flex"
              classList={{
                "bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.6)]": health.data?.ok === true,
                "bg-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.6)] animate-pulse": health.data?.ok === false,
                "bg-slate-500": !health.data,
              }}
            >
              {health.data?.ok && <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>}
            </span>
            <div
              class="text-2xl font-bold tracking-tight"
              classList={{
                "text-emerald-400": health.data?.ok === true,
                "text-rose-400": health.data?.ok === false,
                "text-slate-400": !health.data,
              }}
            >
              {health.isLoading ? "…" : health.data?.ok ? t("common.online") : t("common.offline")}
            </div>
          </div>
        </Card>
        
        <Card title={t("dashboard.wfmUserTitle")} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-teal-500/[0.02] blur-xl group-hover:bg-teal-500/[0.04] transition-all duration-500"></div>
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-teal-400/80" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
            </svg>
            <div class="text-xl font-bold font-mono tracking-wide text-teal-300">
              {health.data?.wfm_username ?? t("common.dash")}
            </div>
          </div>
        </Card>
        
        <Card title={t("dashboard.alecaTitle")} class="relative overflow-hidden group">
          <div class="absolute -right-6 -bottom-6 w-24 h-24 rounded-full bg-indigo-500/[0.02] blur-xl group-hover:bg-indigo-500/[0.04] transition-all duration-500"></div>
          <div class="flex items-center gap-2">
            <svg class="w-5 h-5 text-indigo-400/80" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"></path>
            </svg>
            <div class="text-xl font-bold font-mono tracking-wide text-indigo-300">
              v{health.data?.aleca_version ?? t("common.dash")}
            </div>
          </div>
        </Card>
      </section>

      {/* Main Lists & Telemetries Grid */}
      <section class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* WTB Matches Card */}
        <Card title={t("dashboard.wtbTitle")} subtitle={t("dashboard.wtbSubtitle")} class="shadow-md">
          <Show when={!wtb.isLoading} fallback={<div class="text-slate-500 text-sm font-medium animate-pulse">{t("common.loading")}</div>}>
            <Show
              when={(wtb.data?.items ?? []).length > 0}
              fallback={<EmptyState title={t("dashboard.wtbEmpty")} hint={t("dashboard.wtbEmptyHint")} />}
            >
              <ul class="space-y-3">
                <For each={wtb.data!.items.slice(0, 5)}>
                  {(m) => (
                    <li class="flex items-center justify-between gap-3 p-3.5 rounded-2xl bg-white/[0.01] hover:bg-white/[0.02] border border-white/[0.02] hover:border-white/[0.05] transition-all duration-300 hover:-translate-y-0.5">
                      <div class="min-w-0">
                        <div class="text-[14px] font-semibold text-slate-100 truncate">{m.item_name}</div>
                        <div class="text-[11px] text-slate-500 font-mono flex items-center gap-1.5 mt-0.5">
                          <span class="text-teal-400 font-bold">{m.buyer}</span>
                          <span>·</span>
                          <span class="px-1.5 py-0.2 rounded bg-slate-950/40 text-[9px] uppercase border border-slate-800/50">{m.buyer_status}</span>
                          <span>·</span>
                          <span>{t("dashboard.rep")} {fmtInt(m.buyer_reputation)}</span>
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

        {/* Profit Sets Card */}
        <Card title={t("dashboard.setsTitle")} subtitle={t("dashboard.setsSubtitle")} class="shadow-md">
          <Show when={!sets.isLoading} fallback={<div class="text-slate-500 text-sm font-medium animate-pulse">{t("common.loading")}</div>}>
            <Show
              when={(sets.data?.items ?? []).length > 0}
              fallback={<EmptyState title={t("dashboard.setsEmpty")} hint={t("dashboard.setsEmptyHint")} />}
            >
              <ul class="space-y-3">
                <For each={sets.data!.items.slice(0, 5)}>
                  {(s) => (
                    <li class="flex items-center justify-between gap-3 p-3.5 rounded-2xl bg-white/[0.01] hover:bg-white/[0.02] border border-white/[0.02] hover:border-white/[0.05] transition-all duration-300 hover:-translate-y-0.5">
                      <div class="text-[14px] font-semibold text-slate-100 truncate">{s.set_name}</div>
                      <Badge variant="good">+{fmtPlat(s.profit)}</Badge>
                    </li>
                  )}
                </For>
              </ul>
            </Show>
          </Show>
        </Card>

        {/* Relist Nudges Card */}
        <Card title={t("dashboard.nudgesTitle")} subtitle={t("dashboard.nudgesSubtitle")} class="shadow-md">
          <Show when={!nudges.isLoading} fallback={<div class="text-slate-500 text-sm font-medium animate-pulse">{t("common.loading")}</div>}>
            <Show
              when={(nudges.data?.items ?? []).length > 0}
              fallback={<EmptyState title={t("dashboard.nudgesEmpty")} hint={t("dashboard.nudgesEmptyHint")} />}
            >
              <ul class="space-y-3">
                <For each={nudges.data!.items.slice(0, 5)}>
                  {(n) => (
                    <li class="p-3.5 rounded-2xl bg-white/[0.01] hover:bg-white/[0.02] border border-white/[0.02] hover:border-white/[0.05] transition-all duration-300 hover:-translate-y-0.5">
                      <div class="flex items-center justify-between gap-3">
                        <span class="text-[14px] font-semibold text-slate-100 truncate">{n.item_name}</span>
                        <span class="font-mono text-xs font-bold text-slate-400 bg-slate-950/40 px-2 py-0.5 rounded-lg border border-slate-800/40">{fmtPlat(n.your_price)}</span>
                      </div>
                      <div class="text-[11px] font-medium text-amber-300 flex items-center gap-1.5 mt-2 bg-amber-500/5 border border-amber-500/10 px-2.5 py-1 rounded-xl">
                        <svg class="w-3.5 h-3.5 text-amber-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
                        </svg>
                        <span class="truncate">{n.suggestion}</span>
                      </div>
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
