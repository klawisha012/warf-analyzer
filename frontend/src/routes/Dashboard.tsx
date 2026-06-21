import { For, Show } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import PageHeader from "../components/PageHeader";
import StatTile from "../components/StatTile";
import EmptyState from "../components/EmptyState";
import ItemThumb from "../components/ItemThumb";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, fmtInt } from "../lib/format";
import { useItemThumbs } from "../lib/itemImages";
import { useSlugChannel } from "../hooks/useSlugChannel";
import { t } from "../i18n";

export default function Dashboard() {
  const thumbOf = useItemThumbs();
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
    <div class="space-y-7">
      <PageHeader
        title={t("nav.dashboard")}
        pulse
        eyebrow={<span>warframe.market · {health.data?.ok ? t("common.online") : t("common.offline")}</span>}
      />

      {/* Key metrics */}
      <section class="grid grid-cols-1 sm:grid-cols-3 gap-[18px]">
        <StatTile
          label={t("dashboard.healthTitle")}
          positive={health.data?.ok === true}
          icon={<svg viewBox="0 0 24 24" fill="none"><path d="M3 12h4l2 6 4-12 2 6h6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>}
          value={health.isLoading ? "…" : health.data?.ok ? t("common.online") : t("common.offline")}
        />
        <StatTile
          label={t("dashboard.wfmUserTitle")}
          icon={<svg viewBox="0 0 24 24" fill="none"><path d="M12 12a4 4 0 100-8 4 4 0 000 8z" stroke="currentColor" stroke-width="1.6"/><path d="M4 21a8 8 0 0116 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>}
          value={health.data?.wfm_username ?? t("common.dash")}
        />
        <StatTile
          label={t("dashboard.alecaTitle")}
          icon={<svg viewBox="0 0 24 24" fill="none"><path d="M3 7h18v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" stroke="currentColor" stroke-width="1.6"/><path d="M9 7V5a2 2 0 012-2h2a2 2 0 012 2v2" stroke="currentColor" stroke-width="1.6"/></svg>}
          value={`v${health.data?.aleca_version ?? t("common.dash")}`}
        />
      </section>

      {/* Lists */}
      <section class="grid grid-cols-1 lg:grid-cols-3 gap-[18px]">
        {/* WTB matches */}
        <div class="panel">
          <div class="panel-head">
            <div class="min-w-0">
              <div class="panel-title">{t("dashboard.wtbTitle")}</div>
              <div class="panel-sub">{t("dashboard.wtbSubtitle")}</div>
            </div>
          </div>
          <div class="panel-body">
            <Show when={!wtb.isLoading} fallback={<div class="p-3 text-sm text-dim animate-pulse">{t("common.loading")}</div>}>
              <Show
                when={(wtb.data?.items ?? []).length > 0}
                fallback={<EmptyState title={t("dashboard.wtbEmpty")} hint={t("dashboard.wtbEmptyHint")} />}
              >
                <For each={wtb.data!.items.slice(0, 5)}>
                  {(m) => (
                    <div class="row">
                      <ItemThumb src={thumbOf(m.slug)} name={m.item_name} size={38} />
                      <div class="item-main flex-1 min-w-0">
                        <div class="text-[14px] font-semibold text-fg truncate">{m.item_name}</div>
                        <div class="text-[11px] text-dim flex items-center gap-1.5 mt-0.5">
                          <span class="text-brand-soft font-semibold">{m.buyer}</span>
                          <span>·</span>
                          <span>{t("dashboard.rep")} {fmtInt(m.buyer_reputation)}</span>
                        </div>
                      </div>
                      <div class="flex flex-col items-end gap-1.5">
                        <span class="num font-bold text-[15px] text-fg">{fmtPlat(m.offer_price)}</span>
                        <span class={`chip ${m.buyer_status === "ingame" ? "ingame" : "online"}`}><span class="dot" />{m.buyer_status}</span>
                      </div>
                    </div>
                  )}
                </For>
              </Show>
            </Show>
          </div>
        </div>

        {/* Profitable sets */}
        <div class="panel">
          <div class="panel-head">
            <div class="min-w-0">
              <div class="panel-title">{t("dashboard.setsTitle")}</div>
              <div class="panel-sub">{t("dashboard.setsSubtitle")}</div>
            </div>
          </div>
          <div class="panel-body">
            <Show when={!sets.isLoading} fallback={<div class="p-3 text-sm text-dim animate-pulse">{t("common.loading")}</div>}>
              <Show
                when={(sets.data?.items ?? []).length > 0}
                fallback={<EmptyState title={t("dashboard.setsEmpty")} hint={t("dashboard.setsEmptyHint")} />}
              >
                <For each={sets.data!.items.slice(0, 5)}>
                  {(s) => (
                    <div class="row">
                      <ItemThumb src={thumbOf(s.set_slug)} name={s.set_name} size={38} />
                      <div class="flex-1 min-w-0 text-[14px] font-semibold text-fg truncate">{s.set_name}</div>
                      <span class="margin-pill">+{fmtPlat(s.profit)}</span>
                    </div>
                  )}
                </For>
              </Show>
            </Show>
          </div>
        </div>

        {/* Relist nudges */}
        <div class="panel">
          <div class="panel-head">
            <div class="min-w-0">
              <div class="panel-title">{t("dashboard.nudgesTitle")}</div>
              <div class="panel-sub">{t("dashboard.nudgesSubtitle")}</div>
            </div>
          </div>
          <div class="panel-body">
            <Show when={!nudges.isLoading} fallback={<div class="p-3 text-sm text-dim animate-pulse">{t("common.loading")}</div>}>
              <Show
                when={(nudges.data?.items ?? []).length > 0}
                fallback={<EmptyState title={t("dashboard.nudgesEmpty")} hint={t("dashboard.nudgesEmptyHint")} />}
              >
                <div class="px-1 py-1.5 space-y-1.5">
                  <For each={nudges.data!.items.slice(0, 5)}>
                    {(n) => (
                      <div class="flex gap-3 rounded-[10px] p-3 hover:bg-white/[0.03] transition-colors">
                        <ItemThumb src={thumbOf(n.slug)} name={n.item_name} size={38} />
                        <div class="flex-1 min-w-0">
                          <div class="flex items-center justify-between gap-3">
                            <span class="text-[14px] font-semibold text-fg truncate">{n.item_name}</span>
                            <span class="num text-xs font-semibold text-sub">{fmtPlat(n.your_price)}</span>
                          </div>
                          <div class="text-[11px] font-medium text-amber-300 flex items-center gap-1.5 mt-2">
                            <svg class="w-3.5 h-3.5 text-amber-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                            <span class="truncate">{n.suggestion}</span>
                          </div>
                        </div>
                      </div>
                    )}
                  </For>
                </div>
              </Show>
            </Show>
          </div>
        </div>
      </section>
    </div>
  );
}
