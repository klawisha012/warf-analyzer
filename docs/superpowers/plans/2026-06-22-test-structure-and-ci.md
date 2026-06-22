# Test Structure + CI/CD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize `tests/` into a clean unit/integration/e2e tree split by backend/frontend, add a frontend test runner (Vitest) and browser e2e (Playwright), introduce blocking lint/format (Ruff + ESLint/Prettier), and wire a 3-job GitHub Actions pipeline.

**Architecture:** Monorepo — Python backend (`backend/`, uv, FastAPI, pytest) + SolidJS frontend (`frontend/`, Vite, TypeScript). Backend tests live at the repo root and run via `uv run --project backend pytest`. Frontend test files live under the root `tests/` tree but are driven by Vitest/Playwright configs inside `frontend/` (which own `node_modules` and the `@` alias). E2E runs Playwright against `vite preview` with the backend stubbed by request interception, so CI needs no live services.

**Tech Stack:** Python 3.12 + uv + Ruff + pytest; SolidJS + Vite 6 + TypeScript 5.7 + Vitest + Playwright + ESLint 9 (flat) + Prettier; GitHub Actions.

## Global Constraints

- Python `>=3.12`; backend managed by **uv** (`uv.lock`); run tests with `uv run --project backend pytest` from the repo root.
- Node `>=20.11` (configs use `import.meta.dirname`); CI uses Node 22; frontend managed by **npm** (`package-lock.json`).
- Lint/format steps in CI are **blocking** — fix all existing violations so the first CI run is green.
- Backend tests must stay importable on Linux. (Verified: win32 deps `pystray`/`win10toast` are imported lazily inside functions in `decrypt_agent/main.py`; `alecaframe_api` never imports them at module level.)
- `from tests import FIXTURES_DIR` / `REPO_ROOT` must keep working after the data move — only `tests/__init__.py` changes; test files reference data via the constant, not hardcoded paths.
- GitHub Actions: top-level `permissions: contents: read`, `concurrency` with cancel-in-progress, actions pinned by major tag from trusted publishers. No secrets.
- No mypy (out of scope). Conventional-commit messages in English; one atomic commit per task.

---

### Task 1: Reorganize the `tests/` tree (backend moves, dir scaffold, pytest config)

**Files:**
- Move: `tests/unit/test_*.py` → `tests/unit/backend/`
- Move: `tests/test_data/fixtures/*.json` → `tests/test_data/backend/`
- Create: `tests/unit/backend/__init__.py`, `tests/fixtures/__init__.py`, `tests/unit/frontend/.gitkeep`, `tests/integration/frontend/.gitkeep`, `tests/e2e/flows/.gitkeep`, `tests/e2e/pages/.gitkeep`, `tests/test_data/frontend/.gitkeep`
- Delete: `tests/integration/frontend/__init__.py` (vestigial Python package marker; this dir holds TS tests now)
- Modify: `tests/__init__.py`, `pytest.ini`

**Interfaces:**
- Produces: `FIXTURES_DIR` now resolves to `tests/test_data/backend`; directory homes `tests/unit/frontend`, `tests/integration/frontend`, `tests/e2e/flows`, `tests/e2e/pages` for later tasks.

- [ ] **Step 1: Move backend unit tests into a `backend/` subpackage**

Run (Git Bash, from repo root):
```bash
mkdir -p tests/unit/backend
git mv tests/unit/test_*.py tests/unit/backend/
printf '"""Backend unit tests (pure, no I/O)."""\n' > tests/unit/backend/__init__.py
git add tests/unit/backend/__init__.py
```

- [ ] **Step 2: Move static fixture data and scaffold the new directories**

Run:
```bash
mkdir -p tests/test_data/backend tests/test_data/frontend
git mv tests/test_data/fixtures/*.json tests/test_data/backend/
rmdir tests/test_data/fixtures 2>/dev/null || true

# TS test homes (no __init__.py — these are not Python packages)
git rm tests/integration/frontend/__init__.py
mkdir -p tests/unit/frontend tests/e2e/flows tests/e2e/pages tests/fixtures
printf '' > tests/unit/frontend/.gitkeep
printf '' > tests/integration/frontend/.gitkeep
printf '' > tests/e2e/flows/.gitkeep
printf '' > tests/e2e/pages/.gitkeep
printf '' > tests/test_data/frontend/.gitkeep
printf '"""Reusable test code (builders, factories, helpers) shared across suites."""\n' > tests/fixtures/__init__.py
git add tests/unit/frontend/.gitkeep tests/integration/frontend/.gitkeep tests/e2e/flows/.gitkeep tests/e2e/pages/.gitkeep tests/test_data/frontend/.gitkeep tests/fixtures/__init__.py
```

- [ ] **Step 3: Point `FIXTURES_DIR` at the new data location**

Edit `tests/__init__.py` to:
```python
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "test_data" / "backend"
```

- [ ] **Step 4: Keep pytest from descending into TS / e2e-browser dirs**

Edit `pytest.ini` to:
```ini
[pytest]
# Backend lives in backend/ (pyproject.toml + uv.lock there); tests stay at the
# repo root. Run from the repo root with the backend env:
#   uv run --project backend pytest
testpaths = tests
asyncio_mode = auto
addopts = -ra -q -m "not e2e"
# Matched against directory BASENAMES (pytest fnmatch). `frontend` covers both
# unit/frontend and integration/frontend; `flows`/`pages` cover the Playwright dirs.
norecursedirs = frontend flows pages node_modules .venv
markers =
    e2e: requires a running docker-compose stack
```

- [ ] **Step 5: Verify the full backend suite still passes after the move**

Run: `uv run --project backend pytest`
Expected: PASS — same number of tests as before, e2e deselected (`-m "not e2e"`). No collection or import errors.

- [ ] **Step 6: Commit**

```bash
git add tests/ pytest.ini
git commit -m "test: split unit suite by backend/frontend and scaffold test tree"
```

---

### Task 2: Backend lint + format (Ruff)

**Files:**
- Create: `ruff.toml` (repo root — single config covering `backend/src` and `tests/`)
- Modify: `backend/pyproject.toml` (add `ruff` to the dev group)
- Modify: many `backend/src/**` and `tests/**` files (auto-applied format/lint fixes)

**Interfaces:**
- Produces: repo-root `ruff.toml`; the commands `uv run --project backend ruff format --check backend/src tests` and `uv run --project backend ruff check backend/src tests` exit 0 (consumed by the CI backend job in Task 6).

> Config lives at the **repo root**, not in `backend/pyproject.toml`: Ruff resolves config from each file's nearest ancestor, and `tests/` sits above `backend/`. A root `ruff.toml` governs both trees consistently; the Ruff *binary* still comes from the backend dev group.

- [ ] **Step 1: Add Ruff to the backend dev dependency group**

Edit `backend/pyproject.toml`, `[dependency-groups]` → `dev`:
```toml
[dependency-groups]
dev = [
    "fakeredis>=2.26",
    "pytest>=9.0.3",
    "pytest-asyncio>=1.3.0",
    "pytest-httpx>=0.36.2",
    "ruff>=0.9",
]
```

- [ ] **Step 2: Create the root Ruff config**

Create `ruff.toml`:
```toml
# Single source of truth for backend/src and tests/ (both are linted from the
# repo root: `uv run --project backend ruff check backend/src tests`).
target-version = "py312"
line-length = 88

[lint]
select = ["E", "F", "W", "I", "UP", "B"]
ignore = ["E501"]  # line length is enforced by `ruff format`, not the linter

[lint.per-file-ignores]
"**/__init__.py" = ["F401"]  # re-exports are intentional

[lint.isort]
known-first-party = ["alecaframe_api", "decrypt_agent", "tests"]
```

- [ ] **Step 3: Sync the env so Ruff is available**

Run: `uv sync --project backend`
Expected: resolves and installs `ruff` into the backend env.

- [ ] **Step 4: Apply formatting**

Run: `uv run --project backend ruff format backend/src tests`
Expected: "N files reformatted, M files left unchanged" (a large N is expected — the codebase was never auto-formatted).

- [ ] **Step 5: Apply safe lint autofixes**

Run: `uv run --project backend ruff check --fix backend/src tests`
Expected: import sorting (`I`) and trivial fixes applied automatically.

- [ ] **Step 6: Resolve any residual lint findings by hand**

Run: `uv run --project backend ruff check backend/src tests`
For each remaining finding: fix the code. If a specific rule is genuinely inappropriate for this codebase, narrow it via `ignore` or `per-file-ignores` in `ruff.toml` with a one-line rationale comment — do not blanket-disable categories.
Expected after fixes: "All checks passed!"

- [ ] **Step 7: Verify format-check is clean and tests still pass**

Run:
```bash
uv run --project backend ruff format --check backend/src tests
uv run --project backend ruff check backend/src tests
uv run --project backend pytest
```
Expected: format-check reports no changes; lint passes; pytest green (formatting must not change behavior).

- [ ] **Step 8: Commit**

```bash
git add ruff.toml backend/pyproject.toml backend/uv.lock backend/src tests
git commit -m "style: add Ruff lint+format and apply across backend and tests"
```

---

### Task 3: Frontend lint + format (ESLint 9 flat + Prettier)

**Files:**
- Create: `frontend/eslint.config.js`, `frontend/.prettierrc.json`, `frontend/.prettierignore`
- Modify: `frontend/package.json` (devDeps + scripts), `frontend/package-lock.json`
- Modify: many `frontend/src/**` files (auto-applied format/lint fixes)

**Interfaces:**
- Produces: npm scripts `lint`, `lint:fix`, `format`, `format:check` (consumed by the CI frontend job in Task 6).

- [ ] **Step 1: Install ESLint + Prettier toolchain**

Run (from `frontend/`):
```bash
cd frontend
npm install -D eslint@^9 @eslint/js@^9 typescript-eslint@^8 eslint-plugin-solid@^0.14 eslint-config-prettier@^9 globals@^15 prettier@^3
```

- [ ] **Step 2: Add the ESLint flat config**

Create `frontend/eslint.config.js`:
```js
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import solid from "eslint-plugin-solid/configs/typescript";
import prettier from "eslint-config-prettier";
import globals from "globals";

export default tseslint.config(
  {
    ignores: [
      "dist/",
      "coverage/",
      "playwright-report/",
      "test-results/",
      "node_modules/",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    ...solid,
    languageOptions: {
      parser: tseslint.parser,
      globals: { ...globals.browser },
    },
  },
  prettier,
);
```

- [ ] **Step 3: Add Prettier config + ignore**

Create `frontend/.prettierrc.json`:
```json
{
  "semi": true,
  "singleQuote": false,
  "printWidth": 100,
  "trailingComma": "all"
}
```

Create `frontend/.prettierignore`:
```
dist
coverage
playwright-report
test-results
node_modules
package-lock.json
```

- [ ] **Step 4: Add scripts**

Edit `frontend/package.json` `scripts` to include (keep existing `dev`/`build`/`preview`/`typecheck`):
```json
{
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "lint": "eslint .",
    "lint:fix": "eslint . --fix",
    "format": "prettier --write .",
    "format:check": "prettier --check ."
  }
}
```

- [ ] **Step 5: Apply formatting and lint autofixes**

Run (from `frontend/`):
```bash
npm run format
npm run lint:fix
```
Expected: Prettier rewrites `src/**`; ESLint autofixes what it can.

- [ ] **Step 6: Resolve residual lint findings by hand**

Run: `npm run lint`
Fix each remaining error. SolidJS-specific note: `eslint-plugin-solid` may flag reactivity issues (e.g., destructuring props) — prefer fixing the code; only disable a rule inline with a rationale if it is a genuine false positive.
Expected after fixes: ESLint exits 0.

- [ ] **Step 7: Verify format-check, lint, typecheck, and build are all green**

Run (from `frontend/`):
```bash
npm run format:check
npm run lint
npm run typecheck
npm run build
```
Expected: all four pass (formatting must not break the TypeScript build).

- [ ] **Step 8: Commit**

```bash
cd ..
git add frontend/eslint.config.js frontend/.prettierrc.json frontend/.prettierignore frontend/package.json frontend/package-lock.json frontend/src
git commit -m "style: add ESLint+Prettier to frontend and apply across src"
```

---

### Task 4: Frontend unit/integration tests (Vitest)

**Files:**
- Create: `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`
- Create: `tests/unit/frontend/format.test.ts`, `tests/integration/frontend/Badge.test.tsx`
- Modify: `frontend/package.json` (devDeps + scripts), `frontend/package-lock.json`

**Interfaces:**
- Consumes: `@/lib/format` exports `fmtPlat`, `fmtInt`, `prettySlug`, `wfmUrl`; `@/components/Badge` default export `Badge(props: { variant?: ...; children })`.
- Produces: npm scripts `test`, `test:watch`, `coverage` (consumed by the CI frontend job in Task 6).

- [ ] **Step 1: Install Vitest + Solid testing toolchain**

Run (from `frontend/`):
```bash
cd frontend
npm install -D vitest@^2 jsdom@^25 @solidjs/testing-library@^0.8 @testing-library/jest-dom@^6 @vitest/coverage-v8@^2
```

- [ ] **Step 2: Add the Vitest config (reads test files from the root `tests/` tree)**

Create `frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";
import solid from "vite-plugin-solid";
import { resolve } from "node:path";

const here = import.meta.dirname; // frontend/
const repoRoot = resolve(here, "..");

export default defineConfig({
  plugins: [solid()],
  resolve: { alias: { "@": resolve(here, "src") } },
  // Test files live outside the Vite root (frontend/) — allow serving them.
  server: { fs: { allow: [here, repoRoot] } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: [resolve(here, "vitest.setup.ts")],
    include: [
      resolve(repoRoot, "tests/unit/frontend/**/*.{test,spec}.{ts,tsx}"),
      resolve(repoRoot, "tests/integration/frontend/**/*.{test,spec}.{ts,tsx}"),
    ],
    coverage: {
      provider: "v8",
      reportsDirectory: resolve(here, "coverage"),
      include: ["src/**"],
    },
  },
});
```

- [ ] **Step 3: Add the Vitest setup file**

Create `frontend/vitest.setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Add test scripts**

Add to `frontend/package.json` `scripts`:
```json
{
  "test": "vitest run",
  "test:watch": "vitest",
  "coverage": "vitest run --coverage"
}
```

- [ ] **Step 5: Write the unit example test (pure helpers)**

Create `tests/unit/frontend/format.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { fmtPlat, fmtInt, prettySlug, wfmUrl } from "@/lib/format";

describe("format helpers", () => {
  it("formats platinum with a thousands separator and suffix", () => {
    expect(fmtPlat(1234)).toBe("1,234p");
  });

  it("returns an em dash for nullish platinum", () => {
    expect(fmtPlat(null)).toBe("—");
    expect(fmtPlat(undefined)).toBe("—");
  });

  it("formats integers with separators", () => {
    expect(fmtInt(32539253)).toBe("32,539,253");
  });

  it("title-cases underscore slugs", () => {
    expect(prettySlug("kronen_prime_handle")).toBe("Kronen Prime Handle");
  });

  it("builds a warframe.market url from a slug", () => {
    expect(wfmUrl("kronen_prime_set")).toBe(
      "https://warframe.market/items/kronen_prime_set",
    );
  });
});
```

- [ ] **Step 6: Run the suite and confirm the unit test passes**

Run (from `frontend/`): `npm run test`
Expected: 1 file (`format.test.ts`), 5 passing assertions. (If `import.meta.dirname` is undefined, your Node is < 20.11 — upgrade Node.)

- [ ] **Step 7: Write the integration example test (component render)**

Create `tests/integration/frontend/Badge.test.tsx`:
```tsx
import { describe, it, expect } from "vitest";
import { render } from "@solidjs/testing-library";
import Badge from "@/components/Badge";

describe("<Badge>", () => {
  it("renders its children", () => {
    const { getByText } = render(() => <Badge variant="good">Online</Badge>);
    expect(getByText("Online")).toBeInTheDocument();
  });

  it("maps the variant onto a chip class", () => {
    const { getByText } = render(() => <Badge variant="good">Online</Badge>);
    expect(getByText("Online").className).toContain("online");
  });

  it("defaults to the neutral chip", () => {
    const { getByText } = render(() => <Badge>Plain</Badge>);
    expect(getByText("Plain").className).toBe("chip");
  });
});
```

- [ ] **Step 8: Run the whole Vitest suite**

Run (from `frontend/`): `npm run test`
Expected: 2 files, 8 tests, all passing.

- [ ] **Step 9: Commit**

```bash
cd ..
git add frontend/vitest.config.ts frontend/vitest.setup.ts frontend/package.json frontend/package-lock.json tests/unit/frontend/format.test.ts tests/integration/frontend/Badge.test.tsx
git commit -m "test: add Vitest with Solid testing-library and example tests"
```

---

### Task 5: Browser e2e (Playwright) with stubbed backend

**Files:**
- Create: `frontend/playwright.config.ts`, `tests/e2e/pages/app-shell.page.ts`, `tests/e2e/flows/smoke.spec.ts`
- Modify: `frontend/package.json` (devDep + scripts), `frontend/package-lock.json`

**Interfaces:**
- Consumes: built frontend served by `vite preview` on `127.0.0.1:4173`; the SPA shell renders `aside.sidebar` and `.brand-name`, and `index.html` sets `<title>AlecaFrame</title>`; the app fetches `/api/**` (stubbed via `page.route`).
- Produces: npm scripts `e2e`, `e2e:install` (consumed by the CI e2e job in Task 6).

- [ ] **Step 1: Install Playwright test runner**

Run (from `frontend/`):
```bash
cd frontend
npm install -D @playwright/test@^1
npx playwright install --with-deps chromium
```

- [ ] **Step 2: Add the Playwright config (preview server + chromium)**

Create `frontend/playwright.config.ts`:
```ts
import { defineConfig, devices } from "@playwright/test";
import { resolve } from "node:path";

export default defineConfig({
  testDir: resolve(import.meta.dirname, "../tests/e2e/flows"),
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run preview -- --port 4173 --host 127.0.0.1",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
```

- [ ] **Step 3: Add the Page Object for the app shell**

Create `tests/e2e/pages/app-shell.page.ts`:
```ts
import type { Page, Locator } from "@playwright/test";

/** Page Object for the persistent app shell (sidebar + brand). */
export class AppShellPage {
  readonly page: Page;
  readonly sidebar: Locator;
  readonly brand: Locator;

  constructor(page: Page) {
    this.page = page;
    this.sidebar = page.locator("aside.sidebar");
    this.brand = page.locator(".brand-name");
  }

  /** Stub every backend call so the SPA renders without a live backend. */
  async stubApi(): Promise<void> {
    await this.page.route("**/api/**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true, wfm_username: "Tenno", items: [], total: 0 }),
      }),
    );
  }

  async goto(): Promise<void> {
    await this.stubApi();
    await this.page.goto("/");
  }
}
```

- [ ] **Step 4: Add the smoke flow**

Create `tests/e2e/flows/smoke.spec.ts`:
```ts
import { test, expect } from "@playwright/test";
import { AppShellPage } from "../pages/app-shell.page";

test("app shell renders without a live backend", async ({ page }) => {
  const shell = new AppShellPage(page);
  await shell.goto();

  await expect(page).toHaveTitle("AlecaFrame");
  await expect(shell.sidebar).toBeVisible();
  await expect(shell.brand).toContainText("Frame");
});
```

- [ ] **Step 5: Add e2e scripts**

Add to `frontend/package.json` `scripts`:
```json
{
  "e2e": "playwright test",
  "e2e:install": "playwright install --with-deps chromium"
}
```

- [ ] **Step 6: Build the frontend, then run the flow**

Run (from `frontend/`):
```bash
npm run build
npm run e2e
```
Expected: `vite preview` boots on 4173, chromium runs `smoke.spec.ts`, 1 test passes. (Playwright auto-starts/stops the preview server via `webServer`.)

- [ ] **Step 7: Commit**

```bash
cd ..
git add frontend/playwright.config.ts frontend/package.json frontend/package-lock.json tests/e2e/pages/app-shell.page.ts tests/e2e/flows/smoke.spec.ts
git commit -m "test: add Playwright browser e2e with stubbed backend"
```

---

### Task 6: GitHub Actions CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: Task 2 commands (`ruff format --check` / `ruff check`), Task 3–5 npm scripts (`format:check`, `lint`, `typecheck`, `test`, `build`, `e2e`), and `uv run --project backend pytest`.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [master, main]
  pull_request:

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Sync backend env
        run: uv sync --project backend
      - name: Ruff format check
        run: uv run --project backend ruff format --check backend/src tests
      - name: Ruff lint
        run: uv run --project backend ruff check backend/src tests
      - name: Pytest (unit + integration)
        run: uv run --project backend pytest

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run format:check
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test
      - run: npm run build

  e2e:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - name: Install Playwright browser
        run: npx playwright install --with-deps chromium
      - run: npm run build
      - run: npm run e2e
```

- [ ] **Step 2: Validate the YAML parses**

Run: `uv run --project backend python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ok')"`
Expected: `ok` (no parse error). (PyYAML ships transitively in the backend env; if absent, validate with any YAML linter.)

- [ ] **Step 3: Cross-check every referenced command exists**

Confirm by inspection that each script used in the workflow is defined: backend commands match Task 2; `format:check`/`lint`/`typecheck`/`test`/`build`/`e2e` exist in `frontend/package.json` (Tasks 3–5).
Expected: every `run:` line maps to a real command.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add GitHub Actions pipeline (backend, frontend, e2e)"
```

---

### Task 7: Documentation + `.gitignore` + full local verification

**Files:**
- Create: `tests/README.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: all commands established in Tasks 1–6.

- [ ] **Step 1: Write the test README (all three layers on one screen)**

Create `tests/README.md`:
```markdown
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
```

- [ ] **Step 2: Update `.gitignore` for the new generated artifacts**

Append to `.gitignore`:
```gitignore
# Tooling caches / test artifacts
.ruff_cache/
frontend/coverage/
frontend/playwright-report/
frontend/test-results/
frontend/.playwright/
```

- [ ] **Step 3: Full local verification sweep**

Run:
```bash
uv run --project backend ruff format --check backend/src tests
uv run --project backend ruff check backend/src tests
uv run --project backend pytest
cd frontend && npm run format:check && npm run lint && npm run typecheck && npm run test && npm run build && npm run e2e
```
Expected: every command green — this mirrors exactly what the three CI jobs run.

- [ ] **Step 4: Confirm nothing generated is tracked**

Run: `git status --porcelain`
Expected: only intended files; no `coverage/`, `playwright-report/`, `test-results/`, or `.ruff_cache/` showing as untracked.

- [ ] **Step 5: Commit**

```bash
cd ..
git add tests/README.md .gitignore
git commit -m "docs: add tests/README and ignore tooling artifacts"
```

---

## Notes for the executor

- **Worktree:** per project convention, run this plan in an isolated worktree branched from `master` HEAD (skill `superpowers:using-git-worktrees`). Inside a worktree the backend editable install + `frontend/node_modules` may need the PYTHONPATH/junction workaround noted in project memory.
- **Task order matters:** Task 1 (moves) precedes Task 2 (Ruff) so formatting lands on files in their final location. Tasks 3–5 build on each other's `package.json`/`package-lock.json` — run them in order to avoid lockfile churn.
- **Lint churn is expected and intended** (blocking-lint decision): Tasks 2 and 3 will touch many `src` files. Keep each task's reformat in its own commit so review stays legible.
