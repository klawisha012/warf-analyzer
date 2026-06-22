# Тест-структура + CI/CD — Design

**Дата:** 2026-06-22
**Статус:** утверждён (брейншторм пройден)
**Фаза:** 1 (проработка) → 5 (реализация)

## 1. Цель

Привести каталог `tests/` к ясной трёхуровневой структуре (unit / integration /
e2e) с разделением backend/frontend, добавить недостающий фронт-тест-раннер и
браузерный e2e, ввести единый линт/формат на обе части стека и собрать
GitHub Actions CI-пайплайн (формат/линт → типчек → тесты → сборка).

## 2. Контекст и текущее состояние

Монорепо:
- **backend/** — Python 3.12, `uv` (`uv.lock`), FastAPI, hatchling. Пакет
  `alecaframe_api`. Тесты гоняются из корня: `uv run --project backend pytest`.
- **frontend/** — SolidJS, Vite 6, TypeScript 5.7, Tailwind v4.
- **docker/** + `docker-compose.yml` — стек (backend, frontend/nginx, centrifugo,
  rabbitmq, redis, poller).

Что уже есть в `tests/` (~35 файлов):
- `unit/` — ~15 тестов, **плоско, только бэкенд**.
- `integration/backend/` — ~20 тестов; `integration/frontend/` — пусто
  (`__init__.py`).
- `e2e/test_smoke_e2e.py` — pytest-смоук по **живому docker-стеку** (помечен
  `-m e2e`, требует реальные сервисы/инвентарь пользователя).
- `test_data/fixtures/*.json` — статические сэмплы.
- `tests/__init__.py` экспортирует `REPO_ROOT` и `FIXTURES_DIR`
  (`test_data/fixtures`); `conftest.py` — общая фикстура `tmp_data_dir`.
- `pytest.ini` (корень): `testpaths=tests`, `asyncio_mode=auto`,
  `addopts=-ra -q -m "not e2e"`, маркер `e2e`.

Чего нет:
- Фронт — **без тест-раннера вообще** (нет vitest).
- Нет `tests/README.md`, нет `unit/{backend,frontend}` сплита, нет
  `fixtures/` (код) отдельно от `test_data/` (данные), нет `e2e/{flows,pages}`.
- Линт/формат не настроены **нигде** (бэк без ruff, фронт без eslint/prettier).
- CI отсутствует (`.github/` нет).

**Ключевой факт переносимости:** тесты обращаются к данным через константу
`FIXTURES_DIR`, а не хардкод-пути — значит файлы тестов можно перемещать, а
JSON-данные перенести, поправив **одну** строку в `tests/__init__.py`.
Win32-зависимости (`pystray`, `win10toast`) имеют маркер `sys_platform=='win32'`
и на Linux-CI не ставятся.

## 3. Решённые развилки (брейншторм)

1. **Раскладка тестов** → сплит `unit/` на `backend/` + `frontend/`; существующие
   unit-тесты переезжают в `unit/backend/` (внутри плоско). Без выдуманных
   `services/models/utils` — в `src` их нет (`wfm/fissures/db/infra/reference`).
2. **Фронт-тесты** → Vitest + `@solidjs/testing-library` + jsdom + рабочие примеры.
3. **E2E** → добавляем Playwright (`flows/` + `pages/` Page Objects). pytest-смоук
   по стеку остаётся как отдельный ручной слой.
4. **Линт** → Ruff (бэк) + ESLint/Prettier (фронт); линт-шаг в CI **блокирующий**,
   существующие нарушения чиним заранее (первый прогон CI зелёный).

## 4. Целевая структура `tests/`

```
tests/
├── unit/
│   ├── backend/          # git mv существующих unit-тестов сюда (+ __init__.py)
│   └── frontend/         # NEW: Vitest .test.ts(x) (TS, без __init__.py)
├── integration/
│   ├── backend/          # без изменений
│   └── frontend/         # Vitest интеграционные; vestigial __init__.py убрать
├── e2e/
│   ├── flows/            # NEW: Playwright *.spec.ts
│   ├── pages/            # NEW: Page Objects (*.ts)
│   └── test_smoke_e2e.py # остаётся (pytest-смоук инфры, -m e2e)
├── fixtures/             # NEW: переиспользуемый ТЕСТОВЫЙ КОД (Python) + __init__.py
├── test_data/
│   ├── backend/          # git mv test_data/fixtures/*.json сюда
│   └── frontend/         # NEW: .gitkeep (пока пусто)
├── conftest.py           # без изменений
├── __init__.py           # FIXTURES_DIR → test_data/backend
└── README.md             # NEW: запуск бэк/фронт/e2e на один экран
```

**Отклонения от нарисованного шаблона (обоснованные):**
- Нет `services/models/utils` — мэппинг на реальные подпакеты `src` не такой;
  unit делится только до `backend`/`frontend`.
- `composables` (Vue-термин) → `frontend/` (SolidJS использует `hooks/`).
- Сосуществуют два e2e-слоя: Playwright (UI-флоу, в CI) и pytest-смоук (здоровье
  живого стека, ручной) — разные уровни проверки.
- `test_data/fixtures/` → `test_data/backend/`: убирает коллизию «fixtures(код)
  vs fixtures(данные)»; правится только константа `FIXTURES_DIR`, все ссылки на
  данные идут через неё и не меняются.

**Размещение фронт-тестов (осознанный компромисс):** тест-файлы лежат в корневом
`tests/unit/frontend` и `tests/integration/frontend` (как в утверждённом дереве),
а раннер/`node_modules`/alias живут в `frontend/`. Vitest сконфигурён читать эти
пути; тесты импортят исходники через alias `@/…`. Идиоматичная альтернатива —
со-локация `frontend/src/**/*.test.tsx` — отклонена в пользу единого дерева.

## 5. Бэкенд: Ruff (линт + формат)

- `backend/pyproject.toml`: `ruff` в `[dependency-groups] dev`; блоки
  `[tool.ruff]` (target py312, line-length 88) и `[tool.ruff.lint]` (наборы
  `E,F,I,UP,B`; разумные `per-file-ignores`, напр. `__init__.py: F401`).
- Прогон `ruff format` + `ruff check --fix` по `backend/src` и `tests/`; остаток
  правится вручную.
- mypy **не вводим** (вне запроса).

## 6. Фронт: Vitest + ESLint + Prettier

**Vitest:**
- Отдельный `frontend/vitest.config.ts`: плагин `vite-plugin-solid`,
  `environment: 'jsdom'`, `globals: true`, alias `@ → src`, `setupFiles`
  (jest-dom матчеры), `include` → абсолютные пути на
  `../tests/unit/frontend/**` и `../tests/integration/frontend/**`
  (через `import.meta.dirname`, т.к. ESM-конфиг).
- devDeps: `vitest`, `@solidjs/testing-library`, `@testing-library/jest-dom`,
  `jsdom`, `@vitest/coverage-v8`.
- Setup-файл `frontend/vitest.setup.ts` (импорт jest-dom).
- Примеры: unit на `src/lib/format.ts`; смоук-рендер компонента (`Badge`/`Card`)
  в `integration/frontend`.
- Сборка (`tsc --noEmit` через `include:["src"]`) тест-файлы не трогает —
  `npm run build` остаётся чистым.

**ESLint v9 (flat) + Prettier:**
- `frontend/eslint.config.js`: `@eslint/js` + `typescript-eslint` +
  `eslint-plugin-solid` + `eslint-config-prettier`.
- `frontend/.prettierrc.json` + `frontend/.prettierignore`.
- Прогон `prettier --write` + `eslint --fix`; остаток вручную.

**Скрипты `package.json`:** `lint`, `lint:fix`, `format`, `format:check`,
`test` (`vitest run`), `test:watch`, `coverage`, `e2e`, `e2e:install`.

## 7. E2E: Playwright

- `frontend/playwright.config.ts`: `testDir: '../tests/e2e/flows'`, проект
  `chromium`, `webServer` поднимает `vite preview` на сбилженном `dist/`
  (`127.0.0.1:4173`), `baseURL`.
- devDep `@playwright/test`.
- **Стабильность в CI:** флоу мокают бэкенд через `page.route('**/api/**', …)` —
  без живого backend/docker/сети. Один пример-флоу (рендер страницы + список из
  замоканного API) + один Page Object в `tests/e2e/pages/`.
- WebSocket (`/connection`, centrifugo) при preview недоступен; пример-флоу
  выбирается так, чтобы рендер не зависел от realtime (при необходимости — мок/
  заглушка соединения).
- pytest-смоук по живому стеку — **вне CI**, ручной (документируется в README).

## 8. CI/CD — `.github/workflows/ci.yml`

- **Триггеры:** `push` (ветки `master`, `main`) + `pull_request`.
- **Хардненинг:** `permissions: contents: read` (top-level), `concurrency`
  (отмена устаревших ранов на ветку), экшены запинены по мажорному тегу
  доверенных издателей (`actions/checkout@v4`, `actions/setup-node@v4`,
  `astral-sh/setup-uv@v5`). Секреты не используются.

| Job | runs-on | Шаги |
|-----|---------|------|
| **backend** | ubuntu-latest | setup-uv → `uv sync --project backend` → `ruff format --check` → `ruff check` → `uv run --project backend pytest` (unit+integration; `-m "not e2e"` из pytest.ini) |
| **frontend** | ubuntu-latest | setup-node (cache npm) → `npm ci` → `npm run format:check` → `npm run lint` → `npm run typecheck` → `npm run test` (`vitest run`) → `npm run build` |
| **e2e** | ubuntu-latest | setup-node → `npm ci` → `npx playwright install --with-deps chromium` → `npm run build` → `npm run e2e` (мокнутый API, блокирующий) |

Рабочая директория фронт-джобов — `frontend/` (`defaults.run.working-directory`).

## 9. Риски

- **Переносимость на Linux-CI (главный):** какой-либо импортируемый в тестах
  модуль бэка может транзитивно тянуть win32-only (`pystray`/`win10toast`) на
  этапе коллекции pytest. Митигация: проверить фактическим прогоном; если падает —
  guard на импорты (ленивая/условная загрузка tray-кода) или точечный
  `importorskip`. Юнит/интеграционные импортят `wfm/db/fissures/...` — вероятно
  чисто, подтвердить.
- **Шум линта:** первый `ruff`/`eslint` на нетронутую базу даст много правок —
  ожидаемо (выбран блокирующий режим); правки атомарны и проверяются прогоном.
- **Vitest из корневого `tests/`:** нестандартная связка путей — закрепляется
  абсолютными `include` и alias; пример-тесты подтверждают работоспособность.

## 10. Файловый манифест

**Создаётся:**
- `tests/README.md`, `tests/fixtures/__init__.py`
- `tests/unit/backend/__init__.py`, каталоги `tests/unit/frontend/`,
  `tests/e2e/flows/`, `tests/e2e/pages/`, `tests/test_data/frontend/.gitkeep`
- `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`,
  `frontend/eslint.config.js`, `frontend/.prettierrc.json`,
  `frontend/.prettierignore`, `frontend/playwright.config.ts`
- Пример-тесты: `tests/unit/frontend/*.test.ts`,
  `tests/integration/frontend/*.test.tsx`, `tests/e2e/flows/*.spec.ts`,
  `tests/e2e/pages/*.ts`
- `.github/workflows/ci.yml`

**Перемещается (git mv):**
- `tests/unit/test_*.py` → `tests/unit/backend/`
- `tests/test_data/fixtures/*.json` → `tests/test_data/backend/`

**Меняется:**
- `tests/__init__.py` (`FIXTURES_DIR` → `test_data/backend`)
- `tests/integration/frontend/__init__.py` (удалить vestigial)
- `pytest.ini` (`norecursedirs` для фронт/e2e-ts путей + `node_modules`)
- `backend/pyproject.toml` (ruff dev-dep + config)
- `frontend/package.json` (+ devDeps, скрипты), `frontend/package-lock.json`
- Существующие `backend/src/**` и `frontend/src/**` — авто-правки формата/линта
- `.gitignore`

## 11. `.gitignore`

Добавить под реально появляющиеся артефакты: `.ruff_cache/`,
`frontend/coverage/`, `frontend/playwright-report/`, `frontend/test-results/`,
`frontend/.playwright/`.

## 12. Критерии приёмки

- `uv run --project backend pytest` — зелёно локально; в CI backend-job зелёный.
- `cd frontend && npm run format:check && npm run lint && npm run typecheck &&
  npm run test && npm run build` — всё зелёно.
- `cd frontend && npm run e2e` — пример-флоу проходит на мокнутом API.
- Структура `tests/` соответствует секции 4; `from tests import FIXTURES_DIR` и
  все существующие тесты работают после переезда.
- `.github/workflows/ci.yml` проходит на push/PR (3 джоба зелёные); линт-шаги
  блокирующие.
- `tests/README.md` описывает запуск всех трёх слоёв на один экран.
