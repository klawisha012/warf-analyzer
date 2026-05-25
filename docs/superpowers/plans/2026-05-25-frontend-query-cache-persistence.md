# Frontend Query Cache Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После reload страницы данные TanStack Query показываются мгновенно из disk-cache, в фоне идёт refetch — "Загрузка…" исчезает на повторных визитах.

**Architecture:** Single-file change в `frontend/src/main.tsx`. Используем официальный TanStack механизм `persistQueryClient` + `createSyncStoragePersister` поверх `window.localStorage`. Синхронное чтение → данные доступны на первом рендере. Healthz исключаем из persist через `dehydrateOptions.shouldDehydrateQuery`. Cache buster — версия из `package.json`.

**Tech Stack:** SolidJS, `@tanstack/solid-query@^5.62.0`, новые `@tanstack/query-persist-client-core` + `@tanstack/query-sync-storage-persister`, Vite 6, TypeScript.

**Spec:** `docs/superpowers/specs/2026-05-25-frontend-query-cache-persistence-design.md`

---

## File Structure

- **Modify:** `frontend/package.json` — две новые prod-зависимости.
- **Modify:** `frontend/src/main.tsx` — расширить инициализацию `QueryClient`, добавить persister, вызвать `persistQueryClient(...)`.
- **Не трогаем:** routes, components, hooks, api/queries. Persistence — drop-in.

`frontend/tsconfig.json` уже содержит `"resolveJsonModule": true` — отдельной задачи на это нет.

---

### Task 1: Install dependencies

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] **Step 1: Install both TanStack persistence packages**

Run from `frontend/`:

```bash
npm install @tanstack/query-persist-client-core @tanstack/query-sync-storage-persister
```

Expected: `package.json` `dependencies` получает обе записи. Минорная версия должна совпадать с уже установленным `@tanstack/solid-query` (`^5.62.0`) — оба пакета следуют общему major v5.

- [ ] **Step 2: Verify versions installed**

```bash
node -e "const p=require('./package.json'); console.log(p.dependencies['@tanstack/query-persist-client-core'], p.dependencies['@tanstack/query-sync-storage-persister'])"
```

Expected output: две строки вида `^5.xx.x ^5.xx.x` (точные минорные могут отличаться, важен major `5`).

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps(frontend): add @tanstack/query-persist-client-core + sync-storage-persister"
```

---

### Task 2: Wire up persistence in main.tsx

**Files:**
- Modify: `frontend/src/main.tsx` (целиком переписать секцию инициализации QueryClient)

- [ ] **Step 1: Replace the QueryClient block with persistence-enabled version**

Заменить текущий блок:

```tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
```

на:

```tsx
import { persistQueryClient } from "@tanstack/query-persist-client-core";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { version as appVersion } from "../package.json";

const ONE_DAY_MS = 24 * 60 * 60 * 1000;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: ONE_DAY_MS,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const persister = createSyncStoragePersister({
  storage: window.localStorage,
  key: "alecaframe-query-cache",
});

persistQueryClient({
  queryClient,
  persister,
  maxAge: ONE_DAY_MS,
  buster: appVersion,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) =>
      query.queryKey[0] !== "healthz" && query.state.status === "success",
  },
});
```

Импорты `persistQueryClient`, `createSyncStoragePersister`, `version` добавить рядом с существующим импортом `QueryClient` сверху файла, в правильном алфавитном/группированном порядке (после `import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";`).

**Почему `query.state.status === "success"`:** не хотим сохранять `error` или `pending` записи — они только испортят hydration.

**Почему `gcTime` важно:** TanStack Query по умолчанию gc-ит unused queries через 5 минут. Persister пишет на диск только то что живо в памяти → если `gcTime < maxAge`, на диске окажутся протухшие данные. Выравниваем оба в 24ч.

- [ ] **Step 2: Verify TypeScript compiles**

Run from `frontend/`:

```bash
npm run typecheck
```

Expected: zero errors. Если есть ошибка про `version` из `package.json` — `resolveJsonModule` уже включён в `tsconfig.json:17`, должно работать. Если падает на `query.state.status` — проверить что версия `@tanstack/query-persist-client-core` точно `^5.x` (типы там одинаковые с `solid-query`).

- [ ] **Step 3: Verify build succeeds**

```bash
npm run build
```

Expected: чистая сборка, в output появляется bundle с persister-кодом (~5-10 KB gzip добавятся).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.tsx
git commit -m "feat(frontend): persist query cache to localStorage (SWR across reloads)"
```

---

### Task 3: Manual verification in browser

**Files:** нет изменений в коде, только наблюдение.

Backend должен быть поднят (docker compose up) и Dashboard должен возвращать данные. Frontend dev-сервер запустить отдельно: `npm run dev` из `frontend/`.

- [ ] **Step 1: First load — cache cold**

1. Открыть приложение в новой incognito-вкладке (чистый localStorage).
2. Открыть DevTools → Application → Local Storage → выбранный origin.
3. Зайти на Dashboard `/`.

Expected:
- Видна "Загрузка…" в WTB / Sets / Nudges карточках 1-26s (как сейчас, baseline).
- После прихода данных в localStorage появляется ключ `alecaframe-query-cache` с JSON-блобом.
- Inspect JSON: внутри `clientState.queries` есть entries с `queryKey: ["me", "wtb-matches", ...]`, `["me", "sets-profit", ...]`, `["me", "relist-nudges"]`. **Не должно быть** `queryKey: ["healthz"]`.

- [ ] **Step 2: Reload — cache warm**

Hit F5 / Ctrl+R.

Expected:
- "Загрузка…" **не появляется** в WTB / Sets / Nudges карточках — данные сразу видны.
- В Network panel видны фоновые запросы `/api/me/wtb-matches`, `/api/me/sets-profit`, `/api/me/relist-nudges` — refetch идёт.
- Healthz всё равно стартует с `…` (это OK — мы его не персистим, это и в спеке).

- [ ] **Step 3: Expiry test — maxAge**

1. В DevTools → Application → Local Storage → найти `alecaframe-query-cache`.
2. Скопировать значение, в начале JSON есть `"timestamp": <number>`. Заменить на timestamp 25 часов назад: `Date.now() - 25*60*60*1000`. Например через консоль:

```js
const k = "alecaframe-query-cache";
const v = JSON.parse(localStorage.getItem(k));
v.timestamp = Date.now() - 25*60*60*1000;
localStorage.setItem(k, JSON.stringify(v));
```

3. Reload.

Expected: "Загрузка…" появляется (cache отброшен по maxAge).

- [ ] **Step 4: Buster test — version bump**

1. После того как cache снова прогрелся (step 2 повторить), не закрывая браузер изменить `frontend/package.json` `version` с `"0.1.0"` на `"0.1.1"`.
2. Перезапустить dev-сервер (`Ctrl+C` → `npm run dev` снова — Vite пересоберёт с новой версией).
3. Reload страницу.

Expected: "Загрузка…" появляется (buster mismatch → cache отброшен).

4. Вернуть `version` обратно в `"0.1.0"`, не коммитить тестовое изменение.

- [ ] **Step 5: Sanity — no console errors**

Throughout все шаги выше — console чистая (нет красных error-ов от TanStack или persister-а).

Если все 5 шагов прошли — фича работает. Если что-то отвалилось — открыть `docs/superpowers/specs/2026-05-25-frontend-query-cache-persistence-design.md` секцию "Edge cases" и проверить совпадает ли симптом.

---

## Self-Review notes

**Spec coverage:**
- maxAge 24ч → Task 2 step 1 (константа `ONE_DAY_MS`), Task 3 step 3.
- buster version → Task 2 step 1 (`import { version }`), Task 3 step 4.
- staleTime 30s → Task 2 step 1 (сохраняется как было).
- whitelist всё кроме healthz → Task 2 step 1 (`shouldDehydrateQuery`), Task 3 step 1 verification.
- No UI индикатор fetching → ничего не делаем в компонентах, спеком разрешено.
- localStorage не IndexedDB → Task 1 (`query-sync-storage-persister` — это именно localStorage).
- gcTime alignment → Task 2 step 1 (явный `gcTime: ONE_DAY_MS` + объяснение почему).

**Что отдельно подсветил по сравнению со спекой:**
- Добавил фильтр `query.state.status === "success"` — спека этого не требовала явно, но мы не хотим персистить error/pending. Не противоречит спеке.
- `gcTime` alignment — критичный нюанс который в спеке упомянут только как "default" — здесь явно фиксируем в коде.

**No placeholders:** проверено, все шаги содержат конкретный код / команды / ожидаемый output.

**Type consistency:** все имена (`queryClient`, `persister`, `ONE_DAY_MS`, `appVersion`) используются единообразно. `shouldDehydrateQuery` сигнатура соответствует TanStack v5 типам (берёт `Query`, возвращает `boolean`).
