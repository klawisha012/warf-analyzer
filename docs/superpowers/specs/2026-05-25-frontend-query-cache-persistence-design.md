# Frontend Query Cache Persistence (stale-while-revalidate across page reloads)

**Date:** 2026-05-25
**Status:** Approved (variants chosen by user)
**Scope:** Frontend only — `frontend/src/main.tsx` + 1 new tiny module.

## Problem

Сейчас после reload страницы пользователь видит "Загрузка…" на каждой карточке Dashboard (и аналогично на других роутах). Причина: `@tanstack/solid-query` хранит cache только в памяти. Reload → cache пуст → `createQuery` стартует с `isLoading: true` → fallback в `<Show>` показывает loading-state, пока не придёт ответ с сервера (наш Dashboard cold-cache — 26 секунд).

Цель: после reload данные показываются **мгновенно** из disk-cache, в фоне идёт refetch, обновлённые значения подменяются молча.

## Решение

**TanStack Query persistence через `@tanstack/query-sync-storage-persister` + `persistQueryClient`.** Это официальный механизм TanStack для сохранения cache между сессиями. Backend хранилища — `localStorage` (синхронное чтение → данные доступны на первом рендере → "Загрузка…" не показывается вообще).

### Почему не IndexedDB

IndexedDB даёт больше места (50MB+) но он **асинхронный**. Hydration кэша происходит ПОСЛЕ первого рендера → первый рендер всё равно увидит пустой cache → loading-state мелькнёт. Это противоречит основной цели задачи.

Размер наших payload-ов (десятки KB на всё приложение) — далеко от 5MB лимита localStorage, IndexedDB не нужен.

### Конкретные параметры

| Параметр | Значение | Обоснование |
|----------|----------|-------------|
| `maxAge` | 24 часа | После суток cache отбрасывается — данные Warframe Market успевают устареть. |
| `buster` | значение `version` из `package.json` (сейчас `"0.1.0"`) | При апдейте версии приложения cache инвалидируется автоматически — защита от breaking changes в схеме данных. |
| `staleTime` | 30s (без изменений) | После reload данные из disk-cache считаются stale → автоматический refetch в фоне. |
| Whitelist | всё **кроме** `healthz` | `healthz` рефетчится каждые 5s через `refetchInterval`, кэшить его на диске бессмысленно (и шумно — постоянные writes в localStorage). |
| UI индикатор фонового refetch | нет | По выбору пользователя — тихое молчаливое обновление. |

## Архитектура

### Изменения в `frontend/src/main.tsx`

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";
import { persistQueryClient } from "@tanstack/query-persist-client-core";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { version as appVersion } from "../package.json";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 24 * 60 * 60 * 1000,         // важно: gcTime >= maxAge, иначе persister выкинет нужные entries
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
  maxAge: 24 * 60 * 60 * 1000,
  buster: appVersion,
  dehydrateOptions: {
    shouldDehydrateQuery: (query) => {
      // skip healthz: it refetches every 5s, no point persisting
      const key = query.queryKey[0];
      return key !== "healthz";
    },
  },
});
```

### Зависимости

```bash
npm install @tanstack/query-persist-client-core @tanstack/query-sync-storage-persister
```

Обе — официальные TanStack пакеты, совместимы с `@tanstack/solid-query@^5.62.0`, который уже в проекте.

### TS импорт `version` из package.json

Vite поддерживает JSON-импорты "из коробки", но в `tsconfig.json` может потребоваться `"resolveJsonModule": true`. Если флага нет — добавить.

## Поведение в разных сценариях

| Сценарий | Что видит пользователь |
|----------|----------------------|
| Первый визит (cache пуст) | "Загрузка…" → данные через 1-26s (как сейчас, без изменений). |
| Повторный визит (reload), cache свежий (<24ч) | **Данные мгновенно**. В фоне refetch, через 200-500ms могут молча обновиться. |
| Повторный визит, cache старый (>24ч) | Cache игнорируется → как первый визит. |
| Апдейт `package.json version` | Cache игнорируется → как первый визит (защита от schema breaks). |
| Сетевой сбой при refetch | Данные из cache остаются на экране, ошибка тихая (без `onError`). |
| `healthz` после reload | Как сейчас — стартует с `isLoading: true`, рефетчится каждые 5s. |

## Edge cases

- **`localStorage` quota exceeded:** persister должен молча failover — TanStack-овский `createSyncStoragePersister` ловит quota errors и логирует warn. Размер наших данных это не делает реальной угрозой, но проверить в DevTools после первой сборки.
- **`localStorage` disabled (приватный режим Safari, корп. браузеры):** persister no-op'нется, fallback — поведение как сейчас (показ "Загрузка…"). Никаких крашей.
- **Множественные вкладки:** localStorage shared, последняя запись wins. Не критично — данные one-user, конфликта не будет.
- **SSR:** проекта нет, чисто SPA, `window` всегда доступен.

## Testing plan

Vitest конфига в проекте сейчас нет (нет блока `test` в package.json и нет `*.test.ts(x)` файлов), поэтому unit-тесты для этой фичи добавлять не будем. Верификация — ручная:

1. **First load:** в пустом браузере открыть Dashboard, увидеть "Загрузка…", дождаться данных. В DevTools → Application → localStorage появился ключ `alecaframe-query-cache`.
2. **Reload:** F5. "Загрузка…" не должно быть видно, данные мгновенно. В Network видны фоновые запросы.
3. **24h+ expiry:** в DevTools вручную поменять timestamp в localStorage entry на > 24ч назад → reload → cache игнорируется, "Загрузка…" появляется.
4. **Buster:** изменить `version` в `package.json` на `"0.1.1"`, rebuild, reload → cache игнорируется.
5. **`healthz` not persisted:** в localStorage entry проверить что в `clientState.queries` нет записи с `queryKey: ["healthz"]`.

## Out of scope

- Service Worker / offline mode (отдельная задача).
- Sync между вкладками (BroadcastChannel) — не нужен для one-user app.
- IndexedDB миграция — не нужна пока влезаем в 5MB.
- Кэширование mutations (не используются).
- UI индикатор `isFetching` — пользователь выбрал тихий вариант.

## Файлы под изменение

- `frontend/src/main.tsx` — добавить инициализацию persister'а (~15 строк).
- `frontend/package.json` — две новые зависимости.
- `frontend/tsconfig.json` — возможно `resolveJsonModule: true` (проверить).

Никаких изменений в роутах, компонентах, query keys, fetchers. Persistence — drop-in.
