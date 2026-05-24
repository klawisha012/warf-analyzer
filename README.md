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
| Python | 3.12+ (тестировал на 3.13.12) |
| pwsh | PowerShell 7.x (`pwsh.exe`) |
| AlecaFrame | установлена через Overwolf, хотя бы раз запускалась |
| uv | для управления зависимостями |

## Установка

```powershell
cd "B:\Sync\Programming\projects\aleca frame inventory"
uv sync
```

## Запуск

```powershell
# самый простой
uv run alecaframe-api

# с автоперезагрузкой
$env:ALECA_RELOAD = "1"; uv run alecaframe-api

# напрямую через uvicorn
uv run uvicorn alecaframe_api.main:app --reload --port 8765
```

Открыть `http://127.0.0.1:8765/docs` — Swagger UI с интерактивными запросами.

## Конфиг (env vars)

| Переменная | Дефолт | Назначение |
|---|---|---|
| `ALECA_HOST` | `127.0.0.1` | bind host |
| `ALECA_PORT` | `8765` | bind port |
| `ALECA_TTL_SECONDS` | `60` | TTL кеша; после истечения первый запрос триггерит refresh |
| `ALECA_DATA_DIR` | `./data` | куда писать расшифрованные JSON |
| `ALECA_SCRIPT` | `./scripts/dump_inventory.ps1` | путь к pwsh-скрипту |
| `ALECA_PWSH` | `pwsh` | имя бинаря PowerShell 7 |
| `ALECA_DATA_HOME` | `%LOCALAPPDATA%\AlecaFrame` | папка AlecaFrame |
| `ALECA_LOG_LEVEL` | `INFO` | уровень логов |
| `ALECA_RELOAD` | — | `1` = uvicorn reload |

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
├── pyproject.toml
├── README.md
├── scripts/
│   └── dump_inventory.ps1     # вызов AlecaFrameClientLib.dll
├── src/alecaframe_api/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + endpoints
│   ├── bridge.py               # pwsh runner + in-memory cache
│   ├── naming.py               # uniqueName → display name resolver
│   └── schemas.py              # Pydantic response models
└── data/                       # gitignored, расшифрованные JSON
    ├── lastData.json
    ├── deltas.json
    └── _meta.json
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
