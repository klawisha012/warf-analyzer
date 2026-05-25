# Phase B.1b: Frontend pages on B.1a endpoints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the SolidJS Hello-World with four real trading pages — Dashboard, Inventory, PrimeParts, Sets — built on top of the B.1a `/wfm/*` and `/me/*` endpoints. Each page is opinionated UI for a specific trader workflow.

**Architecture:** Strict UI-only layer. No backend changes (we may patch one small backend gap noted in B.1a's carry-forward: the "/wfm/orders/{slug}` returns 404 when catalogue is empty" UX issue — a one-shot lazy bootstrap inside `wfm_items` and `wfm_orders`). Frontend uses Solid Router for navigation, TanStack Query for data fetching with TTL-aware refetch, and shared layout/components for visual consistency.

**Tech Stack:** SolidJS 1.9 + Vite 6 + Tailwind 4 + @tanstack/solid-query + @solidjs/router. No new heavy deps. Build still produces a single static bundle served by the nginx container from B.0.

**Out of scope (deferred to B.1c / B.2):** WebSocket subscriptions, real-time push, ApexCharts (history), forecasts, alerts.

---

## File Map

**Create:**
- `frontend/src/api/types.ts` — hand-written TS types matching the B.1a Pydantic response models
- `frontend/src/api/queries.ts` — typed wrapper functions calling `api<T>("/...")` + key factories
- `frontend/src/components/Card.tsx` — generic card with title + slot
- `frontend/src/components/Badge.tsx` — pill badge (variants: neutral / good / warn / bad / vaulted)
- `frontend/src/components/PriceCell.tsx` — single-cell rendering of min/median/spread/buy_max
- `frontend/src/components/ItemRow.tsx` — table row for PricedItemEntry
- `frontend/src/components/ItemCard.tsx` — grid card for PricedItemEntry (Inventory)
- `frontend/src/components/SetRow.tsx` — row for sets-profit table
- `frontend/src/components/Layout.tsx` — sticky header + outlet
- `frontend/src/components/EmptyState.tsx` — generic "no results" placeholder
- `frontend/src/routes/Dashboard.tsx`
- `frontend/src/routes/Inventory.tsx`
- `frontend/src/routes/PrimeParts.tsx`
- `frontend/src/routes/Sets.tsx`
- `frontend/src/lib/format.ts` — `fmtPlat()`, `fmtPercent()`, `fmtRelTime()` utilities

**Modify:**
- `frontend/src/main.tsx` — add 4 routes + Layout wrapper
- `frontend/src/App.tsx` — becomes the Dashboard entry (or shrinks to a stub if dashboard moves into routes/)
- `src/alecaframe_api/wfm/router.py` — single backend tweak: when slug catalogue is empty, trigger a lazy bootstrap inside the `/wfm/items` and `/wfm/orders/{slug}` handlers (one-shot retry on the WFM `/items` endpoint, then re-check)
- `README.md` — update the "Frontend" section with the route list

**No changes:**
- `docker/frontend/Dockerfile` — same multi-stage build; new files picked up automatically
- `docker/frontend/nginx.conf` — already serves `try_files $uri $uri/ /index.html` for SPA fallback

---

## Conventions

- **Commit format:** Conventional Commits.
- **Branch:** `feature/b1b-frontend-pages` (already created from `master` @ `f1e68ad`).
- **Working dir:** `B:\Sync\Programming\projects\aleca frame inventory`.
- **Frontend commands:** run from `frontend/` directory.
- **Verification:** `npm run typecheck && npm run build` after each non-trivial task.
- **Visual language:** follow the existing App.tsx conventions — dark slate background (`bg-slate-950`), card surfaces (`bg-slate-900 border border-slate-800 rounded-2xl p-4`), accent colour `emerald-400` for "good", `rose-400` for "bad", `amber-300` for "warn", `slate-400` for muted.

---

## Task 1: Frontend dependency bump (devtools) + Solid Router multi-route setup

**Files:**
- Modify: `frontend/src/main.tsx`
- (Optional) Modify: `frontend/package.json` if `@tanstack/solid-query-devtools` is desired

- [ ] **Step 1: Optional — add solid-query devtools for development**

```powershell
cd frontend
npm install --save-dev "@tanstack/solid-query-devtools@^5.62.0"
cd ..
```

If install fails (peer-dep), skip — this is purely a DX aid.

- [ ] **Step 2: Replace `frontend/src/main.tsx` with multi-route version**

Open `frontend/src/main.tsx`. Replace its entire contents with:

```typescript
/* @refresh reload */
import { render } from "solid-js/web";
import { lazy } from "solid-js";
import { Router, Route } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";

import Layout from "./components/Layout";
import "./styles.css";

const Dashboard  = lazy(() => import("./routes/Dashboard"));
const Inventory  = lazy(() => import("./routes/Inventory"));
const PrimeParts = lazy(() => import("./routes/PrimeParts"));
const Sets       = lazy(() => import("./routes/Sets"));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

render(
  () => (
    <QueryClientProvider client={queryClient}>
      <Router root={Layout}>
        <Route path="/"            component={Dashboard} />
        <Route path="/inventory"   component={Inventory} />
        <Route path="/prime-parts" component={PrimeParts} />
        <Route path="/sets"        component={Sets} />
      </Router>
    </QueryClientProvider>
  ),
  root,
);
```

- [ ] **Step 3: Verify typecheck still passes (will fail because Layout/routes don't exist yet — that's expected)**

```powershell
cd frontend
npm run typecheck
```

Expected: errors about missing modules `./components/Layout`, `./routes/Dashboard`, etc. We'll fix them in subsequent tasks. Don't commit yet.

- [ ] **Step 4: Defer commit to Task 2**

(We'll commit main.tsx together with Layout + the first route in the next task.)

---

## Task 2: Layout + Dashboard stub + commit "wiring works"

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/routes/Dashboard.tsx` (initial — stub)
- Create: `frontend/src/routes/Inventory.tsx` (stub)
- Create: `frontend/src/routes/PrimeParts.tsx` (stub)
- Create: `frontend/src/routes/Sets.tsx` (stub)
- Delete: `frontend/src/App.tsx` (no longer the entry — moved into routes/Dashboard)

- [ ] **Step 1: Layout**

Create `frontend/src/components/Layout.tsx`:

```typescript
import type { JSX } from "solid-js";
import { A, useLocation } from "@solidjs/router";

type LayoutProps = { children?: JSX.Element };

const NAV = [
  { href: "/",            label: "Dashboard"   },
  { href: "/inventory",   label: "Inventory"   },
  { href: "/prime-parts", label: "Prime Parts" },
  { href: "/sets",        label: "Sets"        },
] as const;

export default function Layout(props: LayoutProps) {
  const loc = useLocation();
  return (
    <div class="min-h-screen text-slate-100 bg-slate-950">
      <header class="sticky top-0 z-10 bg-slate-950/80 backdrop-blur border-b border-slate-800">
        <nav class="max-w-6xl mx-auto px-6 py-3 flex items-center gap-1">
          <span class="font-semibold text-slate-200 mr-4">AlecaFrame</span>
          {NAV.map((item) => (
            <A
              href={item.href}
              end={item.href === "/"}
              class="px-3 py-1.5 rounded-lg text-sm transition-colors"
              classList={{
                "bg-slate-800 text-slate-100": loc.pathname === item.href,
                "text-slate-400 hover:text-slate-100 hover:bg-slate-900":
                  loc.pathname !== item.href,
              }}
            >
              {item.label}
            </A>
          ))}
        </nav>
      </header>
      <main class="max-w-6xl mx-auto px-6 py-6">{props.children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Route stubs (4 files)**

Create `frontend/src/routes/Dashboard.tsx`:

```typescript
export default function Dashboard() {
  return (
    <section>
      <h1 class="text-2xl font-bold mb-4">Dashboard</h1>
      <p class="text-slate-400">Widgets land in Task 7.</p>
    </section>
  );
}
```

Create `frontend/src/routes/Inventory.tsx`:

```typescript
export default function Inventory() {
  return (
    <section>
      <h1 class="text-2xl font-bold mb-4">Inventory</h1>
      <p class="text-slate-400">Grid lands in Task 8.</p>
    </section>
  );
}
```

Create `frontend/src/routes/PrimeParts.tsx`:

```typescript
export default function PrimeParts() {
  return (
    <section>
      <h1 class="text-2xl font-bold mb-4">Prime Parts</h1>
      <p class="text-slate-400">Table lands in Task 9.</p>
    </section>
  );
}
```

Create `frontend/src/routes/Sets.tsx`:

```typescript
export default function Sets() {
  return (
    <section>
      <h1 class="text-2xl font-bold mb-4">Sets</h1>
      <p class="text-slate-400">Set rows land in Task 10.</p>
    </section>
  );
}
```

- [ ] **Step 3: Delete the old App.tsx**

```powershell
Remove-Item "frontend\src\App.tsx"
```

- [ ] **Step 4: Verify build**

```powershell
cd frontend
npm run typecheck
npm run build
cd ..
```

Expected: both succeed. `dist/index.html` exists. Bundle a bit bigger than before (lazy routes add ~3 KB chunks).

- [ ] **Step 5: Optional live check**

```powershell
docker compose build frontend
docker compose up -d frontend
Start-Sleep -Seconds 5
(Invoke-WebRequest http://127.0.0.1:3000/ -UseBasicParsing).StatusCode
```

Expected: 200. Navigate manually to `/inventory`, `/prime-parts`, `/sets` — each shows the stub heading.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/Layout.tsx frontend/src/routes frontend/src/main.tsx
git rm frontend/src/App.tsx
git commit -m "feat(frontend): multi-route layout with 4 page stubs"
```

If `git rm` complains because `App.tsx` was already deleted (via `Remove-Item`), use `git add -A` instead.

---

## Task 3: API types + queries module

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/queries.ts`

- [ ] **Step 1: Types**

Create `frontend/src/api/types.ts`:

```typescript
/** Mirror of `src/alecaframe_api/schemas.py` Pydantic models, hand-maintained.
 *
 * Keep alphabetical by export to make additions easy to spot in diffs.
 */

export type ApiInfo = {
  name: string;
  version: string;
  docs_url: string;
  endpoints: string[];
};

export type HealthResponse = {
  ok: boolean;
  wfm_username: string | null;
  aleca_version: string | null;
  cache: Record<string, unknown>;
};

export type OrderRow = {
  side: "sell" | "buy" | string;
  price: number;
  qty: number;
  user: string;
  status: string;
  reputation: number;
  platform: string;
};

export type OrderBookStats = {
  side: "sell" | "buy" | string;
  online_only: boolean;
  count_orders: number;
  volume_qty: number;
  min_price: number | null;
  p10: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p90: number | null;
  max_price: number | null;
  top5: number[];
};

export type OrderBookResponse = {
  slug: string;
  item_name: string;
  fetched_at: string;
  stale: boolean;
  sell: OrderBookStats;
  buy: OrderBookStats;
  top_orders: OrderRow[];
};

export type PricedItem = {
  unique_name: string;
  name: string;
  slug: string | null;
  count: number | null;
  vaulted: boolean | null;
  sell_min: number | null;
  sell_median: number | null;
  sell_spread: number | null;
  buy_max: number | null;
  estimated_value: number | null;
  stale: boolean;
};

export type PricedItemListResponse = {
  total: number;
  returned: number;
  items: PricedItem[];
};

export type RelistNudge = {
  slug: string;
  item_name: string;
  your_price: number;
  median: number | null;
  top5: number[];
  suggestion: string;
};

export type RelistNudgeResponse = { total: number; items: RelistNudge[] };

export type SetProfitRow = {
  set_slug: string;
  set_name: string;
  set_price: number;
  parts_cost: number;
  tax_estimate: number;
  profit: number;
  missing_parts: Record<string, number>;
  owned_parts: Record<string, number>;
};

export type SetProfitResponse = { total: number; returned: number; items: SetProfitRow[] };

export type WFMItemRef = {
  slug: string;
  item_name: string;
  thumb_url: string | null;
  vaulted: boolean;
  wfm_id: string;
};

export type WFMItemsResponse = { total: number; items: WFMItemRef[] };

export type WtbMatch = {
  slug: string;
  item_name: string;
  your_qty: number;
  buyer: string;
  buyer_status: string;
  buyer_reputation: number;
  offer_price: number;
};

export type WtbMatchResponse = { total: number; items: WtbMatch[] };
```

- [ ] **Step 2: Queries**

Create `frontend/src/api/queries.ts`:

```typescript
import { api } from "./client";
import type {
  ApiInfo, HealthResponse,
  OrderBookResponse,
  PricedItemListResponse,
  RelistNudgeResponse,
  SetProfitResponse,
  WFMItemsResponse,
  WtbMatchResponse,
} from "./types";

/** Query-key factory — keep all keys here so devtools / invalidations are predictable. */
export const keys = {
  info:           () => ["info"] as const,
  healthz:        () => ["healthz"] as const,
  wfmItems:       () => ["wfm", "items"] as const,
  wfmOrders:      (slug: string, opts: { includeOffline: boolean }) =>
    ["wfm", "orders", slug, opts] as const,
  meListings:     () => ["me", "listings"] as const,
  meInventory:    (slot: string, limit: number) => ["me", "inventory-priced", slot, limit] as const,
  mePrimeParts:   (min_count: number) => ["me", "prime-parts-priced", min_count] as const,
  meSetsProfit:   (min_margin: number) => ["me", "sets-profit", min_margin] as const,
  meWtbMatches:   (min_offer: number) => ["me", "wtb-matches", min_offer] as const,
  meRelistNudges: () => ["me", "relist-nudges"] as const,
};

export const fetchers = {
  info: () => api<ApiInfo>("/"),
  healthz: () => api<HealthResponse>("/healthz"),
  wfmItems: () => api<WFMItemsResponse>("/wfm/items"),
  wfmOrders: (slug: string, includeOffline: boolean) =>
    api<OrderBookResponse>(`/wfm/orders/${encodeURIComponent(slug)}?include_offline=${includeOffline ? 1 : 0}`),
  meListings: () => api<unknown>("/me/listings"),
  meInventory: (slot: string, limit: number) =>
    api<PricedItemListResponse>(`/me/inventory-priced?slot=${slot}&limit=${limit}`),
  mePrimeParts: (min_count: number) =>
    api<PricedItemListResponse>(`/me/prime-parts-priced?min_count=${min_count}`),
  meSetsProfit: (min_margin: number) =>
    api<SetProfitResponse>(`/me/sets-profit?min_margin=${min_margin}`),
  meWtbMatches: (min_offer: number) =>
    api<WtbMatchResponse>(`/me/wtb-matches?min_offer=${min_offer}`),
  meRelistNudges: () => api<RelistNudgeResponse>("/me/relist-nudges"),
};
```

- [ ] **Step 3: Verify**

```powershell
cd frontend
npm run typecheck
cd ..
```

Expected: no errors.

- [ ] **Step 4: Commit**

```powershell
git add frontend/src/api/types.ts frontend/src/api/queries.ts
git commit -m "feat(frontend): typed API queries + response types for B.1a endpoints"
```

---

## Task 4: Format helpers + Badge + Card + EmptyState

**Files:**
- Create: `frontend/src/lib/format.ts`
- Create: `frontend/src/components/Badge.tsx`
- Create: `frontend/src/components/Card.tsx`
- Create: `frontend/src/components/EmptyState.tsx`

- [ ] **Step 1: Format helpers**

Create `frontend/src/lib/format.ts`:

```typescript
export function fmtPlat(n: number | null | undefined): string {
  if (n == null) return "—";
  return `${n.toLocaleString("en-US")}p`;
}

export function fmtInt(n: number | null | undefined): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US");
}

export function fmtRelTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const dt = Date.now() - then;
  const s = Math.round(dt / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function spreadPct(min: number | null, median: number | null): number | null {
  if (min == null || median == null || median === 0) return null;
  return Math.round(((median - min) / median) * 100);
}
```

- [ ] **Step 2: Badge component**

Create `frontend/src/components/Badge.tsx`:

```typescript
import type { JSX } from "solid-js";

type Variant = "neutral" | "good" | "warn" | "bad" | "vaulted" | "info";

const VARIANT: Record<Variant, string> = {
  neutral: "bg-slate-800 text-slate-300 border-slate-700",
  good:    "bg-emerald-900/40 text-emerald-300 border-emerald-800",
  warn:    "bg-amber-900/40 text-amber-200 border-amber-800",
  bad:     "bg-rose-900/40 text-rose-300 border-rose-800",
  vaulted: "bg-indigo-900/40 text-indigo-300 border-indigo-800",
  info:    "bg-sky-900/40 text-sky-300 border-sky-800",
};

export default function Badge(props: { variant?: Variant; children: JSX.Element }) {
  const cls = VARIANT[props.variant ?? "neutral"];
  return (
    <span class={`inline-flex items-center text-xs px-2 py-0.5 rounded-md border ${cls}`}>
      {props.children}
    </span>
  );
}
```

- [ ] **Step 3: Card component**

Create `frontend/src/components/Card.tsx`:

```typescript
import type { JSX } from "solid-js";

type CardProps = {
  title?: string;
  subtitle?: string;
  trailing?: JSX.Element;
  children: JSX.Element;
  class?: string;
};

export default function Card(props: CardProps) {
  return (
    <section
      class={`rounded-2xl bg-slate-900 border border-slate-800 p-4 ${props.class ?? ""}`}
    >
      {(props.title || props.subtitle || props.trailing) && (
        <header class="flex items-center justify-between gap-4 mb-3">
          <div>
            {props.title && <h2 class="text-lg font-semibold text-slate-100">{props.title}</h2>}
            {props.subtitle && <p class="text-sm text-slate-400">{props.subtitle}</p>}
          </div>
          {props.trailing}
        </header>
      )}
      {props.children}
    </section>
  );
}
```

- [ ] **Step 4: EmptyState**

Create `frontend/src/components/EmptyState.tsx`:

```typescript
import type { JSX } from "solid-js";

export default function EmptyState(props: {
  title: string;
  hint?: string;
  icon?: JSX.Element;
}) {
  return (
    <div class="text-center py-12 text-slate-400">
      {props.icon && <div class="mb-2 flex justify-center">{props.icon}</div>}
      <div class="text-slate-200 font-medium">{props.title}</div>
      {props.hint && <div class="text-sm mt-1">{props.hint}</div>}
    </div>
  );
}
```

- [ ] **Step 5: Verify**

```powershell
cd frontend
npm run typecheck
cd ..
```

Expected: no errors.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/lib/format.ts frontend/src/components/Badge.tsx frontend/src/components/Card.tsx frontend/src/components/EmptyState.tsx
git commit -m "feat(frontend): shared components (Card, Badge, EmptyState) + format helpers"
```

---

## Task 5: PriceCell + ItemRow + ItemCard + SetRow

**Files:**
- Create: `frontend/src/components/PriceCell.tsx`
- Create: `frontend/src/components/ItemRow.tsx`
- Create: `frontend/src/components/ItemCard.tsx`
- Create: `frontend/src/components/SetRow.tsx`

- [ ] **Step 1: PriceCell**

Create `frontend/src/components/PriceCell.tsx`:

```typescript
import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtPlat, spreadPct } from "../lib/format";

export default function PriceCell(props: { item: PricedItem }) {
  const sp = () => spreadPct(props.item.sell_min, props.item.sell_median);
  return (
    <div class="text-right font-mono">
      <Show
        when={props.item.sell_median != null}
        fallback={<span class="text-slate-500">—</span>}
      >
        <div class="text-slate-100">{fmtPlat(props.item.sell_median)}</div>
        <div class="text-xs text-slate-400">
          min {fmtPlat(props.item.sell_min)}
          <Show when={sp() != null}> · spread {sp()}%</Show>
        </div>
      </Show>
    </div>
  );
}
```

- [ ] **Step 2: ItemRow (table row)**

Create `frontend/src/components/ItemRow.tsx`:

```typescript
import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtInt, fmtPlat } from "../lib/format";
import Badge from "./Badge";
import PriceCell from "./PriceCell";

export default function ItemRow(props: { item: PricedItem }) {
  return (
    <tr class="border-b border-slate-800 hover:bg-slate-900/60">
      <td class="py-2 px-3">
        <div class="text-slate-100">{props.item.name}</div>
        <Show when={props.item.slug}>
          <a
            href={`https://warframe.market/items/${props.item.slug}`}
            target="_blank"
            class="text-xs text-slate-500 hover:text-slate-300 font-mono"
          >
            {props.item.slug}
          </a>
        </Show>
      </td>
      <td class="py-2 px-3 text-right font-mono">{fmtInt(props.item.count)}</td>
      <td class="py-2 px-3">
        <Show when={props.item.vaulted}>
          <Badge variant="vaulted">vaulted</Badge>
        </Show>
        <Show when={props.item.stale}>
          <Badge variant="warn">stale</Badge>
        </Show>
      </td>
      <td class="py-2 px-3"><PriceCell item={props.item} /></td>
      <td class="py-2 px-3 text-right font-mono text-slate-300">
        {fmtPlat(props.item.buy_max)}
      </td>
      <td class="py-2 px-3 text-right font-mono text-slate-100">
        {fmtPlat(props.item.estimated_value)}
      </td>
    </tr>
  );
}
```

- [ ] **Step 3: ItemCard (grid card)**

Create `frontend/src/components/ItemCard.tsx`:

```typescript
import { Show } from "solid-js";
import type { PricedItem } from "../api/types";
import { fmtInt, fmtPlat } from "../lib/format";
import Badge from "./Badge";

export default function ItemCard(props: { item: PricedItem }) {
  const it = () => props.item;
  return (
    <article class="rounded-xl bg-slate-900 border border-slate-800 p-3 hover:border-slate-700 transition-colors">
      <header class="flex items-start justify-between gap-2 mb-2">
        <div>
          <div class="text-slate-100 font-medium">{it().name}</div>
          <Show when={it().slug}>
            <div class="text-xs text-slate-500 font-mono">{it().slug}</div>
          </Show>
        </div>
        <Show when={it().vaulted}>
          <Badge variant="vaulted">vaulted</Badge>
        </Show>
      </header>
      <dl class="grid grid-cols-2 gap-y-1 text-sm">
        <dt class="text-slate-400">Qty</dt>
        <dd class="text-right font-mono text-slate-100">{fmtInt(it().count)}</dd>
        <dt class="text-slate-400">Sell median</dt>
        <dd class="text-right font-mono text-slate-100">{fmtPlat(it().sell_median)}</dd>
        <dt class="text-slate-400">Sell min</dt>
        <dd class="text-right font-mono text-slate-300">{fmtPlat(it().sell_min)}</dd>
        <dt class="text-slate-400">Buy max</dt>
        <dd class="text-right font-mono text-slate-300">{fmtPlat(it().buy_max)}</dd>
        <dt class="text-slate-400">Est. value</dt>
        <dd class="text-right font-mono text-emerald-300">{fmtPlat(it().estimated_value)}</dd>
      </dl>
    </article>
  );
}
```

- [ ] **Step 4: SetRow**

Create `frontend/src/components/SetRow.tsx`:

```typescript
import { For, Show } from "solid-js";
import type { SetProfitRow } from "../api/types";
import { fmtPlat } from "../lib/format";
import Badge from "./Badge";

export default function SetRowComp(props: { row: SetProfitRow }) {
  const profitVariant = () =>
    props.row.profit >= 30 ? "good" : props.row.profit >= 10 ? "info" : "neutral";
  const missing = () => Object.entries(props.row.missing_parts ?? {});
  return (
    <article class="rounded-xl bg-slate-900 border border-slate-800 p-4">
      <header class="flex items-center justify-between gap-3 mb-2">
        <div>
          <div class="text-slate-100 font-semibold">{props.row.set_name}</div>
          <div class="text-xs text-slate-500 font-mono">{props.row.set_slug}</div>
        </div>
        <Badge variant={profitVariant() as never}>+{fmtPlat(props.row.profit)} profit</Badge>
      </header>
      <dl class="grid grid-cols-3 gap-2 text-sm mb-2">
        <div>
          <dt class="text-slate-400 text-xs">Set price</dt>
          <dd class="font-mono text-slate-100">{fmtPlat(props.row.set_price)}</dd>
        </div>
        <div>
          <dt class="text-slate-400 text-xs">Parts cost</dt>
          <dd class="font-mono text-slate-100">{fmtPlat(props.row.parts_cost)}</dd>
        </div>
        <div>
          <dt class="text-slate-400 text-xs">Tax (est.)</dt>
          <dd class="font-mono text-slate-300">{fmtPlat(props.row.tax_estimate)}</dd>
        </div>
      </dl>
      <Show when={missing().length > 0}>
        <div>
          <div class="text-xs text-slate-400 mb-1">To buy:</div>
          <ul class="flex flex-wrap gap-1">
            <For each={missing()}>
              {([slug, qty]) => (
                <li class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">
                  {qty}× {slug}
                </li>
              )}
            </For>
          </ul>
        </div>
      </Show>
    </article>
  );
}
```

- [ ] **Step 5: Verify**

```powershell
cd frontend
npm run typecheck
cd ..
```

Expected: no errors.

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/components/PriceCell.tsx frontend/src/components/ItemRow.tsx frontend/src/components/ItemCard.tsx frontend/src/components/SetRow.tsx
git commit -m "feat(frontend): item display components (PriceCell, ItemRow, ItemCard, SetRow)"
```

---

## Task 6: Dashboard page — 3 widgets

**Files:**
- Modify: `frontend/src/routes/Dashboard.tsx`

- [ ] **Step 1: Implement**

Replace the contents of `frontend/src/routes/Dashboard.tsx` with:

```typescript
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
      {/* Header strip */}
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

      {/* Widgets */}
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
```

- [ ] **Step 2: Verify**

```powershell
cd frontend
npm run typecheck
npm run build
cd ..
```

Expected: no errors. Bundle slightly larger.

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/routes/Dashboard.tsx
git commit -m "feat(frontend): Dashboard page with WTB-matches, set-profits, relist-nudges widgets"
```

---

## Task 7: Inventory page

**Files:**
- Modify: `frontend/src/routes/Inventory.tsx`

- [ ] **Step 1: Implement**

Replace `frontend/src/routes/Inventory.tsx`:

```typescript
import { For, Show, createSignal, createMemo } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import ItemCard from "../components/ItemCard";
import { fetchers, keys } from "../api/queries";

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
```

- [ ] **Step 2: Verify**

```powershell
cd frontend
npm run typecheck
cd ..
```

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/routes/Inventory.tsx
git commit -m "feat(frontend): Inventory page with slot filter + search"
```

---

## Task 8: PrimeParts page

**Files:**
- Modify: `frontend/src/routes/PrimeParts.tsx`

- [ ] **Step 1: Implement**

Replace `frontend/src/routes/PrimeParts.tsx`:

```typescript
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
```

- [ ] **Step 2: Verify**

```powershell
cd frontend
npm run typecheck
cd ..
```

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/routes/PrimeParts.tsx
git commit -m "feat(frontend): PrimeParts table with min-qty filter + total est. value"
```

---

## Task 9: Sets page

**Files:**
- Modify: `frontend/src/routes/Sets.tsx`

- [ ] **Step 1: Implement**

Replace `frontend/src/routes/Sets.tsx`:

```typescript
import { For, Show, createSignal } from "solid-js";
import { createQuery } from "@tanstack/solid-query";
import Card from "../components/Card";
import EmptyState from "../components/EmptyState";
import SetRowComp from "../components/SetRow";
import { fetchers, keys } from "../api/queries";

export default function Sets() {
  const [minMargin, setMinMargin] = createSignal(0);

  const sets = createQuery(() => ({
    queryKey: keys.meSetsProfit(minMargin()),
    queryFn:  () => fetchers.meSetsProfit(minMargin()),
  }));

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3 flex-wrap">
        <h1 class="text-2xl font-bold mr-auto">Buildable sets</h1>
        <label class="text-sm text-slate-400 flex items-center gap-2">
          min&nbsp;profit (p)
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
        fallback={<Card><div class="text-slate-500">Loading…</div></Card>}
      >
        <Show
          when={(sets.data?.items ?? []).length > 0}
          fallback={
            <EmptyState
              title="No profitable sets"
              hint="Either set seeds aren't loaded (B.2) or the market doesn't open a gap right now."
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
```

- [ ] **Step 2: Verify**

```powershell
cd frontend
npm run typecheck
cd ..
```

- [ ] **Step 3: Commit**

```powershell
git add frontend/src/routes/Sets.tsx
git commit -m "feat(frontend): Sets page with min-profit filter"
```

---

## Task 10: Backend tweak — lazy slug bootstrap when catalogue is empty

This addresses B.1a's carry-forward #5: when decrypt-agent is OFF at lifespan and the slug catalogue is empty, `/wfm/orders/{slug}` returns a misleading 404 ("unknown slug") instead of triggering a retry.

**Files:**
- Modify: `src/alecaframe_api/wfm/router.py`

- [ ] **Step 1: Add a helper at the top of `wfm/router.py` (after the existing helpers)**

Inside `src/alecaframe_api/wfm/router.py`, add a helper near the other helpers (after `_order_to_row`):

```python
async def _ensure_slug_catalogue(client, resolver) -> None:
    """Lazy-bootstrap the slug catalogue if it's empty.

    Lifespan tries this once; if it failed (e.g. agent down), the catalogue
    stays empty for the lifetime of the process. This helper retries on the
    first endpoint hit that needs it. Best-effort — if WFM is unreachable too,
    we just leave the resolver empty and the endpoint surfaces the WFM error.
    """
    if resolver.size() > 0:
        return
    try:
        items = await client.get_items()
        resolver.load(items)
    except Exception as e:
        log.warning("lazy slug bootstrap failed: %s", e)
```

You'll also need `log` imported. Add at the top of the file (if not already there):

```python
import logging
log = logging.getLogger("alecaframe.wfm.router")
```

- [ ] **Step 2: Invoke the helper in `wfm_orders` BEFORE the `resolver.by_slug(slug)` check**

Find:

```python
@router.get(
    "/wfm/orders/{slug}", response_model=OrderBookResponse,
    summary="Current WFM order book for a slug",
)
async def wfm_orders(
    slug: str,
    client: WFMClientDep,
    resolver: SlugResolverDep,
    include_offline: Annotated[bool, Query(description="Include offline orders")] = False,
    fresh: Annotated[bool, Query(description="Bypass cache")] = False,
) -> OrderBookResponse:
    item = resolver.by_slug(slug)
    if item is None:
        raise HTTPException(404, f"unknown slug '{slug}'")
```

Insert the bootstrap before the lookup:

```python
async def wfm_orders(
    slug: str,
    client: WFMClientDep,
    resolver: SlugResolverDep,
    include_offline: Annotated[bool, Query(description="Include offline orders")] = False,
    fresh: Annotated[bool, Query(description="Bypass cache")] = False,
) -> OrderBookResponse:
    await _ensure_slug_catalogue(client, resolver)
    item = resolver.by_slug(slug)
    if item is None:
        raise HTTPException(404, f"unknown slug '{slug}'")
```

- [ ] **Step 3: Also bootstrap in `wfm_items` itself (so first hit fills the catalogue)**

Find:

```python
@router.get(
    "/wfm/items", response_model=WFMItemsResponse,
    summary="WFM slug catalogue (24h cache)",
)
async def wfm_items(client: WFMClientDep) -> WFMItemsResponse:
    try:
        items = await client.get_items()
    except WFMError as e:
        raise HTTPException(503, str(e)) from e
```

Add the SlugResolver dependency and feed the bootstrap into the same call:

```python
@router.get(
    "/wfm/items", response_model=WFMItemsResponse,
    summary="WFM slug catalogue (24h cache)",
)
async def wfm_items(client: WFMClientDep, resolver: SlugResolverDep) -> WFMItemsResponse:
    try:
        items = await client.get_items()
    except WFMError as e:
        raise HTTPException(503, str(e)) from e
    # Side effect: refresh the in-memory resolver so subsequent /wfm/orders/{slug}
    # works even if lifespan bootstrap failed.
    resolver.load(items)
    return WFMItemsResponse(
        total=len(items),
        items=[
            WFMItemRef(
                slug=i.slug, item_name=i.item_name, thumb_url=i.thumb_url,
                vaulted=i.vaulted, wfm_id=i.wfm_id,
            )
            for i in items
        ],
    )
```

- [ ] **Step 4: Verify unit tests still pass**

```powershell
uv run pytest -v
```

Expected: 50 passed, 10 deselected.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/wfm/router.py
git commit -m "fix(wfm-router): lazy slug-catalogue bootstrap when lifespan bootstrap failed"
```

---

## Task 11: Live smoke + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rebuild & restart frontend (and backend if Task 10 changed it)**

```powershell
docker compose build backend frontend
docker compose up -d --force-recreate backend frontend
Start-Sleep -Seconds 10
```

- [ ] **Step 2: Smoke test the four pages**

Open `http://127.0.0.1:3000/` — verify:
- Dashboard renders with 3 widgets (data may be empty if agent off; layout still correct)
- `/inventory` shows slot tabs + search box
- `/prime-parts` shows table with filter
- `/sets` shows set rows or empty state

```powershell
$pages = @("/", "/inventory", "/prime-parts", "/sets")
foreach ($p in $pages) {
    $r = Invoke-WebRequest "http://127.0.0.1:3000$p" -UseBasicParsing
    "$p -> $($r.StatusCode)"
}
```

Expected: all return 200 (Vite/nginx SPA fallback serves the index for every route).

- [ ] **Step 3: README — frontend section**

In `README.md`, find the `## Endpoints` or `## Структура` section. Insert a new section just after the architecture diagram (or near "Запуск"):

```markdown
## Frontend pages (B.1b)

После `./scripts/start-stack.ps1` открой `http://127.0.0.1:3000`:

| Route | Что показывает |
|---|---|
| `/` | Dashboard: Health/WFM-user/AlecaFrame-version + три виджета (Top WTB matches, Top set profits, Re-list nudges) |
| `/inventory` | Сетка карточек инвентаря с фильтром по slot и поиском по имени |
| `/prime-parts` | Таблица прайм-партов с min-qty фильтром и общим est. value |
| `/sets` | Buildable сеты с фильтром min profit |

Маршрутизация на @solidjs/router, fetching на @tanstack/solid-query (TTL 30s, no refetch-on-focus).
SPA fallback в nginx → каждый маршрут возвращает 200, клиент сам рендерит.
```

- [ ] **Step 4: Commit**

```powershell
git add README.md
git commit -m "docs: document B.1b frontend pages in README"
```

---

## Task 12: Final live verification + cleanup

**Files:** none

- [ ] **Step 1: Full stack up + manual flow**

```powershell
./scripts/start-stack.ps1 -Detached
```

Open `http://127.0.0.1:3000`. Click through every nav item. Confirm:
- Header stays sticky on scroll
- Active nav item highlighted
- No 404s in browser DevTools network tab
- API calls go to `/api/...` with 200 (or 503 if agent off, with graceful UI fallback)

- [ ] **Step 2: Full pytest pass**

```powershell
uv run pytest -v
```

Expected: 50 unit, 10 e2e deselected.

- [ ] **Step 3: Optional — run e2e if agent is up**

```powershell
uv run pytest -m e2e -v
```

Expected: 10/10 pass (B.0 5 + B.1a 5). The B.1a 3 that previously 503'd with agent off should now 200.

- [ ] **Step 4: Cleanup** — nothing to commit; verification only.

---

## Definition of Done — Phase B.1b

- `npm run typecheck` and `npm run build` succeed
- All four routes (`/`, `/inventory`, `/prime-parts`, `/sets`) render and return 200 over the nginx proxy
- Dashboard shows three widget cards (real data when agent + WFM up, graceful empty-state otherwise)
- Inventory grid filters by slot and by search query
- PrimeParts table sorts by est. value desc with total value summary
- Sets page filters by min profit
- Backend `/wfm/orders/{slug}` no longer returns misleading 404 when catalogue is empty — it auto-bootstraps on first hit
- pytest still 50/50 unit tests
- e2e green when agent + WFM are reachable

---

## Self-Review Notes

**Spec coverage** (against design doc §6.4 — Phase B.1 frontend pages):
- ✅ Dashboard with sticky header + 3 widget cards (WTB matches, set profits, re-list nudges)
- ✅ Inventory: search + filter (slot/category/q), grid of cards
- ✅ PrimeParts: table with name, qty, vaulted badge, WTS, WTB, spread, est. value
- ✅ Sets: list of buildable sets with profit calculation
- ⏭ Real-time updates per visible item — deferred to B.1c
- ⏭ ApexCharts — not used yet; lands in B.2 (history charts)
- ⏭ PM-template button on set cards — deferred to B.1c (when listing actions exist)

**Type / name consistency:**
- `PricedItem` type used by `ItemCard`, `ItemRow`, `PriceCell` — same shape, no aliasing
- `SetProfitRow` type matches backend `SetProfitRowModel` field-for-field
- `keys.*` query-key factory functions used consistently across all routes
- `fmtPlat(n)` is the single plat formatter — no inline `${n}p` template strings in components

**Scope:** no scope creep into B.1c (real-time) or B.2 (history). One backend tweak (lazy bootstrap) is included because it's a UX blocker for B.1b's live smoke test.

**Open assumption to verify during execution:**
- `@solidjs/router` v0.15 supports the `Router root={Layout}` syntax. If the API has changed, alternative is to render `Layout` as a parent route element wrapping the children. Adapt if needed.

---

**End of Phase B.1b plan.** B.1c (real-time wiring) plan follows after B.1b lands.
