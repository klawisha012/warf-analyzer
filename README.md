# AlecaFrame Inventory API

Локальный FastAPI-бэкенд, который читает твой Warframe-инвентарь из
кеша AlecaFrame **без запуска самого AlecaFrame**.

## Как это работает

AlecaFrame шифрует слепок профиля игры (`%LOCALAPPDATA%\AlecaFrame\lastData.dat`)
HWID-привязанным ключом. Сам ключ зашит в их `AlecaFrameClientLib.dll`. Реверсить
крипту не нужно — DLL уже умеет расшифровывать на этой машине.

Бэкенд:

1. `POST /refresh` (или TTL 60 секунд) → вызывает `scripts/dump_inventory.ps1`
2. Скрипт через reflection грузит `AlecaFrameClientLib.dll`, зовёт публичные
   статичные методы `Utils.Misc.ReadLastDataFile()` / `ReadAllTextEncrypted(...)`
3. Расшифрованный JSON ложится в `data/lastData.json` и `data/deltas.json`
4. FastAPI парсит, обогащает названиями из `%LOCALAPPDATA%\AlecaFrame\cachedData\json\`
   и отдаёт по REST.

Работает **только на машине, где установлена и запускалась AlecaFrame** —
HWID-ключ не вынести.

## Требования

| | |
|---|---|
| OS | Windows 10 / 11 |
| Python | 3.13+ |
| Node.js | 22+ (только для разработки фронта) |
| pwsh | PowerShell 7.x |
| Docker Desktop | актуальная версия, WSL2 backend |
| AlecaFrame | установлена через Overwolf, хотя бы раз запускалась |
| uv | для зависимостей Python |

## Архитектура (B.0)

Бэкенд и инфраструктура — в docker-compose. Расшифровка `.dat` файлов
требует Windows-only DLL, поэтому она вынесена в отдельный host-процесс
`decrypt-agent` (tray-app), к которому backend-контейнер обращается через
`host.docker.internal:8788`.

```
host:                  docker compose:
┌────────────────┐    ┌──────────────────────────────────────┐
│ decrypt-agent  │    │ frontend (:3000)  ─── nginx + Solid  │
│  pystray tray  │    │                                       │
│  :8788  ◀──────┼────┤ backend  (:8765) ─── FastAPI         │
│  pwsh + DLL    │    │ poller          ─── worker stub      │
│                │    │ redis    (:6379)                     │
│  writes ./data │    │ rabbitmq (:5672/:15672)             │
└────────────────┘    │ centrifugo (:8002 host → :8000 inner)│
                      └──────────────────────────────────────┘
```

Note: Centrifugo на хосте маппится на 8002, а не 8000 — порт 8000 занят Docker Desktop.
Внутри compose network — обычный 8000. Frontend nginx правильно проксирует.

## Установка

```powershell
git clone <repo> ; cd "aleca frame inventory"
uv sync                              # Python deps
Push-Location frontend ; npm install ; Pop-Location   # frontend deps
Copy-Item .env.example .env
```

Если `uv sync` падает из-за того, что `alecaframe-poller.exe` залочен Windows Defender —
добавь папку проекта в Defender exclusions, или закрой запущенные процессы Python
из предыдущего сеанса.

## Запуск

```powershell
./scripts/start-stack.ps1
```

Что делает скрипт:
1. Запускает `decrypt-agent` в отдельном окне (если ещё не запущен)
2. `docker compose up -d` — все шесть сервисов
3. Ждёт `/healthz` бэкенда и печатает три URL-а

UI: <http://127.0.0.1:3000>
API: <http://127.0.0.1:8765/docs>
RabbitMQ UI: <http://127.0.0.1:15672> (aleca / aleca-local)

Полная остановка:

```powershell
docker compose down
# и Quit из tray-меню decrypt-agent
```

## Frontend pages (B.1b)

После `./scripts/start-stack.ps1` открой `http://127.0.0.1:3000`:

| Route | Что показывает |
|---|---|
| `/` | Dashboard: Health/WFM-user/AlecaFrame-version + три виджета (Top WTB matches, Top set profits, Re-list nudges) |
| `/inventory` | Сетка карточек инвентаря с фильтром по slot и поиском по имени |
| `/prime-parts` | Таблица прайм-партов с min-qty фильтром и общим est. value |
| `/sets` | Buildable сеты с фильтром min profit |

Маршрутизация на `@solidjs/router`, fetching на `@tanstack/solid-query` (staleTime 30s, no refetch-on-focus).
SPA fallback в nginx → каждый маршрут возвращает 200, клиент сам рендерит.

При выключённом decrypt-agent dashboard покажет offline + empty-state в виджетах;
прочие страницы покажут «No items» вместо crash.

## Разработка фронта вне docker

В docker-compose фронт собран и отдаётся через nginx. Для быстрого
HMR-цикла:

```powershell
docker compose up -d redis rabbitmq centrifugo backend poller
cd frontend
npm run dev   # vite на :5173, /api проксируется в backend
```

## Конфиг (env vars)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `ALECA_AGENT_URL` | `http://host.docker.internal:8788` | где живёт decrypt-agent |
| `ALECA_REDIS_URL` | `redis://redis:6379/0` | L1-кеш, общий rate-limiter (B.1+) |
| `ALECA_RABBITMQ_URL` | `amqp://aleca:aleca-local@rabbitmq:5672/` | event bus |
| `ALECA_CENTRIFUGO_API` | `http://centrifugo:8000/api` | publish events to UI |
| `ALECA_CENTRIFUGO_API_KEY` | (override в `.env`) | secret для publish |
| `ALECA_CENTRIFUGO_TOKEN_HMAC_SECRET` | (override в `.env`) | HMAC ключ для JWT-токенов клиентов |
| `ALECA_DATA_DIR` | `/data` | mounted volume с расшифрованным JSON |
| `ALECA_TTL_SECONDS` | `60` | TTL backend-кеша |
| `ALECA_WFM_PLATFORM` | `pc` | `pc` / `xbox` / `ps4` / `switch` |
| `ALECA_LOG_LEVEL` | `INFO` | уровень логов |
| `AGENT_PORT` | `8788` | порт decrypt-agent (host) |
| `AGENT_OUT_DIR` | `./data` (рядом с проектом) | куда писать JSON |

## Endpoints

### Сервисные

- `GET /` — список endpoint-ов
- `GET /healthz` — статус + возраст кеша + WFM-юзер
- `POST /refresh` — заставить расшифровать заново
- `GET /meta` — версия AlecaFrame, пути, бридж-мета

### Сводные

- `GET /summary` — валюты + счётчики разделов + стэндинг
- `GET /currencies` — Plat / Credits / Endo / Ducats / Trades / Gifts
- `GET /standings` — daily affiliation по всем синдикатам

### WFM market (B.1a)

- `GET /wfm/items` — каталог slug-ов из warframe.market (24h cache)
- `GET /wfm/orders/{slug}?include_offline=0&fresh=0` — текущий order book с агрегациями (min/median/percentiles/spread/volume)
- `GET /wfm/profile/{user}` — репутация и статус
- `GET /me/listings` — твои активные WTS/WTB
- `GET /me/inventory-priced?slot=warframe|primary|secondary|melee|all&limit=50` — инвентарь с медианной ценой и spread
- `GET /me/prime-parts-priced?min_count=1` — расширение `/prime-parts` с ценами + Vaulted-флаг
- `GET /me/sets-profit?min_margin=0` — buildable сеты + cost-to-complete + profit
- `GET /me/wtb-matches?min_offer=10` — WTB-ордера на items, которые у тебя есть
- `GET /me/relist-nudges` — listings, выпавшие из топ-5 / ниже медианы

### Списки инвентаря

- `GET /warframes` — Suits
- `GET /weapons?slot=primary|secondary|melee|sentinel|sentinel_weapon|archwing|arch_gun|arch_melee|amp|kdrive|moa|kubrow`
- `GET /mods?q=&limit=&offset=` — RawUpgrades (сортирован по имени)
- `GET /recipes?q=&limit=&offset=` — BPs в инвентаре
- `GET /misc?q=&sort=name|count_desc|count_asc&limit=&offset=` — MiscItems
- `GET /prime-parts?min_count=1` — агрегированный список Prime BPs + парт
- `GET /foundry` — что строится прямо сейчас
- `GET /rivens` — Riven mods (Upgrades с `Randomized`)

### Низкоуровневые

- `GET /raw?path=Suits.0` — расшифрованный `lastData.json` целиком или срез
- `GET /deltas` — `deltas.json`

## Примеры

```powershell
# поднять
uv run alecaframe-api

# в другом терминале:
curl http://127.0.0.1:8765/summary | jq .
curl "http://127.0.0.1:8765/weapons?slot=melee" | jq '.items[] | .name'
curl "http://127.0.0.1:8765/mods?q=primed&limit=10" | jq .
curl http://127.0.0.1:8765/prime-parts | jq '.items[:10]'
curl "http://127.0.0.1:8765/raw?path=DailyAffiliationCetus"
curl -X POST http://127.0.0.1:8765/refresh | jq .
```

## Структура

```
aleca frame inventory/
├── docker-compose.yml
├── .env.example
├── docker/
│   ├── backend/Dockerfile
│   ├── poller/Dockerfile
│   ├── frontend/{Dockerfile, nginx.conf}
│   ├── centrifugo/config.json
│   ├── rabbitmq/{definitions.json, rabbitmq.conf}
│   └── redis/redis.conf
├── scripts/
│   ├── dump_inventory.ps1
│   └── start-stack.ps1
├── src/
│   ├── alecaframe_api/        # backend (in container)
│   └── decrypt_agent/         # host-side (tray app)
├── frontend/                  # SolidJS + Vite + Tailwind 4
├── tests/
├── data/                      # gitignored: shared volume
└── docs/superpowers/{specs,plans}/
```

## Известные ограничения

- **Только эта машина.** HWID-привязка делает кеш непереносимым.
- **`/rivens`** возвращает Upgrades с `Randomized` в `ItemType`; имена и роллы
  доступны через `extra.UpgradeFingerprint` (это JSON-строка с buffs/curses).
- **`/deltas`** обычно показывает `currentDeltas: {}` — AlecaFrame чистит
  delta-буфер при просмотре. Чтобы поймать живую дельту, надо запускать
  AlecaFrame и снимать через DevTools.
- **Цены WFM** не входят — это отдельный источник. Можно добавить, дёрнув
  `https://api.warframe.market/v1/items/{slug}/orders` (токен в
  `%LOCALAPPDATA%\AlecaFrame\WFMarketToken.tk`).
- **Не пересылай содержимое `data/`** — там твой полный игровой профиль.

## Безопасность

`data/` исключён из git. Если хочешь параноидально — добавь basic auth в
FastAPI или забинди на `127.0.0.1` (дефолт).
