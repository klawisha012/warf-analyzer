# Tests

Layout mirrors the two halves of the stack and three test depths.

```
tests/
├── unit/          backend/ (pytest)   ·  frontend/ (Vitest)
├── integration/   backend/ (pytest)   ·  frontend/ (Vitest)
├── e2e/           flows/ + pages/ (Playwright)  ·  test_smoke_e2e.py (pytest, live stack)
├── fixtures/      reusable Python test code
└── test_data/     backend/ + frontend/  (static JSON samples)
```

## Backend (Python · pytest · uv)

Run from the repo root:

```bash
uv run --project backend pytest            # unit + integration (e2e deselected)
uv run --project backend pytest tests/unit/backend
uv run --project backend ruff check backend/src tests
uv run --project backend ruff format --check backend/src tests
```

Data samples are reached via `from tests import FIXTURES_DIR`
(`tests/test_data/backend`), never hardcoded paths.

## Frontend (SolidJS · Vitest)

Vitest/ESLint/Prettier configs live in `frontend/` (they own `node_modules` and
the `@ → src` alias); the test files live here under `tests/{unit,integration}/frontend`.

```bash
cd frontend
npm run test          # vitest run
npm run coverage
npm run lint
npm run format:check
```

## E2E (Playwright, stubbed backend)

Runs against a production build served by `vite preview`; `/api/**` is stubbed
via request interception, so no backend/docker/network is needed.

```bash
cd frontend
npm run e2e:install   # one-time: download chromium
npm run build
npm run e2e
```

## E2E (live stack, manual)

`tests/e2e/test_smoke_e2e.py` checks a running docker-compose stack and is
**excluded from CI** (marked `e2e`). Start the stack first, then:

```bash
./scripts/start-stack.ps1
uv run --project backend pytest tests/e2e/test_smoke_e2e.py -m e2e -v
```
