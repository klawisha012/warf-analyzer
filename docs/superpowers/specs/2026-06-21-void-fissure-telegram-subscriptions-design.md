# Подписки на разрывы Бездны с уведомлениями в Telegram — Design

**Дата:** 2026-06-21
**Статус:** утверждён (брейншторм пройден)
**Фаза:** 1 (проработка) → 5 (реализация)

## 1. Цель

Дать возможность подписаться на конкретные **разрывы Бездны (Void Fissures)** в
Warframe и получать уведомление в Telegram, как только в worldstate появляется
новый разрыв, проходящий фильтр подписки.

## 2. Контекст и привязка к архитектуре

Проект — FastAPI-бэкенд (`alecaframe_api`) + SolidJS-фронтенд. Уже есть готовые
паттерны, на которые фича ложится один-в-один:

- **Поллеры** (`PricePoller`, `AuctionPoller`) — async-циклы, поднимаются как
  `asyncio.create_task` в `lifespan` `main.py`. Новый `FissurePoller` — их близнец.
- **Persistence** — `Repo` (aiosqlite), DDL в `db/schema.sql`
  (`CREATE TABLE IF NOT EXISTS`), мелкие миграции через `_try_add_column`.
- **DI** — singletons в модуле `*/dependencies.py`, наполняются в `lifespan`.
- **Тесты** — `pytest` + `pytest-asyncio` (`asyncio_mode=auto`) + `pytest-httpx`
  (мок HTTP) + `fakeredis`.

Данных о разрывах в проекте **нет** — это новый внешний источник (worldstate).

## 3. Анализ: все возможные разрывы Бездны (таксономия)

Каждый активный разрыв в worldstate описывается набором независимых осей:

- **Эра реликвии** (`tier`), 6 значений: `Lith`, `Meso`, `Neo`, `Axi`,
  `Requiem`, `Omnia`.
- **Тип миссии** (`missionType`) — открытый перечень; на практике:
  Capture, Defense, Disruption, Excavation, Extermination, Hijack,
  Interception, Mobile Defense, Rescue, Sabotage, Spy, Survival, Assault,
  плюс Void-Storm-режимы: Skirmish, Volatile, Void Cascade, Void Flood, Orphix.
- **Стальной путь** (`isHard`: bool) — независимая ось.
- **Бездонный шторм / Railjack** (`isStorm`: bool) — независимая ось.
- **Локация** (`node`, например `Proteus (Neptune)`) + время жизни (~1 ч).

«Подписка» = фильтр по {эра, тип миссии, isHard, isStorm}, любая ось может быть
не задана (= «любое»).

## 4. Источник данных: warframestat.us

`FissureClient` тянет `https://api.warframestat.us/{platform}/fissures` (один
массив, содержит и обычные, и Steel Path, и Void Storm — различаются флагами).
Реальная форма объекта (проверено живым ответом 2026-06-21, PC):

```json
{
  "id": "6a37c2cad201d87c508ce5b1",
  "activation": "2026-06-21T10:54:02.850Z",
  "expiry": "2026-06-21T12:42:01.145Z",
  "node": "Proteus (Neptune)",
  "missionType": "Defense",
  "enemy": "Corpus",
  "tier": "Neo",
  "tierNum": 3,
  "isStorm": false,
  "isHard": true
}
```

- `id` — стабильный и уникальный на время жизни разрыва → ключ дедупликации.
- Поля `eta`/`active`/`missionKey` в массиве **отсутствуют** — `eta` вычисляем
  из `expiry - now` на сериализации.
- Маппинг платформы settings → warframestat.us: `pc→pc`, `xbox→xb1`,
  `ps4→ps4`, `switch→swi`.

Нормализуем в dataclass `Fissure(id, era, mission_type, node, planet, enemy,
is_hard, is_storm, activation, expiry)`. `planet` парсится из `node` (скобки).

`FissureClient.get_fissures()` держит внутренний TTL-кэш (~30 с): один и тот же
разобранный список переиспользуют и поллер, и HTTP-роут, не долбя API.

## 5. Модель подписок и матчинг

Таблица `fissure_subscription(id, era, mission_type, is_hard, is_storm,
enabled, created_at)`. **NULL в поле = «любое».** `is_hard`/`is_storm` хранятся
как `INTEGER` 0/1/NULL.

Чистая функция `matches(fissure, sub) -> bool`: для каждого *заданного* (не-NULL)
поля — равенство; пустая подписка ловит всё. Изолирована, покрыта юнит-тестами.

## 6. Telegram (два направления)

Модуль `fissures/telegram.py`:

- **Исходящий** — `TelegramClient.send_message(chat_id, text)`:
  `POST https://api.telegram.org/bot{TG_API_KEY}/sendMessage`, тело
  `{chat_id, text}` (plain text, без `parse_mode` — нет проблем с экранированием).
- **Входящий** — `TelegramBot.run()`: long-poll
  `GET .../getUpdates?timeout=25&offset={offset}`. На сообщение `/start` →
  `repo.register_telegram_chat(chat_id, username)` + ответ «✅ Подписка активна».
  `offset` держим в памяти; регистрация идемпотентна, поэтому рестарт безопасен
  (повторный `/start` просто обновит запись).
- `webhook` отвергнут: проект крутится локально в docker-compose без публичного
  HTTPS — long-poll единственный рабочий вариант.

**Модель адресации:** подписки **глобальные** (у приложения нет учёток),
уведомление рассылается **всем** чатам, прошедшим `/start`. `/start` выбран
ради удобства (не нужно вручную искать numeric chat_id), а не ради
персональных подписок. Если `TG_API_KEY` не задан — подсистема Telegram спит
целиком (как деградация при недоступном RabbitMQ); поллер всё равно работает и
отдаёт живой список разрывов в UI.

## 7. Дедупликация и жизненный цикл

Журнал `fissure_notification(subscription_id, fissure_id, notified_at)`,
PK `(subscription_id, fissure_id)`. Уведомляем один раз на пару
(подписка × разрыв). `record_fissure_notification` делает `INSERT OR IGNORE` и
возвращает «было ли вставлено впервые». Старые записи (> 3 ч) подчищаются каждый
тик. Журнал в БД → переживает рестарт, не спамит повторно.

## 8. Поток поллера (`FissurePoller.tick`)

1. `fissures = client.get_fissures()` (ошибки логируются, тик не падает).
2. `subs = repo.list_fissure_subscriptions(enabled_only=True)`; если пусто —
   выход.
3. `chats = repo.list_telegram_chats()` (один раз за тик).
4. Для каждой `sub` и каждого `f`, где `matches(f, sub)`:
   `record_fissure_notification(...)`; если впервые и Telegram включён →
   разослать `format_message(f)` всем `chats`.
5. `prune_fissure_notifications(older_than = now - 3h)`.

## 9. HTTP API (`fissures/router.py`, prefix `/fissures`)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/fissures` | текущие активные разрывы (для UI) |
| GET | `/fissures/meta` | перечень осей: эры (6) + типы миссий (статика ∪ live) |
| GET | `/fissures/subscriptions` | список подписок |
| POST | `/fissures/subscriptions` | создать (era?, mission_type?, is_hard?, is_storm?) |
| DELETE | `/fissures/subscriptions/{id}` | удалить |
| GET | `/fissures/telegram/chats` | зарегистрированные получатели + флаг включённости бота |
| POST | `/fissures/telegram/test` | тест-сообщение всем чатам |

## 10. Frontend

Новый роут `routes/Fissures.tsx` (по образцу `Rivens.tsx`):

- **Слева** — конструктор подписки: select эры, select типа миссии, tri-state
  (любое/да/нет) для Steel Path и Void Storm, кнопка «добавить»; список
  подписок с удалением.
- **Справа** — живой список активных разрывов (`createQuery` с
  `refetchInterval: 30_000`); панель Telegram: статус бота, инструкция «напиши
  боту `/start`», список чатов, кнопка теста.

Правки: `main.tsx` (lazy-роут `/fissures`), `components/Layout.tsx` (навигация),
`api/queries.ts` (`keys` + `fetchers`), `api/types.ts` (типы),
`i18n/dict/{en,ru}.ts` (`nav.fissures` + секция `fissures`). Переиспользуем
`Card`/`Badge`/`EmptyState`.

**Решение (YAGNI):** живой список — через 30-секундный polling, **не** через
Centrifugo. Разрывы меняются медленно, настоящий алерт — Telegram. Это убирает с
фронта realtime-hook, а с бэка — публикацию в Centrifugo.

## 11. Конфиг и инфраструктура

- `config.py`: `tg_api_key: str | None = Field(default=None,
  validation_alias="TG_API_KEY")` (ровно `TG_API_KEY`, без префикса `ALECA_`),
  `fissure_poll_interval_seconds: int = 60`,
  `fissure_source_base_url: str = "https://api.warframestat.us"`.
- `.env.example` + docker-compose (backend-сервис): `TG_API_KEY=`.
- 3 новые таблицы в `schema.sql` (`CREATE TABLE IF NOT EXISTS`).

## 12. Тестирование (TDD)

- `matches` — все комбинации осей, NULL=any, catch-all.
- `parse_fissure` — фикстура `tests/fixtures/wfm_fissures_sample.json`
  (3 реальных объекта: обычный / Steel Path / Void Storm) → нормализованные
  `Fissure` + парс планеты.
- `FissureClient.get_fissures` — `pytest-httpx`: парсинг + TTL-кэш (второй вызов
  не ходит в сеть).
- `TelegramClient.send_message` — `pytest-httpx`: бьёт в правильный URL с
  правильным телом.
- `TelegramBot.handle_updates` — payload `getUpdates` с `/start` → чат
  зарегистрирован в `Repo` + отправлен ответ (fake client).
- `FissurePoller.tick` — fake client + fake Telegram: рассылка по совпадению,
  **дедуп** (второй тик — без повтора), новый разрыв — шлёт, нет подписок — noop.
- `Repo` — CRUD подписок, регистрация чатов (идемпотентность), журнал дедупа,
  prune.
- `fissures/router` — через FastAPI `dependency_overrides` + `TestClient`
  (лёгкие проверки CRUD без полного lifespan).

## 13. Не-цели / явный YAGNI

- Без Centrifugo для этой фичи (см. §10).
- Без персональных per-chat подписок (подписки глобальные, см. §6).
- Без webhook (только long-poll, см. §6).
- Без хранения истории разрывов (живой список — каждый раз свежий).

## 14. Риски

1. warframestat.us — сторонняя зависимость; недоступность → тик логируется и
   пропускается, процесс не падает.
2. Открытый перечень `missionType` (строки от warframestat.us авторитетны) →
   `/fissures/meta` отдаёт объединение статического списка и того, что реально в
   live, чтобы дропдаун всегда покрывал текущие варианты.
3. Транзиентный сбой `sendMessage` после записи в журнал → разрыв пропущен (для
   личного инструмента приемлемо).
