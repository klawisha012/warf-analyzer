import { For, Show, createMemo, createSignal } from "solid-js";
import { createQuery, useQueryClient } from "@tanstack/solid-query";
import Card from "../components/Card";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import { fetchers, keys } from "../api/queries";
import { fmtPlat, prettySlug } from "../lib/format";
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
  }

  async function remove(slug: string) {
    await fetchers.rivenWatchRemove(slug);
    await qc.invalidateQueries({ queryKey: keys.rivenWatchlist() });
    if (selected() === slug) setSelected(null);
  }

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3">
        <h1 class="text-2xl font-bold">{t("rivens.title")}</h1>
      </header>

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
    // Match either the display name or the slug substring.
    const scored = all
      .map((w) => {
        const name = (w.item_name || "").toLowerCase();
        const slug = (w.slug || "").toLowerCase();
        const nameIdx = name.indexOf(q);
        const slugIdx = slug.indexOf(q);
        if (nameIdx === -1 && slugIdx === -1) return null;
        // Earlier match in the name ranks higher; slug-only match ranks lowest.
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
          class="w-full px-2 py-1 text-sm rounded-md bg-slate-900 border border-slate-800 text-slate-100 disabled:opacity-50"
        />
        <Show when={open() && matches().length > 0}>
          <ul class="absolute z-20 mt-1 w-full max-h-72 overflow-auto rounded-md border border-slate-800 bg-slate-950 shadow-xl">
            <For each={matches()}>
              {(w) => (
                <li>
                  <button
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); pick(w); }}
                    class="w-full flex items-center justify-between gap-2 px-2 py-1 text-left text-sm hover:bg-slate-800"
                  >
                    <span class="flex flex-col">
                      <span class="text-slate-100">{w.item_name}</span>
                      <span class="text-xs text-slate-500 font-mono">{w.slug}</span>
                    </span>
                    <Show when={w.disposition != null}>
                      <span class="text-xs px-1.5 py-0.5 rounded bg-slate-800 text-amber-300 font-mono">
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
        fallback={<div class="text-sm text-slate-500">{t("rivens.watchlistEmpty")}</div>}
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
                    class="w-full flex items-center justify-between gap-2 px-2 py-1 rounded text-left text-sm transition-colors"
                    classList={{
                      "bg-slate-800 text-slate-100": p.selected === slug,
                      "text-slate-300 hover:bg-slate-900": p.selected !== slug,
                    }}
                  >
                    <span class="truncate">{meta?.item_name ?? prettySlug(slug)}</span>
                    <span class="flex items-center gap-1">
                      <Show when={(counts()[slug] ?? 0) > 0}>
                        <Badge variant="good">{counts()[slug]}</Badge>
                      </Show>
                      <span
                        role="button"
                        tabindex="0"
                        class="text-slate-500 hover:text-rose-400 px-1"
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

  return (
    <div class="space-y-4">
      <header class="flex items-baseline gap-3 flex-wrap">
        <h2 class="text-xl font-semibold text-slate-100">{p.weapon?.item_name ?? prettySlug(p.slug)}</h2>
        <Show when={p.weapon?.disposition != null}>
          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-amber-300 font-mono">
            {t("rivens.disposition")} {p.weapon!.disposition!.toFixed(2)}
          </span>
        </Show>
        <a
          href={`https://warframe.market/auctions/search?type=riven&weapon_url_name=${encodeURIComponent(p.slug)}`}
          target="_blank"
          class="text-xs text-slate-400 hover:text-emerald-300"
        >
          {t("rivens.openInWfm")}
        </a>
      </header>

      <Show
        when={!auctions.isLoading}
        fallback={<Card><div class="text-slate-500">{t("rivens.auctionsLoading")}</div></Card>}
      >
        <Show
          when={auctions.data}
          fallback={<Card><div class="text-rose-400 text-sm">{t("rivens.auctionsError")}</div></Card>}
        >
          {/* Tier stats */}
          <Card title={t("rivens.tierStats")}>
            <TierStatsTable stats={auctions.data!.stats} />
          </Card>

          {/* Outliers */}
          <Card title={t("rivens.outliersTitle")}>
            <OutliersList outliers={auctions.data!.outliers} />
          </Card>

          {/* Top attributes */}
          <Show when={auctions.data!.top_attributes.length > 0}>
            <Card title={t("rivens.topAttributes")}>
              <TopAttrs attrs={auctions.data!.top_attributes} />
            </Card>
          </Show>

          {/* Strategies */}
          <Card title={t("rivens.strategiesTitle")}>
            <StrategyList tips={auctions.data!.strategies} />
          </Card>

          {/* Per-tier tables */}
          <For each={[
            { name: "god" as const, key: "rivens.tierGod" },
            { name: "mid" as const, key: "rivens.tierMid" },
            { name: "low" as const, key: "rivens.tierLow" },
          ]}>
            {(tier) => (
              <Show when={auctions.data!.tiers[tier.name].length > 0}>
                <Card title={t(tier.key as never)}>
                  <AuctionTable
                    rows={auctions.data!.tiers[tier.name]}
                    outliers={auctions.data!.outliers}
                  />
                </Card>
              </Show>
            )}
          </For>

          {/* History */}
          <Card title={t("rivens.historyTitle")}>
            <Show
              when={(history.data?.items ?? []).length > 0}
              fallback={<div class="text-sm text-slate-500">{t("rivens.historyEmpty")}</div>}
            >
              <HistorySparkline rows={history.data!.items} />
            </Show>
          </Card>
        </Show>
      </Show>
    </div>
  );
}

// -------------------------------------------------------------- sub-components

function TierStatsTable(props: { stats: RivenTierStats[] }) {
  return (
    <table class="w-full text-sm">
      <thead class="text-left text-slate-400">
        <tr class="border-b border-slate-800">
          <th class="py-1 px-2">{t("rivens.tierStats")}</th>
          <th class="py-1 px-2 text-right">{t("rivens.statsCount")}</th>
          <th class="py-1 px-2 text-right">{t("rivens.statsMin")}</th>
          <th class="py-1 px-2 text-right">{t("rivens.statsP25")}</th>
          <th class="py-1 px-2 text-right">{t("rivens.statsMedian")}</th>
          <th class="py-1 px-2 text-right">{t("rivens.statsP75")}</th>
          <th class="py-1 px-2 text-right">{t("rivens.statsMax")}</th>
        </tr>
      </thead>
      <tbody>
        <For each={props.stats}>
          {(s) => (
            <tr class="border-b border-slate-900">
              <td class="py-1 px-2 text-slate-300">{s.tier}</td>
              <td class="py-1 px-2 text-right font-mono">{s.count}</td>
              <td class="py-1 px-2 text-right font-mono">{fmtPlat(s.min_price)}</td>
              <td class="py-1 px-2 text-right font-mono">{fmtPlat(s.p25)}</td>
              <td class="py-1 px-2 text-right font-mono text-slate-100">{fmtPlat(s.median)}</td>
              <td class="py-1 px-2 text-right font-mono">{fmtPlat(s.p75)}</td>
              <td class="py-1 px-2 text-right font-mono">{fmtPlat(s.max_price)}</td>
            </tr>
          )}
        </For>
      </tbody>
    </table>
  );
}

function OutliersList(props: { outliers: RivenOutlier[] }) {
  return (
    <Show
      when={props.outliers.length > 0}
      fallback={<div class="text-sm text-slate-500">{t("rivens.outliersEmpty")}</div>}
    >
      <ul class="space-y-1">
        <For each={props.outliers}>
          {(o) => (
            <li class="flex items-center justify-between gap-2 text-sm">
              <code class="text-xs text-slate-500 font-mono truncate">{o.auction_id}</code>
              <span class="text-emerald-300 font-mono">
                {t("rivens.outlierItem", {
                  price: fmtPlat(o.price), pct: o.discount_pct,
                  median: fmtPlat(o.historical_median), tier: o.tier,
                })}
              </span>
            </li>
          )}
        </For>
      </ul>
    </Show>
  );
}

function TopAttrs(props: { attrs: RivenTopAttribute[] }) {
  return (
    <ul class="flex flex-wrap gap-2">
      <For each={props.attrs}>
        {(a) => (
          <li class="text-xs px-2 py-1 rounded bg-slate-800 text-slate-200">
            {prettyAttr(a.name)} · {Math.round(a.share * 100)}%
          </li>
        )}
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
                "bg-emerald-500": tip.severity === "good",
                "bg-amber-500": tip.severity === "warn",
                "bg-slate-600": tip.severity === "info",
              }}
            />
            <span class="text-slate-200">{locale() === "ru" ? tip.ru : tip.en}</span>
          </li>
        )}
      </For>
    </ul>
  );
}

function AuctionTable(props: { rows: RivenAuctionRow[]; outliers: RivenOutlier[] }) {
  const outlierIds = new Set(props.outliers.map((o) => o.auction_id));
  return (
    <div class="overflow-auto">
      <table class="w-full text-xs">
        <thead class="text-left text-slate-400">
          <tr class="border-b border-slate-800">
            <th class="py-1 px-2 text-right">{t("rivens.colPrice")}</th>
            <th class="py-1 px-2 text-right">{t("rivens.colTopBid")}</th>
            <th class="py-1 px-2 text-right">{t("rivens.colReRolls")}</th>
            <th class="py-1 px-2">{t("rivens.colPolarity")}</th>
            <th class="py-1 px-2">{t("rivens.colAttrs")}</th>
            <th class="py-1 px-2">{t("rivens.colOwner")}</th>
          </tr>
        </thead>
        <tbody>
          <For each={props.rows}>
            {(r) => (
              <tr
                class="border-b border-slate-900"
                classList={{ "bg-emerald-950/30": outlierIds.has(r.auction_id) }}
              >
                <td class="py-1 px-2 text-right font-mono text-slate-100">
                  {fmtPlat(r.buyout_price)}
                </td>
                <td class="py-1 px-2 text-right font-mono text-slate-400">{fmtPlat(r.top_bid)}</td>
                <td class="py-1 px-2 text-right font-mono text-slate-400">{r.re_rolls ?? "—"}</td>
                <td class="py-1 px-2 text-slate-300">{r.polarity ?? "—"}</td>
                <td class="py-1 px-2 text-slate-300">
                  <span class="flex flex-wrap gap-1">
                    <For each={r.attributes}>
                      {(a) => (
                        <span
                          class="text-[10px] px-1 rounded"
                          classList={{
                            "bg-emerald-900/40 text-emerald-200": a.positive,
                            "bg-rose-900/40 text-rose-200": !a.positive,
                          }}
                        >
                          {prettyAttr(a.name)} {a.value > 0 && a.positive ? "+" : ""}{a.value}
                        </span>
                      )}
                    </For>
                  </span>
                </td>
                <td class="py-1 px-2 text-slate-400 font-mono">{r.owner_name ?? "—"}</td>
              </tr>
            )}
          </For>
        </tbody>
      </table>
    </div>
  );
}

function HistorySparkline(props: { rows: { ts: number; median: number | null }[] }) {
  const points = createMemo(() => {
    const ms = props.rows
      .filter((r) => r.median != null)
      .map((r) => ({ ts: r.ts, v: r.median as number }))
      .sort((a, b) => a.ts - b.ts);
    if (ms.length < 2) return "";
    const first = ms[0]!, last = ms[ms.length - 1]!;
    const minTs = first.ts, maxTs = last.ts;
    const minV = Math.min(...ms.map((p) => p.v));
    const maxV = Math.max(...ms.map((p) => p.v));
    const W = 600, H = 80;
    const xRange = Math.max(1, maxTs - minTs);
    const yRange = Math.max(1, maxV - minV);
    return ms.map((p, i) => {
      const x = ((p.ts - minTs) / xRange) * W;
      const y = H - ((p.v - minV) / yRange) * H;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");
  });

  return (
    <Show
      when={points()}
      fallback={<div class="text-sm text-slate-500">{t("rivens.historyEmpty")}</div>}
    >
      <svg viewBox="0 0 600 80" class="w-full" preserveAspectRatio="none">
        <path d={points()} stroke="#10b981" stroke-width="1.5" fill="none" />
      </svg>
    </Show>
  );
}

function prettyAttr(name: string): string {
  return name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
