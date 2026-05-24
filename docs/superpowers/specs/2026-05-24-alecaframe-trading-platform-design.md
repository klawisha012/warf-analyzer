# AlecaFrame Trading Platform — Design

**Дата:** 2026-05-24
**Статус:** draft, ожидает ревью пользователя
**Проект:** `B:\Sync\Programming\projects\aleca frame inventory`
**Предыдущий статус:** работающий FastAPI backend с 17 эндпоинтами поверх локального
кеша AlecaFrame (`lastData.dat` / `deltas.dat` → JSON через `AlecaFrameClientLib.dll`).

---

## 1. Context & Goals

Текущий backend читает Warframe-инвентарь оффлайн (без запуска AlecaFrame), но не
знает о ценах на warframe.market и не помогает торговать. Цель — превратить
его в **личный торговый кокпит**: дашборд + история + сигналы + алерты + прогнозы
цен, с UI на SolidJS и event-driven инфраструктурой (RabbitMQ, Redis,
Centrifugo) в docker-compose.

**Кого обслуживаем:** одного пользователя (single-tenant), торгует на PC-платформе
warframe.market, под Windows-хостом (DLL для расшифровки крутится только там).

**Style торговли в фокусе** (от важного к менее):
1. Флиппинг прайм-партов и сетов (основной volume)
2. Ривены (high skill ceiling, в Approach C, не в этом spec-е)
3. Vault-спекуляции (long-term holds, есть индикатор в B.3)

**Что НЕ цель:**
- Multi-user / SaaS / публичный сервис
- Multi-platform (Xbox/PS/Switch) — конфигурируется, но primary PC
- LLM-прогнозирование (классическая статистика лучше для этой задачи; LLM
  отложен в Approach C для NLP/PM-шаблонов)

---

## 2. Phasing

Дизайн разбит на 4 фазы, каждая ship-able и valuable сама по себе.

| Фаза | Содержание | Размер (дней) |
|---|---|---|
| **B.0** | Docker-compose инфра (redis, rabbit, centrifugo) + decrypt-agent + frontend skeleton + миграция backend в контейнер | 4-6 |
| **B.1** | WFM-клиент (REST+WS) + on-demand эндпоинты + первые 4 страницы UI | 7-10 |
| **B.2** | SQLite-история + signal engine + графики (ApexCharts) | 10-14 |
| **B.3** | Statistical forecasts + alert engine + Centrifugo wiring в UI + desktop toasts | 7-10 |

После B.3 — review point. Дальше — Approach C (рывены, Telegram, опц. LLM) или
заморозка.

---

## 3. Architecture

### 3.1 Constraint и решение

`AlecaFrameClientLib.dll` (расшифровка `.dat`) запускается только под Windows
через `pwsh`. Backend хотим в docker → значит decrypt вынесем в отдельный
host-процесс.

**decrypt-agent** — мини-сервис на хосте:
- Python FastAPI, ~50 строк, запуск через `uv run alecaframe-decrypt-agent`
- UI: system tray icon (pystray) с пунктами `Refresh`, `Open data folder`, `Quit`
- Эндпоинты: `POST /refresh` (вызывает `dump_inventory.ps1`), `GET /wfm-token`,
  `POST /toast` (для B.3 алертов), `GET /healthz`
- Пишет в `./data/{lastData,deltas,_meta}.json` — эта папка mount-ится в backend
  как volume

Backend в контейнере общается с агентом через `host.docker.internal:8788`.

### 3.2 Сервисы docker-compose

| Service | Image | Порты (host loopback) | Volumes | Замечание |
|---|---|---|---|---|
| `redis` | redis:7-alpine | 6379 | redis-data | maxmemory 256MB, allkeys-lru, AOF |
| `rabbitmq` | rabbitmq:4-management-alpine | 5672, 15672 | rabbitmq-data | definitions.json — декларативно exchanges/queues |
| `centrifugo` | centrifugo/centrifugo:v6 | 8000 | config.json | JWT-auth, presence on |
| `backend` | local build (python:3.13-slim + uv) | 8765 | `./data:/data` | extra_hosts host.docker.internal |
| `poller` | тот же образ что backend | — | `./data:/data:ro` | другой CMD: `uv run alecaframe-poller` |
| `frontend` | local multi-stage (node:22 → nginx:alpine) | 3000 | — | nginx проксирует /api → backend, /connection → centrifugo |

Все опубликованные порты bind-ятся на `127.0.0.1` (не наружу).

### 3.3 На хосте

| Process | Команда | Что |
|---|---|---|
| `decrypt-agent` | `uv run alecaframe-decrypt-agent` | tray app, pwsh+DLL bridge |
| `docker compose up -d` | — | вся остальная инфра |

Запуск: `scripts/start-stack.ps1` стартует agent в фоне (если не запущен) и
поднимает compose.

### 3.4 Module layout

```
aleca frame inventory/
├── docker-compose.yml
├── .env.example
├── docker/
│   ├── backend/Dockerfile
│   ├── poller/Dockerfile
│   ├── frontend/{Dockerfile, nginx.conf}
│   ├── centrifugo/config.json
│   ├── rabbitmq/definitions.json
│   └── redis/redis.conf
├── pyproject.toml
├── scripts/
│   ├── dump_inventory.ps1
│   └── start-stack.ps1
├── src/
│   ├── alecaframe_api/                 # backend
│   │   ├── main.py
│   │   ├── config.py                   # Settings via pydantic-settings
│   │   ├── bridge.py                   # читает JSON, HTTP-call agent для refresh
│   │   ├── naming.py
│   │   ├── schemas.py
│   │   ├── infra/
│   │   │   ├── broker.py               # aio-pika producer/consumer
│   │   │   ├── cache.py                # redis.asyncio
│   │   │   └── push.py                 # Centrifugo HTTP publisher
│   │   ├── wfm/
│   │   │   ├── router.py               # APIRouter c /wfm /me /signals /forecast /alerts /history
│   │   │   ├── client.py               # REST WFM-client
│   │   │   ├── socket.py               # WS WFM-client (poller-only)
│   │   │   ├── slugs.py                # uniqueName <-> WFM slug
│   │   │   ├── poller.py               # entry: scheduler + WS listener + cmd consumer
│   │   │   ├── prices.py               # B.1
│   │   │   ├── sets.py                 # B.1
│   │   │   ├── history.py              # B.2
│   │   │   ├── signals.py              # B.2
│   │   │   ├── forecast.py             # B.3
│   │   │   └── alerts.py               # B.3
│   │   └── db/
│   │       ├── schema.sql
│   │       └── repo.py
│   └── decrypt_agent/                  # host-side
│       ├── __init__.py
│       └── main.py                     # FastAPI + pystray + pwsh wrapper
├── frontend/                           # SolidJS
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── routes/                     # Dashboard, Inventory, PrimeParts, Sets, History, Signals, Forecasts, Alerts
│       ├── components/
│       ├── api/{client.ts, centrifuge.ts}
│       └── styles/
└── data/                               # gitignored
    ├── lastData.json, deltas.json, _meta.json
    └── wfm_history.db
```

### 3.5 URL namespaces (backend)

| Prefix | Назначение | Появляется |
|---|---|---|
| `/wfm/*` | прокси-стиль над WFM (orders, items, profile, statistics) | B.1 |
| `/me/*` | твоё ∩ рынок (listings, inventory-priced, prime-parts-priced, sets-profit, wtb-matches, relist-nudges, dashboard-actions) | B.1-B.2 |
| `/signals/*` | derived signal feed + active list | B.2 |
| `/history/*` | time series по slug | B.2 |
| `/forecast/*` | прогнозы (statistical / trend / prophet) | B.3 |
| `/alerts/*` | rules CRUD + history + test-fire | B.3 |
| (существующие) `/warframes`, `/mods`, `/prime-parts`, …  | инвентарь без рынка | as-is |

### 3.6 URL namespaces (frontend)

| Route | Phase |
|---|---|
| `/` Dashboard | B.1 |
| `/inventory` | B.1 |
| `/prime-parts` | B.1 |
| `/sets` | B.1 |
| `/history/:slug` | B.2 |
| `/signals` | B.2 |
| `/forecasts` | B.3 |
| `/alerts` | B.3 |

---

## 4. WFM Client

Единственный модуль, который ходит в `api.warframe.market`. Изолирован
интерфейсом — заменим транспорт без переписывания фич.

### 4.1 Endpoints WFM

| WFM endpoint | Где зовём | TTL (Redis) |
|---|---|---|
| `GET /v1/items` | старт poller (slug-каталог) | 24ч |
| `GET /v1/items/{slug}/orders` | B.1: цены | 60с |
| `GET /v1/profile/{user}` | B.1: репутация | 5мин |
| `GET /v1/profile/{user}/orders` | B.1: твои listings | 60с |
| `GET /v1/items/{slug}/statistics` | B.2: WFM-side история | 5мин |
| `GET /v1/auctions/search` | Approach C: ривены | — |
| `POST /v1/profile/orders` | Stretch B.1: создать WTS | — |
| `WSS /socket?platform=pc` | B.1: live order book | — |
| `POST /auth/signin` | fallback при 401 | — |

### 4.2 Auth

- JWT берём через `GET http://host.docker.internal:8788/wfm-token` (агент читает
  `%LOCALAPPDATA%\AlecaFrame\WFMarketToken.tk`)
- Заголовок: `Authorization: JWT <token>` (с префиксом `JWT`, не `Bearer`)
- Дополнительно: `Language: en`, `Platform: pc` (конфигурируется)
- Парсим `exp` claim → если < 24ч до истечения, structlog warning
- При 401 — clean error в UI «открой AlecaFrame, перелогинься, нажми refresh».
  `/auth/signin` flow отложен.

### 4.3 Rate-limit

- `aiolimiter.AsyncLimiter(3, 1.0)` (3 req/s, WFM рекомендация)
- Лимитер шарится между backend и poller через Redis Lua-script
  (атомарный token bucket)
- 429 → exp backoff с jitter (base 1s, max 60s), 3 retry, потом fail
- Все retries увеличивают latency, метрика logged

### 4.4 Cache (Redis L1)

- Ключи: `wfm:orders:{slug}:{online_only}`, `wfm:items`, `wfm:profile:{user}`,
  `wfm:nx:{slug}` (negative cache, TTL 1ч для 404)
- Хранится raw JSON + `Last-Modified` + `etag` (если WFM отдаёт)
- На повторе шлём `If-Modified-Since` → если 304, продлеваем TTL
- Cache-bypass: query `?fresh=1` на наших API → `force_revalidate=True`
- Stale-while-revalidate: при истечении TTL отдаём cached + асинхронно обновляем

### 4.5 Slug resolver

- Старт poller-а: `GET /v1/items` → `wfm_items` SQLite table + cache в Redis
- Forward (slug → metadata): прямой lookup
- Reverse (uniqueName → slug): нормализация `CamelCase → snake_case`,
  удаление `Blueprint` суффикса, спец-кейсы для `Prime`, `Vandal`, `Wraith`,
  `Umbra`. Fallback — fuzzy match по item_name через AlecaFrame name DB.
- Ambiguous resolution → лог + override через `data/slug_overrides.json`

### 4.6 Класс

```python
class WFMClient:
    def __init__(self, redis, settings: Settings, token_provider): ...
    async def get_orders(self, slug, *, online_only=True, fresh=False) -> OrdersResponse: ...
    async def get_items(self) -> list[ItemRef]: ...
    async def get_profile(self, user) -> ProfileResponse: ...
    async def get_profile_orders(self, user) -> ProfileOrdersResponse: ...
    async def get_statistics(self, slug, *, fresh=False) -> StatisticsResponse: ...
    async def resolve_slug(self, unique_name) -> str | None: ...
    async def _request(self, method, path, *, cache_key, cache_ttl, fresh): ...

class WFMSocketClient:
    """Long-running WS, поднимается в poller, публикует в RabbitMQ."""
    async def run(self, slugs: list[str]) -> None: ...  # reconnect loop
```

---

## 5. Phase B.0 — Foundation

**Deliverables:**
1. `docker-compose.yml` поднимает redis + rabbitmq + centrifugo + backend + poller +
   frontend, всё health-check OK
2. `decrypt-agent` запускается через `uv run alecaframe-decrypt-agent`, tray-icon
   видим, `POST /refresh` работает
3. Существующие 17 эндпоинтов backend-а доступны на `http://localhost:3000/api/*`
   (через nginx-прокси) и `http://localhost:8765/*` (прямо)
4. Frontend на `http://localhost:3000` показывает Hello World со списком endpoint-ов
5. `scripts/start-stack.ps1` запускает agent + compose одной командой

**Что НЕ в B.0:** ни одного нового endpoint-а, ни одной WFM-фичи. Только инфра.

---

## 6. Phase B.1 — On-demand views

### 6.1 Backend endpoints (новые)

| Endpoint | Назначение |
|---|---|
| `GET /wfm/orders/{slug}?include_offline=0&fresh=0` | прокси WFM orders с агрегациями (min/p10/median/p90/max/volume) |
| `GET /wfm/items` | slug-каталог из cache |
| `GET /wfm/profile/{user}` | репутация, registered_at, статус |
| `GET /me/listings` | твои активные orders с обогащением (item_name, current_top5) |
| `GET /me/inventory-priced?slot=warframe\|weapon\|all` | инвентарь + текущая цена per-item |
| `GET /me/prime-parts-priced` | существующий /prime-parts + min/median/spread/vault-flag |
| `GET /me/sets-profit?min_margin=10` | сеты которые ты можешь собрать + profit |
| `GET /me/wtb-matches?min_offer=10p` | WTB ордера на items в твоём инвентаре |
| `GET /me/relist-nudges` | твои listings ушли из top-5 или ниже медианы |

**Stretch (опциональный B.1, иначе в B.3):**
- `POST /wfm/listings` — создать WTS (требует write-токен)
- `DELETE /wfm/listings/{id}`

### 6.2 Set composition

Таблица `set_compositions` строится **в backend lifespan на первом старте**
(и при смене версии AlecaFrame, определяется через `_meta.json.aleca_version`)
из AlecaFrame `cachedData/json/{Warframes,Primary,Secondary,Melee}.json`
(поле `components`). Profit = `set_price - sum(part_floor_prices) - tax(0.1p × parts)`.

Tax-формула WFM: 1% от plat-стоимости трейда + ducat-equivalent (для прайм-партов
обычно ~10 dukat на парт, в plat-эквиваленте ~0.1p). В первой итерации фиксируем
flat 0.1p × parts, в B.2 уточним по реальным трейдам.

### 6.3 WebSocket integration (B.1)

- В poller: `WFMSocketClient.run(slugs)` — long-running asyncio task
- Список подписки = **union** трёх множеств:
  1. slugs которые есть в твоём инвентаре (из `lastData.json`, resolved через `slugs.py`)
  2. slugs твоих активных listings (`/me/listings`)
  3. ручной watchlist в `data/watchlist.txt` (по одному slug на строку, опционально)
- Лимит подписки 50 slug-ов одновременно (WFM-ограничение); если union больше —
  приоритизация: твои listings > inventory > watchlist; остатки fallback на REST polling
- Каждое event → Redis update + RabbitMQ publish `wfm.live.orders`
- Backend consumer → recompute affected signals (B.2 пустые) → Centrifugo publish
  `wfm.orders.{slug}`

### 6.4 Frontend pages

| Route | Содержимое | Real-time |
|---|---|---|
| `/` Dashboard | sticky header (plat/credits/MR), 3 widget-карточки: «Top 5 WTB matches», «Top 5 set profits», «Top 5 re-list nudges» | yes — `system.refresh` + `wfm.orders.*` для видимых |
| `/inventory` | search/filter (slot/category/vaulted/q) + grid карточек с ценой | top-10 visible |
| `/prime-parts` | таблица как на скрине AlecaFrame: name, qty, vaulted, WTS, WTB, spread, margin | yes |
| `/sets` | список собираемых сетов: parts → price → profit, action «PM template» копирует в clipboard | per-part |

ApexCharts ещё не появляется — только числа и значки.

### 6.5 Definition of done

- `scripts/start-stack.ps1` поднимает всё, `/healthz` зелёный
- Dashboard показывает реальные plat/credits/MR и три виджета с данными
- Re-list nudges находит ≥1 пример (если рынок позволяет)
- Sets-profit находит ≥5 прибыльных сетов
- При выкл. decrypt-agent — UI продолжает работать с пометкой «inventory N hours stale»
- Frontend держит ≤30 одновременных Centrifugo subscriptions

---

## 7. Phase B.2 — History + Signals

### 7.1 Storage (SQLite, WAL mode)

`data/wfm_history.db`:

```sql
CREATE TABLE order_snapshots (
  slug          TEXT NOT NULL,
  ts            INTEGER NOT NULL,
  side          TEXT NOT NULL,
  online_only   INTEGER NOT NULL,
  count_orders  INTEGER NOT NULL,
  min_price     INTEGER,
  p10           INTEGER, p25 INTEGER, median INTEGER, p75 INTEGER, p90 INTEGER,
  max_price     INTEGER,
  volume_qty    INTEGER NOT NULL,
  top5_json     TEXT,
  PRIMARY KEY (slug, ts, side, online_only)
) WITHOUT ROWID;
CREATE INDEX idx_snapshots_slug_ts ON order_snapshots(slug, ts DESC);

CREATE TABLE live_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL, slug TEXT, event_type TEXT, payload_json TEXT
);  -- TTL 7 days, cleaned by scheduled job

CREATE TABLE signal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL, slug TEXT, signal_type TEXT,
  payload_json TEXT, dedup_key TEXT UNIQUE
);

CREATE TABLE wfm_items (
  slug TEXT PRIMARY KEY, url_name TEXT, item_name TEXT,
  thumb_url TEXT, mastery_req INTEGER, tags TEXT, vaulted INTEGER,
  unique_name TEXT, updated_at INTEGER
);

CREATE TABLE set_compositions (
  set_slug TEXT, part_slug TEXT, qty INTEGER,
  PRIMARY KEY (set_slug, part_slug)
);
```

После 30 дней — auto-downsample hourly → daily (`history_daily` таблица).

### 7.2 Signals

Каждый сигнал — pure function `(slug, snapshots, current_state) → SignalEvent | None`.

| Signal | Условие | Дедуп ключ |
|---|---|---|
| `undervalued_mine` | твой WTS < median_7d - 2σ | `{slug}:{date}` |
| `overpriced_mine` | твой WTS > top-5_sell × 1.10 | `{slug}:{date}` |
| `competitor_undercut` | новый WTS дешевле твоего на ≥1p | `{slug}:{date}:{competitor_user}` |
| `bid_match` | WTB ≥ hypothetical sell | `{slug}:{date}:{wtb_user}` |
| `floor_drop` | min_price -10% за 6ч | `{slug}:{ts_floor_to_hour}` |
| `momentum_up` | EMA(6h) crosses EMA(24h) up | `{slug}:{date}` |
| `volume_spike` | volume > 3× rolling-24h-mean | `{slug}:{date}` |
| `vault_premium` | vaulted=1 AND median > unvaulted_baseline × 1.5 | `{slug}:{week}` |
| `set_profit_window` | parts+tax < set × 0.85 | `{set_slug}:{date}` |

### 7.3 Endpoints

| Endpoint | Описание |
|---|---|
| `GET /history/{slug}?days=30&granularity=hour\|day` | OHLC-стиль time series |
| `GET /signals/active?type=...&limit=20` | сейчас активные сигналы |
| `GET /signals/feed?since=ts` | infinite scroll |
| `GET /me/dashboard-actions` | top-10 ranked todo |

### 7.4 Frontend pages

- `/history/:slug` — ApexCharts line chart (min/median/max) + volume bars + аннотации signal-событий
- `/signals` — фильтруемая лента, sort by severity/recency, per-row PM-template
- `/` Dashboard обогащается виджетом «Top actions today»

---

## 8. Phase B.3 — Forecasts + Alerts

### 8.1 Forecasting (`wfm/forecast.py`)

Три уровня сложности, **первых двух хватит на 80% полезного**:

**1. Statistical baseline** (default):
- Rolling median 7d, 30d
- EMA α=0.2 на 6ч-сырых снапшотах
- Z-score текущей цены vs rolling-30d → детект аномалий
- Percentile bands (p10/p50/p90) → confidence interval

**2. Linear trend regression:**
- На лог-ценах, окно 14 дней, Huber loss
- `slope_per_day`, `r_squared`, projected price +7d
- r² < 0.3 → не показываем, UI говорит «too noisy»

**3. Prophet** (опциональный, флаг `forecast.engine=prophet`):
- Только для slug с ≥30 дней данных
- Daily granularity, weekly seasonality on
- `yhat`, `yhat_lower`, `yhat_upper` на +7d
- Тренируется ночью cron-job-ом, кешируется

**НЕ берём:** XGBoost, LSTM (over-engineering при текущем объёме данных).

### 8.2 Endpoint

```
GET /forecast/{slug}?engine=statistical|trend|prophet&horizon=7
```

Возвращает: `current_price`, `forecast_price`, `confidence` (high/med/low),
`band_lower`, `band_upper`, `method_used`, `as_of`, `data_points_used`.

### 8.3 Alerts (`wfm/alerts.py`)

```sql
CREATE TABLE alert_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT, condition_json TEXT,
  channels TEXT,  -- "toast,centrifugo" CSV
  is_enabled INTEGER, throttle_seconds INTEGER DEFAULT 3600,
  created_at INTEGER, last_fired_at INTEGER
);
```

Пример `condition_json`:
```json
{"signal":"bid_match","filters":{"min_offer_p":15,"item_slug_in":["kronen_prime_blade"]}}
```

**Engine:** подписан на `signals.new` RabbitMQ. Для каждого нового события —
пробегает rules, дедуп через `signal_events.dedup_key`, throttle через
`last_fired_at + throttle_seconds < now`.

**Transports:**
- **Centrifugo** канал `alert.{rule_id}` → frontend banner + опц. Browser Notifications
- **Desktop toast** → backend HTTP `POST agent:/toast` → агент зовёт `win10toast-click`
- **Telegram** — в Approach C

### 8.4 Frontend `/alerts`

- Список правил, drag-to-reorder priority
- Create-rule wizard: signal type → filters → channels → throttle
- Templated rules: «WTB ≥ floor +10%», «my listing lost #1», «vault item +50%»
- History tab: что сработало за неделю
- Test-fire: dry-run на последних 7 днях → «сработало бы N раз»

### 8.5 DoD

- WTB-offer ≥ median × 1.1 на item из инвентаря → toast в ≤30с
- Restart backend не теряет события (RabbitMQ durable queue)
- `/forecast/{slug}` отдаёт три метода рядом
- Правила управляются из UI без редактирования JSON руками

---

## 9. Data Flow

### 9.1 Свежая цена → UI

```
1. WFM-WS event → poller WFMSocketClient
2. Validate + RabbitMQ publish "wfm.live.orders" {slug, side, ...}
3. Backend consumer:
   - update Redis cached order book
   - compute signals(slug)
   - for new signals:
       - INSERT signal_events
       - publish "signals.new"
       - publish Centrifugo "wfm.orders.{slug}"
4. Alert engine consumer:
   - match rules → throttle → dedup
   - publish Centrifugo "alert.{rule_id}" + agent /toast
5. Frontend:
   - TanStack Query has cached snapshot via REST
   - Centrifugo sub on visible slugs
   - on WS event: invalidate or optimistic update
```

### 9.2 Refresh inventory

```
1. Frontend POST /api/me/refresh
2. Backend HTTP agent:/refresh
3. Agent runs dump_inventory.ps1 → writes data/lastData.json (mounted)
4. Backend re-reads JSON (через bridge.py)
5. Backend Centrifugo publish "inventory.refreshed"
6. All open tabs auto-invalidate
```

### 9.3 Consistency model

- REST = «известно из последнего snapshot или event»
- WS добавляет «свежее»
- WS down → REST догоняет polling-ом (`refetchInterval: 60s` для активных страниц)

---

## 10. Error Handling

| Component down | UI | Backend |
|---|---|---|
| decrypt-agent | banner «inventory N hours stale» | endpoints отдают cached JSON + `stale=true` |
| WFM REST 5xx | price=null + tooltip | `stale=true` на response, log warning |
| WFM 429 | latency растёт | exp backoff jitter, max 60s, потом fail-soft |
| WFM WS disconnect | «Live updates paused» indicator | poller reconnects (exp backoff) |
| Redis | latency ↑ | каждый request к WFM напрямую |
| RabbitMQ | нет real-time push | при старте: lifespan retry с backoff (10×), потом fail; в рантайме: durable queue → события не теряются, но накапливаются до восстановления |
| Centrifugo | UI fallback polling | publish-calls fail, log |
| SQLite locked | редко | WAL + `busy_timeout=5000` |
| Backend | UI offline mode | — |

**UI:**
- Глобальный banner: decrypt-agent / backend down (critical)
- Inline indicators per-item: stale price / no forecast
- Toast snackbars: WS reconnect, rate-limit hit

**Logging:** structlog JSON, ключи `component`, `event`, `slug`, `latency_ms`, `error_class`.

---

## 11. Testing Strategy

| Слой | Инструмент | Покрываем |
|---|---|---|
| Backend unit | pytest + pytest-asyncio + httpx.MockTransport | WFMClient (rate-limit, retry, cache), slug resolver, signal funcs, forecast baseline, sets-profit math |
| Backend integration | testcontainers-python (redis, rabbit) | poller→broker→backend→cache; alert throttle/dedup; SQLite migrations |
| WFM contract | VCR (pytest-recording) | реальные WFM responses записаны, offline replay |
| Frontend unit | vitest + @solidjs/testing-library | компоненты, хуки, форматеры |
| Frontend e2e | playwright | один happy path: `/` → `/prime-parts` → видны цены |
| Type contract | openapi-typescript | regen на backend changes, `tsc --noEmit` падает на drift |
| Pre-commit | ruff, mypy strict (backend); eslint, tsc (frontend) | блокировка commit |
| CI smoke | `docker compose up --wait` + `curl /healthz` | docker валиден, контейнеры стартуют |

**НЕ делаем в B.0-B.3:** load tests, mutation tests, fuzzing.

---

## 12. Out of Scope (этого спека)

- Approach C: ривены, Telegram, опц. LLM (PM-шаблоны, NL-поиск ривенов)
- Multi-platform (Xbox/PS/Switch) — конфигурируется одной env var, но default PC
- Multi-user / SaaS
- Public API / OAuth
- Auto-buy / auto-sell (без подтверждения пользователя — не делаем никогда)
- XGBoost / LSTM forecasting
- Mobile-native UI (web responsive хватит)
- Self-hosted Kafka (используем RabbitMQ)

---

## 13. Open Questions / Risks

| # | Вопрос/риск | Mitigation |
|---|---|---|
| 1 | WFM API закроют / поменяют схему | Изолированный WFMClient, можно подменить |
| 2 | WFM token истёк → 401 | Clear UI message; `/auth/signin` flow можно добавить позже |
| 3 | Slug resolver промахивается на новых items | Ручной override в `data/slug_overrides.json` |
| 4 | DLL-методы (`AlecaFrameClientLib`) изменятся в новой AlecaFrame версии | scripts/dump_inventory.ps1 пинит мажорную версию |
| 5 | Docker Desktop тяжёлый на Windows | Альтернатива — Podman или WSL2 ручной; не блокер сейчас |
| 6 | RabbitMQ overkill для одного пользователя | Можно заменить на NATS позже; интерфейс broker-а абстрагирован |
| 7 | Frontend Solid + Tailwind v4 — relatively new combo | План B — Tailwind v3 если v4 проблемен |
| 8 | Prophet тяжёлая зависимость | Flag-controlled, в default off; ставится в отдельный extra `[forecast-prophet]` |

---

## 14. Decisions Log

Зафиксировано в ходе brainstorming:

- **Shape:** Approach B (Trading Cockpit), фазы B.0/B.1/B.2/B.3
- **Style торговли в приоритете:** prime-parts/sets + vault, без ривенов на этом этапе
- **Mode:** dashboard + real-time alerts + forecasts (всё вместе, в фазах)
- **LLM:** не используется на B.0-B.3; classical statistics; LLM рассматривается в Approach C
- **Broker:** RabbitMQ (легче Kafka, достаточно для use case)
- **Cache:** Redis L1 + SQLite persistence
- **Push:** Centrifugo (WS/SSE) + desktop toast через decrypt-agent
- **Frontend:** SolidJS + Vite + TS + Tailwind 4 + TanStack Query + centrifuge-js + **ApexCharts**
- **decrypt-agent:** Python FastAPI + **pystray system tray app**
- **WFM platform:** **PC**
- **Orders filter:** оба режима, online-default, `?include_offline=1` opt-in
- **WFM transport:** **REST + WebSocket сразу** (с B.1)
- **DLL bridge:** decrypt-agent на хосте, backend в контейнере читает mounted JSON

---

**Конец дизайна. Следующий шаг — `writing-plans` skill для импл-плана.**
