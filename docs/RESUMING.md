# Resuming the Project in a New Session

This document tells a fresh Claude Code session exactly where the work paused.

## TL;DR for the new session

```
1. cd "B:\Sync\Programming\projects\aleca frame inventory"
2. Read docs/superpowers/plans/2026-05-25-phase-b2a-history-signals.md
3. Invoke superpowers:subagent-driven-development and start with Task 1
```

Or just paste this into the new session:

> Continue executing `docs/superpowers/plans/2026-05-25-phase-b2a-history-signals.md` via `superpowers:subagent-driven-development`. Branch `feature/b2a-history-signals` is already checked out (from master @ `0f262b3`). All previous phases (B.0 + B.1) are merged to master, 59 unit tests passing.

## Current state (snapshot at pause)

**Master** @ `0f262b3` — Phase B.0 + Phase B.1 complete, plus B.1 carry-forward fixes and one
inventory-unwrap fix. Tests: 59 unit + 5 e2e, all green.

**Active branch:** `feature/b2a-history-signals` (just recreated from master, empty — no commits yet).

**Stack status:** the docker-compose stack runs locally; the host-side
`decrypt-agent` is OPTIONAL — backend reads `data/lastData.json` from the
mounted volume. Real-time wiring (WS/RabbitMQ/Centrifugo) lights up when both
are running.

## What's done

- B.0 — foundation (docker-compose, decrypt-agent, frontend skeleton)
- B.1a — WFM REST client + 9 endpoints under `/wfm/*` and `/me/*`
- B.1b — 4 SolidJS pages (Dashboard / Inventory / PrimeParts / Sets)
- B.1c — real-time WFM-WS → RabbitMQ → Centrifugo → frontend live updates
- Carry-forward fixes (wss://, backoff reset, RabbitMQ retry, HMAC pad,
  127.0.0.1 default, me_router DI)
- `_unwrap_inventory_if_wrapped` (bridge.py) — handles AlecaFrame mission-event
  wrapper that nests the real inventory under `InventoryJson`

## What's next

**Phase B.2a — History storage + Signals engine + Endpoints** (10 tasks, ~5-7 days).

Plan: `docs/superpowers/plans/2026-05-25-phase-b2a-history-signals.md`

Outline:
1. Add `aiosqlite` dep
2. `db/schema.sql` (5 tables: order_snapshots, live_events, signal_events, wfm_items, set_compositions)
3. `db/repo.py` async queries + 4 tests
4. `wfm/history.py` write_snapshot helper + 2 tests
5. `wfm/sets_loader.py` build SetCompositions from AlecaFrame cachedData + 3 tests
6. `wfm/signals.py` — 9 signal functions + run_signals dispatcher + 7 tests
7. `wfm/history_router.py` — `/history/{slug}`, `/signals/active`, `/signals/feed`, `/me/dashboard-actions`
8. main.py — wire Repo + sets loader + history router; extend consumer
9. poller — periodic REST-snapshot job every 30 min (top 20 slugs)
10. README + smoke verification

After B.2a: write B.2b plan (frontend History page with ApexCharts + Signals feed page) and execute it.

## Useful starter commands

```powershell
# Verify state
git status
git log --oneline -10
docker compose ps
uv run pytest -v

# Bring stack up if you want live verification
./scripts/start-stack.ps1

# Smoke endpoints
curl http://127.0.0.1:8765/healthz | jq .
curl http://127.0.0.1:8765/summary | jq .section_counts
curl http://127.0.0.1:3000/api/healthz | jq .ok
```

## Project map

```
B:\Sync\Programming\projects\aleca frame inventory\
├── docs/
│   ├── RESUMING.md                          ← you are here
│   └── superpowers/
│       ├── specs/2026-05-24-alecaframe-trading-platform-design.md
│       └── plans/
│           ├── 2026-05-24-phase-b0-foundation.md            (done)
│           ├── 2026-05-25-phase-b1a-wfm-rest.md             (done)
│           ├── 2026-05-25-phase-b1b-frontend-pages.md       (done)
│           ├── 2026-05-25-phase-b1c-realtime.md             (done)
│           └── 2026-05-25-phase-b2a-history-signals.md      ← next
├── src/alecaframe_api/   (backend)
├── src/decrypt_agent/    (host tray app)
├── frontend/             (SolidJS)
├── docker-compose.yml
├── scripts/start-stack.ps1
└── tests/                (59 unit + 5 e2e)
```

## Conventions reminder

- **Pattern:** Subagent-Driven Development — fresh subagent per task, two-stage review,
  no human pause between tasks
- **Commit format:** Conventional Commits
- **Per-task DoD:** typecheck + build green, pytest green, smoke verify if applicable
- **Per-task fix cycle:** if reviewer flags Important+ issues, dispatch a fix subagent

## Open carry-forward (NOT blockers, just notes for later)

From B.1a/B.1b/B.1c reviews — see plan files' "Carry-forward items" sections.
None of these block B.2a; can be done as small cleanup chips between tasks.
