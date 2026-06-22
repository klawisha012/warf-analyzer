import { For, Show, createMemo, createSignal } from "solid-js";
import { createQuery, useQueryClient } from "@tanstack/solid-query";
import Card from "../components/Card";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import PageHeader from "../components/PageHeader";
import ItemThumb from "../components/ItemThumb";
import { wfmAsset } from "../lib/itemImages";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, prettySlug } from "../lib/format";
import { rivenAttrName } from "../lib/rivenAttrs";
import { useRivenAlerts } from "../hooks/useRivenAlerts";
import { alertCountByWeapon } from "../lib/rivenAlerts";
import { t, locale } from "../i18n";
import type {
  RivenAuctionRow,
  RivenOutlier,
  RivenStrategyTip,
  RivenTierStats,
  RivenTopAttribute,
  RivenWeapon,
} from "../api/types";

export default function Rivens() {
  const qc = useQueryClient();
  const [selected, setSelected] = createSignal<string | null>(null);

  const watchlist = createQuery(() => ({
    queryKey: keys.rivenWatchlist(),
    queryFn:  fetchers.rivenWatchlist,
    refetchInterval: 30_000,
  }));

  // WFM riven-capable weapons catalogue — 24h cache on the backend, so the
  // first request lights it up and every subsequent search hits the cache.
  const catalogue = createQuery(() => ({
    queryKey: keys.rivenWeapons(),
    queryFn:  fetchers.rivenWeapons,
    staleTime: 24 * 60 * 60 * 1000,
  }));

  // Auto-select first weapon when the watchlist loads.
  createMemo(() => {
    const first = (watchlist.data?.items ?? [])[0];
    if (first && !selected()) setSelected(first.weapon_slug);
  });

  // Subscribe to every watched weapon's alert channel.
  useRivenAlerts(() => (watchlist.data?.items ?? []).map((w) => w.weapon_slug));

  async function addBySlug(slug: string) {
    const clean = slug.trim().toLowerCase();
    if (!clean) return;
    await fetchers.rivenWatchAdd(clean);
    await qc.invalidateQueries({ queryKey: keys.rivenWatchlist() });
    setSelected(clean);
    // Fire an immediate snapshot so the price-history chart starts populating
    // right away instead of waiting up to 60s for the next poller tick.
    fetchers.rivenPollNow(clean)
      .then(() => qc.invalidateQueries({ queryKey: keys.rivenHistory(clean, "all", 7) }))
      .catch(() => { /* poller down → next regular tick will cover it */ });
  }

  async function remove(slug: string) {
    await fetchers.rivenWatchRemove(slug);
    await qc.invalidateQueries({ queryKey: keys.rivenWatchlist() });
    if (selected() === slug) setSelected(null);
  }

  return (
    <div class="space-y-6">
      <PageHeader title={t("nav.rivenAnalyzer")} />

      <div class="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4">
        <WatchlistPanel
          watched={(watchlist.data?.items ?? []).map((w) => w.weapon_slug)}
          weapons={catalogue.data?.items ?? []}
          catalogueLoading={catalogue.isLoading}
          selected={selected()}
          onSelect={setSelected}
          onRemove={remove}
          onAdd={addBySlug}
        />

        <Show
          when={selected()}
          fallback={<Card><EmptyState title={t("rivens.selectWeapon")} hint="" /></Card>}
        >
          <WeaponView slug={selected()!} weapon={catalogue.data?.items.find((w) => w.slug === selected())} />
        </Show>
      </div>
    </div>
  );
}

// -------------------------------------------------------------- Watchlist

function WatchlistPanel(p: {
  watched: string[];
  weapons: RivenWeapon[];
  catalogueLoading: boolean;
  selected: string | null;
  onSelect: (s: string) => void;
  onRemove: (s: string) => void;
  onAdd: (slug: string) => void | Promise<void>;
}) {
  const counts = createMemo(() => alertCountByWeapon());
  const watchedSet = createMemo(() => new Set(p.watched));
  const [query, setQuery] = createSignal("");
  const [open, setOpen] = createSignal(false);

  const matches = createMemo(() => {
    const q = query().trim().toLowerCase();
    if (!q) return [];
    const all = p.weapons.filter((w) => !watchedSet().has(w.slug));
    const scored = all
      .map((w) => {
        const name = (w.item_name || "").toLowerCase();
        const slug = (w.slug || "").toLowerCase();
        const nameIdx = name.indexOf(q);
        const slugIdx = slug.indexOf(q);
        if (nameIdx === -1 && slugIdx === -1) return null;
        const score = nameIdx === -1 ? 1000 + slugIdx : nameIdx;
        return { w, score };
      })
      .filter((r): r is { w: RivenWeapon; score: number } => r !== null)
      .sort((a, b) => a.score - b.score)
      .slice(0, 8)
      .map((r) => r.w);
    return scored;
  });

  async function pick(w: RivenWeapon) {
    setQuery("");
    setOpen(false);
    await p.onAdd(w.slug);
  }

  return (
    <Card title={t("rivens.watchlist")}>
      <div class="relative mb-3">
        <input
          type="text"
          value={query()}
          onInput={(e) => { setQuery(e.currentTarget.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={p.catalogueLoading ? t("common.loading") : t("rivens.searchPlaceholder")}
          disabled={p.catalogueLoading}
          class="field disabled:opacity-50"
        />
        <Show when={open() && matches().length > 0}>
          <ul class="absolute z-20 mt-1 w-full max-h-72 overflow-auto rounded-[10px] border border-line bg-surface2 shadow-[var(--shadow-lift)]">
            <For each={matches()}>
              {(w) => (
                <li>
                  <button
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); pick(w); }}
                    class="w-full flex items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-white/[0.04] transition-colors"
                  >
                    <span class="flex flex-col">
                      <span class="text-fg">{w.item_name}</span>
                      <span class="text-xs text-dim">{w.slug}</span>
                    </span>
                    <Show when={w.disposition != null}>
                      <span class="text-xs px-1.5 py-0.5 rounded bg-surface text-amber-300 num">
                        {t("rivens.disposition")} {w.disposition!.toFixed(2)}
                      </span>
                    </Show>
                  </button>
                </li>
              )}
            </For>
          </ul>
        </Show>
      </div>

      <Show
        when={p.watched.length > 0}
        fallback={<div class="text-sm text-dim">{t("rivens.watchlistEmpty")}</div>}
      >
        <ul class="space-y-1">
          <For each={p.watched}>
            {(slug) => {
              const meta = p.weapons.find((w) => w.slug === slug);
              return (
                <li>
                  <button
                    type="button"
                    onClick={() => p.onSelect(slug)}
                    class="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-[10px] text-left text-sm transition-colors"
                    classList={{
                      "bg-brand/10 text-fg": p.selected === slug,
                      "text-sub hover:bg-white/[0.03]": p.selected !== slug,
                    }}
                  >
                    <ItemThumb src={wfmAsset(meta?.icon)} name={meta?.item_name ?? slug} size={30} />
                    <span class="truncate flex-1">{meta?.item_name ?? prettySlug(slug)}</span>
                    <span class="flex items-center gap-1">
                      <Show when={(counts()[slug] ?? 0) > 0}>
                        <Badge variant="good">{counts()[slug]}</Badge>
                      </Show>
                      <span
                        role="button"
                        tabindex="0"
                        class="text-dim hover:text-rose-400 px-1 transition-colors"
                        onClick={(e) => { e.stopPropagation(); p.onRemove(slug); }}
                      >
                        {t("rivens.watchlistRemove")}
                      </span>
                    </span>
                  </button>
                </li>
              );
            }}
          </For>
        </ul>
      </Show>
    </Card>
  );
}

// -------------------------------------------------------------- WeaponView

const PAGE_SIZE = 20;
const TIER_NAMES = ["god", "mid", "low"] as const;
type TierName = (typeof TIER_NAMES)[number];
type ProfileLens = "base" | "incarnon";

function WeaponView(p: { slug: string; weapon?: RivenWeapon }) {
  const auctions = createQuery(() => ({
    queryKey: keys.rivenAuctions(p.slug),
    queryFn:  () => fetchers.rivenAuctions(p.slug),
    refetchInterval: 60_000,
  }));
  const history = createQuery(() => ({
    queryKey: keys.rivenHistory(p.slug, "all", 7),
    queryFn:  () => fetchers.rivenHistory(p.slug, "all", 7),
    refetchInterval: 5 * 60_000,
  }));

  const [statusFilter, setStatusFilter] = createSignal<"all" | "online" | "ingame">("all");
  const [tierFilter, setTierFilter] = createSignal<TierName | "all">("all");
  // Page-level scoring lens: which combat profile drives the primary grade shown
  // on every card. Defaults to Incarnon (endgame) when the weapon has one.
  const [lens, setLens] = createSignal<ProfileLens>("incarnon");
  const hasIncarnon = createMemo(() => auctions.data?.has_incarnon_profile ?? false);
  // No Incarnon profile → there is no toggle, so force the base lens.
  const effectiveLens = createMemo<ProfileLens>(() => (hasIncarnon() ? lens() : "base"));

  function filterRows(rows: RivenAuctionRow[]): RivenAuctionRow[] {
    const f = statusFilter();
    if (f === "all") return rows;
    if (f === "ingame") return rows.filter((r) => r.owner_status === "ingame");
    return rows.filter((r) => r.owner_status === "ingame" || r.owner_status === "online");
  }

  const filteredOutliers = createMemo(() => {
    const rawOutliers = auctions.data?.outliers ?? [];
    const f = statusFilter();
    if (f === "all") return rawOutliers;
    return rawOutliers.filter((o) => {
      const tierRows = auctions.data?.tiers[o.tier as TierName] ?? [];
      const row = tierRows.find((r) => r.auction_id === o.auction_id);
      if (!row) return false;
      if (f === "ingame") return row.owner_status === "ingame";
      return row.owner_status === "ingame" || row.owner_status === "online";
    });
  });

  function visibleTiers(): { name: TierName; key: string }[] {
    const all = [
      { name: "god" as const, key: "rivens.tierGod" },
      { name: "mid" as const, key: "rivens.tierMid" },
      { name: "low" as const, key: "rivens.tierLow" },
    ];
    const sel = tierFilter();
    return sel === "all" ? all : all.filter((tt) => tt.name === sel);
  }

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3 flex-wrap">
        <ItemThumb src={wfmAsset(p.weapon?.icon)} name={p.weapon?.item_name ?? prettySlug(p.slug)} size={40} />
        <h2 class="text-xl font-semibold text-fg font-display tracking-tight">{p.weapon?.item_name ?? prettySlug(p.slug)}</h2>
        <Show when={p.weapon?.disposition != null}>
          <span class="text-xs px-2 py-0.5 rounded bg-surface2 border border-line text-amber-300 num">
            {t("rivens.disposition")} {p.weapon!.disposition!.toFixed(2)}
          </span>
        </Show>
        <a
          href={`https://warframe.market/auctions/search?type=riven&weapon_url_name=${encodeURIComponent(p.slug)}`}
          target="_blank"
          class="text-xs text-sub hover:text-brand-soft transition-colors"
        >
          {t("rivens.openInWfm")}
        </a>
      </header>

      <Show
        when={!auctions.isLoading}
        fallback={<Card><div class="text-dim">{t("rivens.auctionsLoading")}</div></Card>}
      >
        <Show
          when={auctions.data}
          fallback={<Card><div class="text-rose-400 text-sm">{t("rivens.auctionsError")}</div></Card>}
        >
          <FiltersBar
            statusFilter={statusFilter()}
            setStatusFilter={setStatusFilter}
            tierFilter={tierFilter()}
            setTierFilter={setTierFilter}
            hasIncarnon={hasIncarnon()}
            lens={effectiveLens()}
            setLens={setLens}
            incarnonVersion={auctions.data!.incarnon_game_version}
            incarnonOutdated={auctions.data!.incarnon_outdated}
          />

          <Card title={t("rivens.tierStats")}>
            <TierStatsTable stats={auctions.data!.stats} />
          </Card>

          <Card title={t("rivens.outliersTitle")}>
            <OutliersList outliers={filteredOutliers()} />
          </Card>

          <Show when={auctions.data!.top_attributes.length > 0 || (auctions.data!.avoid_negatives && auctions.data!.avoid_negatives.length > 0) || (auctions.data!.harmless_negatives && auctions.data!.harmless_negatives.length > 0)}>
            <Card title={t("rivens.topAttributes")}>
              <div class="space-y-4">
                <div>
                  <h3 class="text-xs font-semibold text-sub uppercase tracking-wider mb-2">{t("rivens.topPositives")}</h3>
                  <TopAttrs attrs={auctions.data!.top_attributes} />
                </div>
                <Show when={auctions.data!.harmless_negatives && auctions.data!.harmless_negatives.length > 0}>
                  <div>
                    <h3 class="text-xs font-semibold text-cyan uppercase tracking-wider mb-2">{t("rivens.harmlessNegatives")}</h3>
                    <ul class="flex flex-wrap gap-2">
                      <For each={auctions.data!.harmless_negatives}>
                        {(neg) => <li class="text-xs px-2.5 py-1 rounded-full bg-cyan/[0.08] border border-cyan/25 text-cyan">-{rivenAttrName(neg)}</li>}
                      </For>
                    </ul>
                  </div>
                </Show>
                <Show when={auctions.data!.avoid_negatives && auctions.data!.avoid_negatives.length > 0}>
                  <div>
                    <h3 class="text-xs font-semibold text-rose-400 uppercase tracking-wider mb-2">{t("rivens.avoidNegatives")}</h3>
                    <ul class="flex flex-wrap gap-2">
                      <For each={auctions.data!.avoid_negatives}>
                        {(neg) => <li class="text-xs px-2.5 py-1 rounded-full bg-rose-500/[0.08] border border-rose-500/25 text-rose-300">-{rivenAttrName(neg)}</li>}
                      </For>
                    </ul>
                  </div>
                </Show>
              </div>
            </Card>
          </Show>

          <Card title={t("rivens.strategiesTitle")}>
            <StrategyList tips={auctions.data!.strategies} />
          </Card>

          <For each={visibleTiers()}>
            {(tier) => {
              const rows = createMemo(() => filterRows(auctions.data!.tiers[tier.name]));
              return (
                <Show when={rows().length > 0}>
                  <Card title={`${t(tier.key as never)} · ${rows().length}`}>
                    <PaginatedAuctionTable rows={rows()} outliers={auctions.data!.outliers} lens={effectiveLens()} />
                  </Card>
                </Show>
              );
            }}
          </For>

          <Card title={t("rivens.historyTitle")}>
            <HistorySparkline rows={history.data?.items ?? []} loading={history.isLoading} />
          </Card>
        </Show>
      </Show>
    </div>
  );
}

function FiltersBar(p: {
  statusFilter: "all" | "online" | "ingame";
  setStatusFilter: (v: "all" | "online" | "ingame") => void;
  tierFilter: TierName | "all";
  setTierFilter: (v: TierName | "all") => void;
  hasIncarnon: boolean;
  lens: ProfileLens;
  setLens: (v: ProfileLens) => void;
  incarnonVersion: string | null;
  incarnonOutdated: boolean;
}) {
  return (
    <div class="flex flex-wrap items-center gap-4 px-3 py-2.5 surface">
      <div class="flex items-center gap-2">
        <span class="text-xs text-dim">{t("rivens.statusFilter")}:</span>
        <div class="seg">
          <For each={[
            { v: "all" as const,    label: t("rivens.statusAll") },
            { v: "online" as const, label: t("rivens.statusOnline") },
            { v: "ingame" as const, label: t("rivens.statusIngame") },
          ]}>
            {(opt) => (
              <button type="button" class="seg-btn" classList={{ active: p.statusFilter === opt.v }} onClick={() => p.setStatusFilter(opt.v)}>
                {opt.label}
              </button>
            )}
          </For>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="text-xs text-dim">{t("rivens.tier")}:</span>
        <div class="seg">
          <For each={[
            { v: "all" as const, label: t("rivens.tierAll") },
            { v: "god" as const, label: t("rivens.tierGod") },
            { v: "mid" as const, label: t("rivens.tierMid") },
            { v: "low" as const, label: t("rivens.tierLow") },
          ]}>
            {(opt) => (
              <button type="button" class="seg-btn" classList={{ active: p.tierFilter === opt.v }} onClick={() => p.setTierFilter(opt.v)}>
                {opt.label}
              </button>
            )}
          </For>
        </div>
      </div>
      {/* Page-level scoring lens — only when the weapon has a curated Incarnon
          profile (no toggle = no dead control). */}
      <Show when={p.hasIncarnon}>
        <div class="flex items-center gap-2">
          <span class="text-xs text-dim">{t("rivens.scoringFor")}:</span>
          <div class="seg">
            <For each={[
              { v: "base" as const, label: t("rivens.lensBase") },
              { v: "incarnon" as const, label: t("rivens.lensIncarnon") },
            ]}>
              {(opt) => (
                <button type="button" class="seg-btn" classList={{ active: p.lens === opt.v }} onClick={() => p.setLens(opt.v)}>
                  {opt.label}
                </button>
              )}
            </For>
          </div>
          <span
            class="text-[11px]"
            classList={{ "text-amber-300": p.incarnonOutdated, "text-dim": !p.incarnonOutdated }}
            title={p.incarnonVersion ?? ""}
          >
            {p.incarnonOutdated
              ? t("rivens.incarnonOutdated")
              : t("rivens.incarnonAsOf", { v: p.incarnonVersion ?? "?" })}
          </span>
        </div>
      </Show>
    </div>
  );
}

function PaginatedAuctionTable(props: { rows: RivenAuctionRow[]; outliers: RivenOutlier[]; lens: ProfileLens }) {
  const [page, setPage] = createSignal(0);
  const totalPages = createMemo(() => Math.max(1, Math.ceil(props.rows.length / PAGE_SIZE)));
  createMemo(() => { if (page() >= totalPages()) setPage(0); });
  const pageRows = createMemo(() => {
    const start = page() * PAGE_SIZE;
    return props.rows.slice(start, start + PAGE_SIZE);
  });
  return (
    <div class="space-y-2">
      <AuctionTable rows={pageRows()} outliers={props.outliers} lens={props.lens} />
      <Show when={totalPages() > 1}>
        <div class="flex items-center justify-between text-xs text-sub">
          <button type="button" disabled={page() === 0} onClick={() => setPage(page() - 1)} class="px-2.5 py-1 rounded-lg border border-line hover:text-fg hover:bg-white/[0.03] disabled:opacity-30 disabled:cursor-not-allowed transition-colors">←</button>
          <span class="num">{page() + 1} / {totalPages()} · {props.rows.length} {t("rivens.lots")}</span>
          <button type="button" disabled={page() >= totalPages() - 1} onClick={() => setPage(page() + 1)} class="px-2.5 py-1 rounded-lg border border-line hover:text-fg hover:bg-white/[0.03] disabled:opacity-30 disabled:cursor-not-allowed transition-colors">→</button>
        </div>
      </Show>
    </div>
  );
}

// -------------------------------------------------------------- sub-components

function TierStatsTable(props: { stats: RivenTierStats[] }) {
  return (
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-line text-left text-sub">
          <th class="py-1.5 px-2">{t("rivens.tierStats")}</th>
          <th class="py-1.5 px-2 text-right">{t("rivens.statsCount")}</th>
          <th class="py-1.5 px-2 text-right">{t("rivens.statsMin")}</th>
          <th class="py-1.5 px-2 text-right">{t("rivens.statsP25")}</th>
          <th class="py-1.5 px-2 text-right">{t("rivens.statsMedian")}</th>
          <th class="py-1.5 px-2 text-right">{t("rivens.statsP75")}</th>
          <th class="py-1.5 px-2 text-right">{t("rivens.statsMax")}</th>
        </tr>
      </thead>
      <tbody>
        <For each={props.stats}>
          {(s) => (
            <tr class="border-b border-line">
              <td class="py-1.5 px-2 text-sub">{s.tier}</td>
              <td class="py-1.5 px-2 text-right num">{s.count}</td>
              <td class="py-1.5 px-2 text-right num">{fmtPlat(s.min_price)}</td>
              <td class="py-1.5 px-2 text-right num">{fmtPlat(s.p25)}</td>
              <td class="py-1.5 px-2 text-right num text-fg font-semibold">{fmtPlat(s.median)}</td>
              <td class="py-1.5 px-2 text-right num">{fmtPlat(s.p75)}</td>
              <td class="py-1.5 px-2 text-right num">{fmtPlat(s.max_price)}</td>
            </tr>
          )}
        </For>
      </tbody>
    </table>
  );
}

function OutliersList(props: { outliers: RivenOutlier[] }) {
  const [page, setPage] = createSignal(0);
  const outliersPageSize = 8;
  const totalPages = createMemo(() => Math.max(1, Math.ceil(props.outliers.length / outliersPageSize)));
  createMemo(() => { if (page() >= totalPages()) setPage(0); });
  const pageOutliers = createMemo(() => {
    const start = page() * outliersPageSize;
    return props.outliers.slice(start, start + outliersPageSize);
  });

  return (
    <Show
      when={props.outliers.length > 0}
      fallback={<div class="text-sm text-dim">{t("rivens.outliersEmpty")}</div>}
    >
      <div class="space-y-2">
        <ul class="space-y-1.5">
          <For each={pageOutliers()}>
            {(o) => (
              <li>
                <a
                  href={auctionUrl(o.auction_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  class="flex items-center justify-between gap-2 text-sm px-3 py-2 rounded-[10px] bg-surface2 border border-line hover:border-line-strong hover:bg-white/[0.03] transition-colors"
                >
                  <code class="text-xs text-dim num truncate">{o.auction_id}</code>
                  <span class="text-mint num font-semibold">
                    {t("rivens.outlierItem", {
                      price: fmtPlat(o.price), pct: o.discount_pct,
                      median: fmtPlat(o.historical_median), tier: o.tier,
                    })}
                  </span>
                </a>
              </li>
            )}
          </For>
        </ul>

        <Show when={totalPages() > 1}>
          <div class="flex items-center justify-between text-xs text-sub pt-1">
            <button type="button" disabled={page() === 0} onClick={() => setPage(page() - 1)} class="px-2.5 py-1 rounded-lg border border-line hover:text-fg hover:bg-white/[0.03] disabled:opacity-30 disabled:cursor-not-allowed transition-colors">←</button>
            <span class="num text-dim text-[11px]">{page() + 1} / {totalPages()} · {props.outliers.length} {t("rivens.lots")}</span>
            <button type="button" disabled={page() >= totalPages() - 1} onClick={() => setPage(page() + 1)} class="px-2.5 py-1 rounded-lg border border-line hover:text-fg hover:bg-white/[0.03] disabled:opacity-30 disabled:cursor-not-allowed transition-colors">→</button>
          </div>
        </Show>
      </div>
    </Show>
  );
}

function TopAttrs(props: { attrs: RivenTopAttribute[] }) {
  return (
    <ul class="flex flex-wrap gap-2">
      <For each={props.attrs}>
        {(a) => <li class="text-xs px-2.5 py-1 rounded-full bg-mint/[0.08] border border-mint/25 text-mint">{rivenAttrName(a.name)}</li>}
      </For>
    </ul>
  );
}

function StrategyList(props: { tips: RivenStrategyTip[] }) {
  return (
    <ul class="space-y-2">
      <For each={props.tips}>
        {(tip) => (
          <li class="text-sm flex gap-2">
            <span
              class="inline-block w-1 self-stretch rounded"
              classList={{
                "bg-mint": tip.severity === "good",
                "bg-amber-400": tip.severity === "warn",
                "bg-white/20": tip.severity === "info",
              }}
            />
            <span class="text-sub">{locale() === "ru" ? tip.ru : tip.en}</span>
          </li>
        )}
      </For>
    </ul>
  );
}

function gradeColorClass(grade: string): Record<string, boolean> {
  return {
    "text-mint": grade === "S" || grade === "A",
    "text-cyan": grade === "B",
    "text-amber": grade === "C",
    "text-rose-300": grade === "F",
  };
}

function GradeCell(props: { row: RivenAuctionRow; lens: ProfileLens }) {
  // `per_profile` may be absent on older/cached API payloads (pre-S3b) — guard it.
  const profiles = createMemo(() => props.row.per_profile ?? []);
  const base = createMemo(() => profiles().find((p) => p.kind === "base"));
  const inc = createMemo(() => profiles().find((p) => p.kind === "incarnon"));
  // Headline fallback for payloads with grade/score but no per_profile array.
  const headline = createMemo(() =>
    !props.row.unscored && props.row.grade != null
      ? { kind: "base", grade: props.row.grade, score: props.row.score ?? 0 }
      : undefined,
  );
  // Dual lens: the selected profile is primary (big), the other trails small, so
  // the Base→Incarnon delta is always visible (the whole point of Incarnon scoring).
  const primary = createMemo(() => (props.lens === "incarnon" ? inc() : base()) ?? base() ?? inc() ?? headline());
  const secondary = createMemo(() => (props.lens === "incarnon" ? base() : inc()));
  return (
    <Show
      when={!props.row.unscored && primary()}
      fallback={<span class="text-dim" title={props.row.unscored_reason ?? ""}>—</span>}
    >
      <span class="font-bold" classList={gradeColorClass(primary()!.grade)}>{primary()!.grade}</span>
      <span class="text-[10px] text-dim num"> · {primary()!.score}</span>
      <Show when={secondary()}>
        <span class="text-[10px] text-dim">
          {" "}({props.lens === "incarnon" ? t("rivens.lensBase") : t("rivens.lensIncarnon")} {secondary()!.grade})
        </span>
      </Show>
      <Show when={props.row.market_signal === "steal" || props.row.market_signal === "trap"}>
        <span
          class="ml-1 text-[10px] px-1 rounded font-semibold"
          classList={{
            "bg-mint/20 text-mint": props.row.market_signal === "steal",
            "bg-rose-500/15 text-rose-300": props.row.market_signal === "trap",
          }}
          title={t(props.row.market_signal === "steal" ? "rivens.stealHint" : "rivens.trapHint")}
        >
          {props.row.market_signal === "steal" ? `🔥 ${t("rivens.steal")}` : `⚠ ${t("rivens.trap")}`}
        </span>
      </Show>
    </Show>
  );
}

function AuctionTable(props: { rows: RivenAuctionRow[]; outliers: RivenOutlier[]; lens: ProfileLens }) {
  const outlierIds = new Set(props.outliers.map((o) => o.auction_id));
  return (
    <div class="overflow-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="border-b border-line text-left text-sub">
            <th class="py-1.5 px-2">{t("rivens.colGrade")}</th>
            <th class="py-1.5 px-2 text-right">{t("rivens.colPrice")}</th>
            <th class="py-1.5 px-2 text-right">{t("rivens.colTopBid")}</th>
            <th class="py-1.5 px-2 text-right">{t("rivens.colReRolls")}</th>
            <th class="py-1.5 px-2">{t("rivens.colPolarity")}</th>
            <th class="py-1.5 px-2">{t("rivens.colAttrs")}</th>
            <th class="py-1.5 px-2">{t("rivens.colOwner")}</th>
          </tr>
        </thead>
        <tbody>
          <For each={props.rows}>
            {(r) => (
              <tr
                class="border-b border-line hover:bg-white/[0.03] cursor-pointer transition-colors"
                classList={{ "bg-mint/[0.06] hover:bg-mint/[0.10]": outlierIds.has(r.auction_id) }}
                onClick={() => window.open(auctionUrl(r.auction_id), "_blank", "noopener,noreferrer")}
                title={t("rivens.openInWfm")}
              >
                <td class="py-1.5 px-2 whitespace-nowrap">
                  <GradeCell row={r} lens={props.lens} />
                </td>
                <td class="py-1.5 px-2 text-right num text-fg">{fmtPlat(r.buyout_price)}</td>
                <td class="py-1.5 px-2 text-right num text-sub">{fmtPlat(r.top_bid)}</td>
                <td class="py-1.5 px-2 text-right num text-sub">{r.re_rolls ?? "—"}</td>
                <td class="py-1.5 px-2 text-sub">{r.polarity ?? "—"}</td>
                <td class="py-1.5 px-2 text-sub">
                  <span class="flex flex-wrap gap-1">
                    <For each={r.attributes}>
                      {(a) => (
                        <span
                          class="text-[10px] px-1 rounded"
                          classList={{
                            "bg-mint/15 text-mint": a.positive,
                            "bg-rose-500/15 text-rose-300": !a.positive,
                          }}
                        >
                          {rivenAttrName(a.name)} {a.value > 0 && a.positive ? "+" : ""}{a.value}
                        </span>
                      )}
                    </For>
                  </span>
                </td>
                <td class="py-1.5 px-2 text-sub num">
                  <span class="flex items-center gap-1">
                    <Show when={r.owner_status}>
                      <span
                        class="inline-block w-1.5 h-1.5 rounded-full"
                        classList={{
                          "bg-cyan": r.owner_status === "ingame",
                          "bg-mint": r.owner_status === "online",
                          "bg-white/20": r.owner_status === "offline",
                        }}
                        title={r.owner_status ?? ""}
                      />
                    </Show>
                    {r.owner_name ?? "—"}
                  </span>
                </td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
    </div>
  );
}

function HistorySparkline(props: {
  rows: { ts: number; median: number | null }[];
  loading: boolean;
}) {
  const usable = createMemo(() =>
    props.rows
      .filter((r) => r.median != null)
      .map((r) => ({ ts: r.ts, v: r.median as number }))
      .sort((a, b) => a.ts - b.ts),
  );

  const points = createMemo(() => {
    const ms = usable();
    if (ms.length < 2) return "";
    const first = ms[0]!, last = ms[ms.length - 1]!;
    const minTs = first.ts, maxTs = last.ts;
    const minV = Math.min(...ms.map((pt) => pt.v));
    const maxV = Math.max(...ms.map((pt) => pt.v));
    const W = 600, H = 80;
    const padding = 6;
    const chartHeight = H - 2 * padding;
    const xRange = Math.max(1, maxTs - minTs);
    // A flat series (constant median — common for stable weapons) has zero
    // y-range; draw it as a centered horizontal line instead of one pinned to
    // the bottom edge, where it reads as "no chart".
    const flat = maxV === minV;
    const yRange = Math.max(1, maxV - minV);
    return ms.map((pt, i) => {
      const x = ((pt.ts - minTs) / xRange) * W;
      const y = flat ? H / 2 : H - padding - ((pt.v - minV) / yRange) * chartHeight;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");
  });

  return (
    <Show
      when={!props.loading}
      fallback={<div class="text-sm text-dim">{t("rivens.auctionsLoading")}</div>}
    >
      <Show
        when={usable().length >= 2}
        fallback={
          <div class="text-sm text-dim">
            {usable().length === 0 ? t("rivens.historyEmpty") : t("rivens.historyOnePoint")}
          </div>
        }
      >
        <div class="flex items-center justify-between text-xs text-dim mb-1">
          <span>{t("rivens.historyPoints", { n: usable().length })}</span>
          <span class="num">{fmtPlat(usable()[0]!.v)} → {fmtPlat(usable()[usable().length - 1]!.v)}</span>
        </div>
        <svg viewBox="0 0 600 80" class="w-full h-20" preserveAspectRatio="none">
          <defs>
            <linearGradient id="riven-spark" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stop-color="#818cf8" />
              <stop offset="100%" stop-color="#34d399" />
            </linearGradient>
          </defs>
          <path d={points()} stroke="url(#riven-spark)" stroke-width="1.8" fill="none" />
        </svg>
      </Show>
    </Show>
  );
}

function auctionUrl(auctionId: string): string {
  return `https://warframe.market/auction/${encodeURIComponent(auctionId)}`;
}
