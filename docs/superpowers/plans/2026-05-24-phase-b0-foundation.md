# Phase B.0: Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Containerise the existing AlecaFrame backend, add docker-compose infrastructure (Redis + RabbitMQ + Centrifugo), introduce a host-side `decrypt-agent` that owns the Windows-only DLL bridge, and stand up a SolidJS frontend skeleton — all running with a single command.

**Architecture:** The Windows `AlecaFrameClientLib.dll` cannot run inside a Linux container, so we extract decryption into a tiny tray app on the host (`decrypt-agent`). The dockerised backend reads the JSON output through a shared volume and calls the agent over `host.docker.internal:8788` for on-demand refreshes. All other infrastructure (cache, broker, push) runs in compose.

**Tech Stack:** Python 3.13 + uv, FastAPI, pystray, Docker Compose, Redis 7, RabbitMQ 4, Centrifugo v6, SolidJS, Vite, Tailwind CSS 4, nginx.

---

## File Map

**Create:**
- `src/alecaframe_api/config.py` — pydantic-settings central config
- `src/decrypt_agent/__init__.py` — package marker
- `src/decrypt_agent/main.py` — host FastAPI + pystray tray app
- `tests/__init__.py` — test package marker
- `tests/conftest.py` — pytest fixtures
- `tests/test_bridge.py` — backend bridge tests
- `tests/test_decrypt_agent.py` — agent HTTP tests
- `docker-compose.yml` — full stack
- `.env.example` — env template
- `docker/backend/Dockerfile`
- `docker/backend/.dockerignore`
- `docker/poller/Dockerfile`
- `docker/frontend/Dockerfile`
- `docker/frontend/nginx.conf`
- `docker/centrifugo/config.json`
- `docker/rabbitmq/definitions.json`
- `docker/redis/redis.conf`
- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/tsconfig.node.json`
- `frontend/tailwind.config.ts`
- `frontend/postcss.config.js`
- `frontend/index.html`
- `frontend/.gitignore`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/api/client.ts`
- `scripts/start-stack.ps1`

**Modify:**
- `pyproject.toml` — add deps (`pydantic-settings` exists; add `pystray`, `pillow`, `pytest`, `pytest-asyncio`, `httpx[testing]`), add `[project.scripts]` `alecaframe-decrypt-agent` and `alecaframe-poller`
- `src/alecaframe_api/main.py` — make startup graceful when agent is unreachable
- `src/alecaframe_api/bridge.py` — replace pwsh subprocess with HTTP call to agent
- `src/alecaframe_api/__init__.py` — bump version to 0.2.0
- `README.md` — full rewrite of "Setup" and "Running" sections
- `.gitignore` — add `.env`, `node_modules`, `dist`, `frontend/.vite`

**Create (stub, becomes real in B.1):**
- `src/alecaframe_api/wfm/__init__.py`
- `src/alecaframe_api/wfm/poller.py` — entry-point stub that just logs and sleeps

---

## Conventions Used Throughout

- **Commit format:** Conventional Commits (`feat:`, `chore:`, `refactor:`, `test:`, `docs:`)
- **All test commands:** run from project root with `uv run pytest ...`
- **Working directory for shell snippets:** `B:\Sync\Programming\projects\aleca frame inventory` (the project root)
- **Branch:** assume `main`. If the engineer wants a branch, they create it before Task 1.

---

## Task 1: Add test dependencies + create test scaffolding

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Add dev deps via uv**

Run:
```powershell
uv add --dev pytest pytest-asyncio pytest-httpx
```

Expected: deps added, `uv.lock` updated, no errors.

- [ ] **Step 2: Configure pytest in pyproject.toml**

Open `pyproject.toml`, append at the end:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra -q"
```

- [ ] **Step 3: Create tests package**

Create `tests/__init__.py` (empty file).

- [ ] **Step 4: Create shared fixtures**

Create `tests/conftest.py`:

```python
"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Fresh data dir with realistic dummy lastData / deltas / _meta JSONs."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "lastData.json").write_text(
        json.dumps(
            {
                "PremiumCredits": 169,
                "RegularCredits": 32_539_253,
                "FusionPoints": 95_705,
                "PrimeTokens": 0,
                "TradesRemaining": 8,
                "GiftsRemaining": 15,
                "PlayerLevel": 15,
                "Suits": [
                    {
                        "ItemType": "/Lotus/Powersuits/Cowgirl/MesaPrime",
                        "XP": 125_738_693,
                        "ItemId": {"$oid": "test-mesa-id"},
                    }
                ],
                "RawUpgrades": [],
                "MiscItems": [],
                "Recipes": [],
            }
        ),
        encoding="utf-8",
    )
    (d / "deltas.json").write_text(
        json.dumps({"savedCleanly": True, "previousMiscState": [], "currentDeltas": {}}),
        encoding="utf-8",
    )
    (d / "_meta.json").write_text(
        json.dumps(
            {
                "ok": True,
                "elapsed_ms": 200,
                "meta": {
                    "wfm_username": "test-user",
                    "aleca_version": "2.6.87",
                    "extension_dir": "C:/fake",
                    "aleca_data_dir": "C:/fake",
                    "cached_json_dir": "C:/fake/json",
                },
            }
        ),
        encoding="utf-8",
    )
    return d
```

- [ ] **Step 5: Verify pytest discovers tests**

Run:
```powershell
uv run pytest --collect-only
```

Expected: no errors. Output ends with "no tests ran in 0.0Xs" (no test files yet — that's fine).

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml uv.lock tests/__init__.py tests/conftest.py
git commit -m "test: add pytest scaffolding and shared fixtures"
```

---

## Task 2: Central Settings via pydantic-settings

**Files:**
- Create: `src/alecaframe_api/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
"""Test that Settings reads env vars and applies sensible defaults."""
from __future__ import annotations

import importlib

import pytest


def reload_settings():
    """Reimport the module so module-level env reads happen again."""
    import alecaframe_api.config as cfg
    importlib.reload(cfg)
    return cfg.Settings()


def test_defaults_when_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "ALECA_AGENT_URL", "ALECA_REDIS_URL", "ALECA_RABBITMQ_URL",
        "ALECA_CENTRIFUGO_API", "ALECA_CENTRIFUGO_API_KEY",
        "ALECA_DATA_DIR", "ALECA_TTL_SECONDS", "ALECA_WFM_PLATFORM",
    ):
        monkeypatch.delenv(var, raising=False)
    s = reload_settings()
    assert s.agent_url.startswith("http://")
    assert s.redis_url.startswith("redis://")
    assert s.ttl_seconds == 60
    assert s.wfm_platform == "pc"


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALECA_AGENT_URL", "http://example:9999")
    monkeypatch.setenv("ALECA_TTL_SECONDS", "120")
    monkeypatch.setenv("ALECA_WFM_PLATFORM", "xbox")
    s = reload_settings()
    assert s.agent_url == "http://example:9999"
    assert s.ttl_seconds == 120
    assert s.wfm_platform == "xbox"
```

- [ ] **Step 2: Run test, verify it fails**

```powershell
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'alecaframe_api.config'`.

- [ ] **Step 3: Create the config module**

Create `src/alecaframe_api/config.py`:

```python
"""Centralised settings loaded from environment variables.

All env vars share the `ALECA_` prefix and are case-insensitive.
Loaded once at process start; values are immutable.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Platform = Literal["pc", "xbox", "ps4", "switch"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALECA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # decrypt-agent (host-side service)
    agent_url: str = "http://host.docker.internal:8788"
    agent_token_path: str = "/wfm-token"
    agent_refresh_path: str = "/refresh"
    agent_toast_path: str = "/toast"

    # infra
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://aleca:aleca-local@rabbitmq:5672/"
    centrifugo_api: str = "http://centrifugo:8000/api"
    centrifugo_api_key: str = "change-me-in-env"
    centrifugo_token_hmac_secret: str = "change-me-in-env"

    # filesystem
    data_dir: Path = Path("/data")
    sqlite_path: Path = Path("/data/wfm_history.db")
    aleca_data_home: Path | None = None  # set by agent on host, unset in container

    # behaviour
    ttl_seconds: int = 60
    log_level: str = "INFO"

    # warframe.market specifics
    wfm_platform: Platform = "pc"
    wfm_language: str = "en"
    wfm_rate_limit_per_second: int = 3

    # uvicorn-only (used by the `run()` entry point in main.py)
    host: str = "0.0.0.0"
    port: int = 8765
    reload: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor; use this everywhere except in tests that need reload."""
    return Settings()
```

- [ ] **Step 4: Run test, verify it passes**

```powershell
uv run pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/config.py tests/test_config.py
git commit -m "feat: add central Settings module with env-driven config"
```

---

## Task 3: `decrypt-agent` FastAPI service (host-side)

**Files:**
- Create: `src/decrypt_agent/__init__.py`
- Create: `src/decrypt_agent/main.py`
- Create: `tests/test_decrypt_agent.py`
- Modify: `pyproject.toml` (add `pystray`, `pillow`; add script `alecaframe-decrypt-agent`)

- [ ] **Step 1: Add runtime deps for the agent**

Run:
```powershell
uv add pystray pillow win10toast-click
```

Expected: deps added, `uv.lock` updated.

- [ ] **Step 2: Create package marker**

Create `src/decrypt_agent/__init__.py`:

```python
"""Host-side decrypt agent — wraps the Windows-only AlecaFrame DLL behind HTTP.

Runs as a system-tray app. Backend (in container) calls this over
host.docker.internal:8788 for on-demand refresh and to read the WFM JWT.
"""

__version__ = "0.1.0"
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_decrypt_agent.py`:

```python
"""HTTP-level tests for the host decrypt-agent."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def agent_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Build the agent app pointed at a tmp data dir, with subprocess monkey-patched."""
    out_dir = tmp_path / "data"
    out_dir.mkdir()
    (out_dir / "lastData.json").write_text('{"_test":1}', encoding="utf-8")

    token_file = tmp_path / "WFMarketToken.tk"
    token_file.write_text("FAKE.JWT.TOKEN", encoding="utf-8")

    monkeypatch.setenv("AGENT_OUT_DIR", str(out_dir))
    monkeypatch.setenv("AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("AGENT_DUMP_SCRIPT", "")  # disables real pwsh call

    from decrypt_agent.main import build_app
    return build_app()


@pytest.mark.asyncio
async def test_healthz(agent_app: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_get_wfm_token(agent_app: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.get("/wfm-token")
    assert r.status_code == 200
    assert r.json() == {"token": "FAKE.JWT.TOKEN"}


@pytest.mark.asyncio
async def test_refresh_without_script_returns_stub(agent_app: Any) -> None:
    """With AGENT_DUMP_SCRIPT empty, /refresh returns a stub result instead of running pwsh."""
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.post("/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stub"] is True


@pytest.mark.asyncio
async def test_toast_endpoint_accepts_payload(agent_app: Any) -> None:
    """Toast endpoint must accept title/body and return 202 even if no GUI."""
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.post("/toast", json={"title": "Hi", "body": "Test", "click_url": None})
    assert r.status_code in (202, 200)
```

- [ ] **Step 4: Run the tests, verify they fail**

```powershell
uv run pytest tests/test_decrypt_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'decrypt_agent'`.

- [ ] **Step 5: Implement the agent**

Create `src/decrypt_agent/main.py`:

```python
"""decrypt-agent — tiny FastAPI service that exposes the Windows DLL bridge.

Endpoints:
  GET  /healthz          — liveness
  GET  /wfm-token        — returns the WFM JWT from %LOCALAPPDATA%/AlecaFrame
  POST /refresh          — runs scripts/dump_inventory.ps1 (writes data/*.json)
  POST /toast            — shows a Windows toast notification

Configuration via env vars:
  AGENT_HOST                 (default: 127.0.0.1)
  AGENT_PORT                 (default: 8788)
  AGENT_OUT_DIR              (default: <project>/data)
  AGENT_DUMP_SCRIPT          (default: <project>/scripts/dump_inventory.ps1;
                              empty string disables real exec — used by tests)
  AGENT_TOKEN_FILE           (default: %LOCALAPPDATA%/AlecaFrame/WFMarketToken.tk)
  AGENT_PWSH                 (default: pwsh)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("decrypt_agent")

# ------------------------------------------------------------------ config


def _project_root() -> Path:
    # src/decrypt_agent/main.py  ->  project root is parents[2]
    return Path(__file__).resolve().parents[2]


def _env_path(key: str, default: Path) -> Path:
    v = os.getenv(key)
    return Path(v) if v else default


def _default_token_file() -> Path:
    appdata = os.getenv("LOCALAPPDATA", "")
    return Path(appdata) / "AlecaFrame" / "WFMarketToken.tk"


# ------------------------------------------------------------------ models


class ToastRequest(BaseModel):
    title: str = Field(..., max_length=200)
    body: str = Field("", max_length=1000)
    click_url: str | None = None
    duration: int = Field(5, ge=1, le=60)


class RefreshResult(BaseModel):
    ok: bool
    stub: bool = False
    elapsed_ms: int | None = None
    files: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    error: str | None = None


# ------------------------------------------------------------------ logic


async def _run_dump_script(script_path: Path, out_dir: Path, pwsh: str) -> dict[str, Any]:
    """Spawn pwsh + dump_inventory.ps1, return parsed JSON status."""
    if not script_path.exists():
        raise RuntimeError(f"script not found: {script_path}")
    proc = await asyncio.create_subprocess_exec(
        pwsh, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(script_path), "-OutDir", str(out_dir),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(f"pwsh exit {proc.returncode}: {stdout or stderr}")
    try:
        return json.loads(stdout.splitlines()[-1])
    except Exception as e:
        raise RuntimeError(f"could not parse pwsh output: {e!r}; raw={stdout!r}") from e


async def _show_toast(req: ToastRequest) -> None:
    """Schedule a Windows toast. Lazy import keeps tests/cross-platform clean."""
    try:
        from win10toast_click import ToastNotifier  # type: ignore[import-untyped]
    except Exception as e:
        log.warning("toast unavailable (%s); skipping", e)
        return

    def _cb() -> None:
        if req.click_url:
            import webbrowser
            webbrowser.open(req.click_url)

    def _show() -> None:
        ToastNotifier().show_toast(
            req.title, req.body, duration=req.duration,
            callback_on_click=_cb if req.click_url else None,
            threaded=True,
        )

    # toaster uses pythoncom and a hidden window; offload to thread
    await asyncio.get_running_loop().run_in_executor(None, _show)


# ------------------------------------------------------------------ app


def build_app() -> FastAPI:
    """Factory so tests can rebuild with fresh env vars."""
    out_dir = _env_path("AGENT_OUT_DIR", _project_root() / "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    dump_script_str = os.getenv("AGENT_DUMP_SCRIPT")
    dump_script = (
        Path(dump_script_str) if dump_script_str
        else _project_root() / "scripts" / "dump_inventory.ps1"
    )
    token_file = _env_path("AGENT_TOKEN_FILE", _default_token_file())
    pwsh = os.getenv("AGENT_PWSH", "pwsh")
    use_stub = dump_script_str == ""

    app = FastAPI(
        title="AlecaFrame decrypt-agent",
        version="0.1.0",
        description="Host-side DLL bridge for the dockerised backend.",
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "ok": True,
            "out_dir": str(out_dir),
            "dump_script": str(dump_script) if not use_stub else None,
            "token_file_exists": token_file.exists(),
        }

    @app.get("/wfm-token")
    async def wfm_token() -> dict[str, str]:
        if not token_file.exists():
            raise HTTPException(404, f"token file not found: {token_file}")
        token = token_file.read_text(encoding="utf-8").strip()
        if not token:
            raise HTTPException(500, "token file is empty")
        return {"token": token}

    @app.post("/refresh", response_model=RefreshResult)
    async def refresh() -> RefreshResult:
        if use_stub:
            return RefreshResult(ok=True, stub=True, elapsed_ms=0)
        try:
            result = await _run_dump_script(dump_script, out_dir, pwsh)
            return RefreshResult(**result)
        except Exception as e:
            log.exception("refresh failed")
            return RefreshResult(ok=False, error=str(e))

    @app.post("/toast", status_code=202)
    async def toast(req: ToastRequest) -> dict[str, str]:
        asyncio.create_task(_show_toast(req))
        return {"status": "scheduled"}

    return app


# default app for `uvicorn decrypt_agent.main:app`
app = build_app()
```

- [ ] **Step 6: Run tests, verify they pass**

```powershell
uv run pytest tests/test_decrypt_agent.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```powershell
git add src/decrypt_agent/__init__.py src/decrypt_agent/main.py tests/test_decrypt_agent.py pyproject.toml uv.lock
git commit -m "feat(agent): add decrypt-agent FastAPI service (healthz, wfm-token, refresh, toast)"
```

---

## Task 4: pystray tray wrapper + console entry point

**Files:**
- Modify: `src/decrypt_agent/main.py` (add `run()` + tray)
- Modify: `pyproject.toml` (add `[project.scripts]` entry)

- [ ] **Step 1: Append the runner to `main.py`**

Open `src/decrypt_agent/main.py` and append at the very end:

```python


# ------------------------------------------------------------------ tray + runner


def _make_tray_icon(stop_event: "asyncio.Event", out_dir: Path):
    """Build a pystray icon. Returns the Icon instance (caller calls .run())."""
    import pystray
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), color=(20, 24, 38))
    ImageDraw.Draw(img).rectangle((10, 10, 54, 54), outline=(120, 200, 255), width=4)

    def _on_open_data(_icon, _item) -> None:
        os.startfile(str(out_dir))  # type: ignore[attr-defined]  # Windows only

    def _on_refresh(_icon, _item) -> None:
        import urllib.request
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{os.getenv('AGENT_PORT', '8788')}/refresh",
                data=b"", timeout=30,
            )
        except Exception as e:
            log.warning("manual refresh failed: %s", e)

    def _on_quit(icon, _item) -> None:
        stop_event.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Refresh now", _on_refresh),
        pystray.MenuItem("Open data folder", _on_open_data),
        pystray.MenuItem("Quit", _on_quit),
    )
    return pystray.Icon("AlecaFrame Agent", img, "AlecaFrame decrypt-agent", menu)


def run() -> None:
    """Console entry point: serves FastAPI on 127.0.0.1:AGENT_PORT and shows tray icon.

    Tray and uvicorn run in parallel: uvicorn in an asyncio task, tray on the main thread.
    """
    import threading

    import uvicorn

    host = os.getenv("AGENT_HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_PORT", "8788"))
    out_dir = _env_path("AGENT_OUT_DIR", _project_root() / "data")
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=os.getenv("AGENT_LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    stop_event = asyncio.Event()

    def _serve() -> None:
        uvicorn.run(app, host=host, port=port, log_level=os.getenv("AGENT_LOG_LEVEL", "info").lower())

    server_thread = threading.Thread(target=_serve, daemon=True, name="agent-uvicorn")
    server_thread.start()

    # tray on the main thread (pywin32 / pystray requires it)
    if sys.platform != "win32":
        log.warning("non-Windows platform: tray disabled, running headless")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            return
        return

    icon = _make_tray_icon(stop_event, out_dir)
    icon.run()
```

- [ ] **Step 2: Register console script in `pyproject.toml`**

Open `pyproject.toml`. In the `[project.scripts]` table append:

```toml
alecaframe-decrypt-agent = "decrypt_agent.main:run"
```

Also extend the Hatch wheel packages:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/alecaframe_api", "src/decrypt_agent"]
```

- [ ] **Step 3: Reinstall the project so the new console script is picked up**

```powershell
uv sync
```

Expected: `alecaframe-decrypt-agent` is installed (visible under `.venv/Scripts/`).

- [ ] **Step 4: Smoke-test the agent end-to-end**

```powershell
$env:AGENT_DUMP_SCRIPT = ""   # use stub mode
Start-Process -FilePath "uv" -ArgumentList "run alecaframe-decrypt-agent" -PassThru | Tee-Object -Variable agentProc
Start-Sleep -Seconds 3
Invoke-RestMethod http://127.0.0.1:8788/healthz
Invoke-RestMethod -Method POST http://127.0.0.1:8788/refresh
Stop-Process -Id $agentProc.Id -Force
```

Expected: healthz returns `{ok: true}`, refresh returns `{ok: true, stub: true}`. A tray icon briefly appears.

- [ ] **Step 5: Commit**

```powershell
git add src/decrypt_agent/main.py pyproject.toml uv.lock
git commit -m "feat(agent): add tray icon + alecaframe-decrypt-agent console script"
```

---

## Task 5: Refactor `bridge.py` to talk to the agent over HTTP

The current `bridge.py` spawns `pwsh` itself. In B.0 the backend lives in a Linux container and cannot do that. It calls `decrypt-agent` over `host.docker.internal:8788` for refresh, and reads JSON from the mounted `/data` volume.

**Files:**
- Modify: `src/alecaframe_api/bridge.py`
- Modify: `src/alecaframe_api/main.py` (graceful startup, use Settings)
- Modify: `src/alecaframe_api/__init__.py` (bump version)
- Create: `tests/test_bridge.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_bridge.py`:

```python
"""Tests for the HTTP-bridge backend reading agent-decrypted JSON from disk."""
from __future__ import annotations

from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.bridge import AlecaBridge, BridgeError


@pytest.mark.asyncio
async def test_lastdata_reads_from_disk(tmp_data_dir: Path) -> None:
    br = AlecaBridge(agent_url="http://agent.invalid", data_dir=tmp_data_dir)
    br.reload_from_disk(force=True)
    data = await br.lastdata()
    assert data["PremiumCredits"] == 169


@pytest.mark.asyncio
async def test_refresh_calls_agent_then_reloads(
    tmp_data_dir: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://agent.test/refresh",
        method="POST",
        json={"ok": True, "stub": True, "elapsed_ms": 1, "files": {}, "meta": {}},
    )
    br = AlecaBridge(agent_url="http://agent.test", data_dir=tmp_data_dir)
    result = await br.refresh()
    assert result["ok"] is True
    data = await br.lastdata()
    assert data["PlayerLevel"] == 15


@pytest.mark.asyncio
async def test_refresh_agent_down_raises(
    tmp_data_dir: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_exception(
        Exception("connection refused"),
        url="http://agent.test/refresh", method="POST",
    )
    br = AlecaBridge(agent_url="http://agent.test", data_dir=tmp_data_dir)
    with pytest.raises(BridgeError):
        await br.refresh()


@pytest.mark.asyncio
async def test_lastdata_works_offline_if_disk_has_file(tmp_data_dir: Path) -> None:
    """Even if the agent is unreachable, on-disk JSON serves reads."""
    br = AlecaBridge(agent_url="http://nope.invalid", data_dir=tmp_data_dir)
    data = await br.lastdata()
    assert "PremiumCredits" in data
```

- [ ] **Step 2: Run tests, verify they fail**

```powershell
uv run pytest tests/test_bridge.py -v
```

Expected: failures — current `AlecaBridge` signature doesn't match (it takes `script=`, not `agent_url=`).

- [ ] **Step 3: Rewrite `bridge.py`**

Replace the entire contents of `src/alecaframe_api/bridge.py` with:

```python
"""Bridge between the backend and the host decrypt-agent.

The host runs `decrypt-agent` (FastAPI + pystray); it owns the DLL and writes
JSON to a folder that is mounted into this container as /data.

This module:
- reads parsed JSON files from disk (lazy, on demand)
- calls POST {agent_url}/refresh to ask the agent to re-decrypt
- maintains a tiny in-memory cache so re-reads are cheap
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger("alecaframe.bridge")


class BridgeError(RuntimeError):
    """Raised when /refresh fails or files cannot be loaded."""


@dataclass
class CacheEntry:
    data: dict[str, Any]
    loaded_at: float  # monotonic seconds
    source: str  # 'disk'


@dataclass
class AlecaBridge:
    """Talks to decrypt-agent for refresh and reads JSON from disk."""

    agent_url: str
    data_dir: Path
    ttl_seconds: int = 60
    refresh_timeout: float = 30.0

    _lastdata: CacheEntry | None = field(default=None, init=False, repr=False)
    _deltas: CacheEntry | None = field(default=None, init=False, repr=False)
    _meta: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # ----------------------------------------------------------- public reads

    async def lastdata(self, *, force: bool = False) -> dict[str, Any]:
        await self._ensure_loaded(force=force)
        if self._lastdata is None:
            raise BridgeError(f"no lastData.json on disk at {self.data_dir}")
        return self._lastdata.data

    async def deltas(self, *, force: bool = False) -> dict[str, Any]:
        await self._ensure_loaded(force=force)
        if self._deltas is None:
            raise BridgeError(f"no deltas.json on disk at {self.data_dir}")
        return self._deltas.data

    async def refresh(self) -> dict[str, Any]:
        async with self._lock:
            try:
                async with httpx.AsyncClient(timeout=self.refresh_timeout) as client:
                    r = await client.post(f"{self.agent_url.rstrip('/')}/refresh")
                    r.raise_for_status()
                    payload = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise BridgeError(f"agent /refresh failed: {e}") from e
            self.reload_from_disk(force=True)
            return payload

    # ------------------------------------------------------------- introspection

    @property
    def cache_status(self) -> dict[str, Any]:
        now = time.monotonic()

        def info(c: CacheEntry | None) -> dict[str, Any] | None:
            if c is None:
                return None
            return {
                "loaded_age_seconds": round(now - c.loaded_at, 2),
                "source": c.source,
                "top_level_keys": len(c.data) if isinstance(c.data, dict) else None,
            }

        return {
            "lastdata": info(self._lastdata),
            "deltas": info(self._deltas),
            "ttl_seconds": self.ttl_seconds,
            "data_dir": str(self.data_dir),
            "agent_url": self.agent_url,
        }

    @property
    def meta(self) -> dict[str, Any] | None:
        return self._meta

    # ---------------------------------------------------------- private helpers

    async def _ensure_loaded(self, *, force: bool) -> None:
        async with self._lock:
            if force or self._is_stale():
                self.reload_from_disk(force=True)

    def _is_stale(self) -> bool:
        if self._lastdata is None:
            return True
        return (time.monotonic() - self._lastdata.loaded_at) > self.ttl_seconds

    def reload_from_disk(self, *, force: bool) -> None:
        """Public so tests can pre-warm the cache without going through agent."""
        now = time.monotonic()
        for attr, fname in (("_lastdata", "lastData.json"), ("_deltas", "deltas.json")):
            path = self.data_dir / fname
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                log.warning("failed to parse %s: %s", path, e)
                continue
            setattr(self, attr, CacheEntry(data=data, loaded_at=now, source="disk"))
        meta_path = self.data_dir / "_meta.json"
        if meta_path.exists():
            try:
                self._meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
```

- [ ] **Step 4: Update `main.py` to use the new bridge constructor and Settings**

In `src/alecaframe_api/main.py` change the file-paths/lifespan block. Replace these lines:

```python
DATA_DIR = Path(os.getenv("ALECA_DATA_DIR", _DEFAULT_DATA_DIR))
SCRIPT_PATH = Path(os.getenv("ALECA_SCRIPT", _DEFAULT_SCRIPT))
PWSH_PATH = os.getenv("ALECA_PWSH", "pwsh")
TTL_SECONDS = int(os.getenv("ALECA_TTL_SECONDS", "60"))
ALECA_DATA_HOME = Path(
    os.getenv("ALECA_DATA_HOME") or
    (Path(os.getenv("LOCALAPPDATA", "")) / "AlecaFrame")
)
```

with:

```python
from .config import get_settings

_settings = get_settings()
DATA_DIR = _settings.data_dir
TTL_SECONDS = _settings.ttl_seconds
AGENT_URL = _settings.agent_url
# Static name DB still comes from the host (it ships with AlecaFrame).
# When backend runs in a container the engineer mounts it as /data/cachedData/json
# (handled by docker-compose in Task 9).
ALECA_DATA_HOME = _settings.aleca_data_home or (DATA_DIR / "cachedData" / "json").parent
```

Replace the lifespan function body. Find:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, resolver
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bridge = AlecaBridge(
        script=SCRIPT_PATH,
        data_dir=DATA_DIR,
        ttl_seconds=TTL_SECONDS,
        pwsh=PWSH_PATH,
    )
    resolver = NameResolver(ALECA_DATA_HOME / "cachedData" / "json")
    # warm-up: try a refresh but don't fail startup if decrypt fails;
    # the bridge still tries to reload from disk in that case so endpoints
    # can serve cached JSON.
    try:
        await bridge.refresh()
    except BridgeError as e:
        log.warning("startup refresh failed (%s); using disk fallback if available", e)
    yield
```

Replace with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, resolver
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bridge = AlecaBridge(
        agent_url=AGENT_URL,
        data_dir=DATA_DIR,
        ttl_seconds=TTL_SECONDS,
    )
    resolver = NameResolver(ALECA_DATA_HOME / "cachedData" / "json")
    # Backend MUST start cleanly even when the agent is offline. We prefer fresh
    # data, but tolerate every failure mode.
    try:
        await bridge.refresh()
    except BridgeError as e:
        log.warning("startup refresh failed (%s); reading whatever is on disk", e)
        bridge.reload_from_disk(force=True)
    yield
```

Also remove the now-unused `SCRIPT_PATH` and `PWSH_PATH` references elsewhere in the file (search for them — there should be none after this change; only the lifespan and `/meta` endpoint touched them, and `/meta` reads `br.meta` instead).

In the `/meta` endpoint replace:

```python
"script": str(SCRIPT_PATH),
"ttl_seconds": TTL_SECONDS,
```

with:

```python
"agent_url": AGENT_URL,
"ttl_seconds": TTL_SECONDS,
```

- [ ] **Step 5: Bump version**

Open `src/alecaframe_api/__init__.py` and change:

```python
__version__ = "0.1.0"
```

to:

```python
__version__ = "0.2.0"
```

- [ ] **Step 6: Run all tests, verify they pass**

```powershell
uv run pytest -v
```

Expected: every test in `test_config.py`, `test_decrypt_agent.py`, `test_bridge.py` passes.

- [ ] **Step 7: Smoke-test by hand**

```powershell
# terminal 1
$env:AGENT_DUMP_SCRIPT = ""
uv run alecaframe-decrypt-agent
```

```powershell
# terminal 2
$env:ALECA_DATA_DIR = "B:\Sync\Programming\projects\aleca frame inventory\data"
$env:ALECA_AGENT_URL = "http://127.0.0.1:8788"
uv run alecaframe-api
```

```powershell
# terminal 3
Invoke-RestMethod http://127.0.0.1:8765/healthz
Invoke-RestMethod -Method POST http://127.0.0.1:8765/refresh
```

Expected: both endpoints return 200; cache shows `lastdata.source = "disk"`.

Stop both processes (Ctrl+C / icon Quit).

- [ ] **Step 8: Commit**

```powershell
git add src/alecaframe_api/bridge.py src/alecaframe_api/main.py src/alecaframe_api/__init__.py tests/test_bridge.py
git commit -m "refactor(backend): bridge talks to decrypt-agent over HTTP; remove pwsh subprocess from container path"
```

---

## Task 6: Poller skeleton + `alecaframe-poller` console script

The real poller arrives in B.1; B.0 only ships a process that starts cleanly so the `poller` service in compose has a real entry point.

**Files:**
- Create: `src/alecaframe_api/wfm/__init__.py`
- Create: `src/alecaframe_api/wfm/poller.py`
- Modify: `pyproject.toml` (add script `alecaframe-poller`)

- [ ] **Step 1: Create the package marker**

Create `src/alecaframe_api/wfm/__init__.py`:

```python
"""WFM-integration submodule. Real work begins in phase B.1."""
```

- [ ] **Step 2: Create the poller stub**

Create `src/alecaframe_api/wfm/poller.py`:

```python
"""Poller worker entry point — stub for phase B.0.

In B.1 this gains:
  - APScheduler with WFM REST snapshots every 30 minutes
  - WFMSocketClient (long-running WS listener)
  - RabbitMQ command consumer (`wfm.commands`)

For now it just logs, idles, and responds to SIGTERM cleanly so docker-compose
can supervise it without restart loops.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from alecaframe_api.config import get_settings

log = logging.getLogger("alecaframe.poller")


async def _main() -> None:
    s = get_settings()
    logging.basicConfig(
        level=s.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("poller stub starting; will idle until B.1 lands")
    log.info("settings: agent=%s redis=%s rabbit=%s", s.agent_url, s.redis_url, s.rabbitmq_url)

    stop = asyncio.Event()

    def _handler() -> None:
        log.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            # Windows asyncio does not implement add_signal_handler
            signal.signal(sig, lambda *_: _handler())

    # heartbeat every 60s; will be replaced by real polling in B.1
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            log.debug("poller heartbeat")

    log.info("poller stopped")


def run() -> None:
    """Console entry point: `uv run alecaframe-poller`."""
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
```

- [ ] **Step 3: Register the console script**

In `pyproject.toml` under `[project.scripts]` add:

```toml
alecaframe-poller = "alecaframe_api.wfm.poller:run"
```

- [ ] **Step 4: Reinstall and smoke-test**

```powershell
uv sync
uv run alecaframe-poller
```

Expected output (then Ctrl+C):

```
... [INFO] alecaframe.poller: poller stub starting; will idle until B.1 lands
... [INFO] alecaframe.poller: settings: agent=http://host.docker.internal:8788 redis=redis://redis:6379/0 rabbit=...
```

Ctrl+C should exit within ~1s with `poller stopped`.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/wfm/__init__.py src/alecaframe_api/wfm/poller.py pyproject.toml uv.lock
git commit -m "feat: add poller stub + alecaframe-poller entry point"
```

---

## Task 7: Backend Dockerfile

**Files:**
- Create: `docker/backend/Dockerfile`
- Create: `docker/backend/.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

Create `docker/backend/.dockerignore`:

```
.venv
.git
.gitignore
data
docs
docker
frontend
__pycache__
.pytest_cache
.ruff_cache
.mypy_cache
*.pyc
node_modules
tests
```

- [ ] **Step 2: Create the Dockerfile**

Create `docker/backend/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7
# AlecaFrame backend / poller image.
# Same image, two entrypoints — chosen via `command:` in docker-compose.

FROM python:3.13-slim AS builder

# uv via the official image (cached layer)
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Install deps first (cache-friendly layer)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Now copy source and install the project itself
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13-slim AS runtime

RUN useradd -m -u 1000 aleca \
    && mkdir -p /data \
    && chown aleca:aleca /data

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --from=builder --chown=aleca:aleca /app/.venv /app/.venv
COPY --from=builder --chown=aleca:aleca /app/src /app/src

USER aleca
EXPOSE 8765

# Default to the API; the poller service overrides this in compose.
CMD ["alecaframe-api"]
```

- [ ] **Step 3: Build the image**

```powershell
docker build -f docker/backend/Dockerfile -t alecaframe-backend:dev .
```

Expected: build succeeds, final image ~150–200 MB.

- [ ] **Step 4: Smoke-test container starts and serves `/healthz`**

```powershell
docker run --rm -d --name aleca-test -p 18765:8765 `
    -e ALECA_AGENT_URL=http://invalid.example `
    -e ALECA_DATA_DIR=/data `
    alecaframe-backend:dev
Start-Sleep -Seconds 4
Invoke-RestMethod http://127.0.0.1:18765/healthz
docker rm -f aleca-test
```

Expected: `/healthz` returns 200 with `ok: true` (cache will be empty because no data is mounted — that's fine).

- [ ] **Step 5: Commit**

```powershell
git add docker/backend/Dockerfile docker/backend/.dockerignore
git commit -m "build: add backend Dockerfile (multi-stage, uv-based)"
```

---

## Task 8: Poller Dockerfile (reuses backend image)

The poller uses the same image; we just want a thin Dockerfile so `docker-compose` references a service-specific path. This keeps build outputs separable later if we want.

**Files:**
- Create: `docker/poller/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

Create `docker/poller/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7
# Poller image — identical to backend, different entrypoint.
# We re-derive from python:3.13-slim instead of FROM backend to keep this
# file self-contained (docker-compose can build either in any order).

FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON=python3.13 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime
RUN useradd -m -u 1000 aleca && mkdir -p /data && chown aleca:aleca /data
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder --chown=aleca:aleca /app/.venv /app/.venv
COPY --from=builder --chown=aleca:aleca /app/src /app/src
USER aleca
CMD ["alecaframe-poller"]
```

- [ ] **Step 2: Build and smoke-test**

```powershell
docker build -f docker/poller/Dockerfile -t alecaframe-poller:dev .
docker run --rm --name poller-test -e ALECA_LOG_LEVEL=INFO alecaframe-poller:dev &
Start-Sleep -Seconds 3
docker logs poller-test
docker rm -f poller-test
```

Expected: log shows `poller stub starting`, container stays running, log shows heartbeat config line.

- [ ] **Step 3: Commit**

```powershell
git add docker/poller/Dockerfile
git commit -m "build: add poller Dockerfile (shares image recipe with backend)"
```

---

## Task 9: Infrastructure compose services — Redis, RabbitMQ, Centrifugo

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `docker/redis/redis.conf`
- Create: `docker/rabbitmq/definitions.json`
- Create: `docker/centrifugo/config.json`

- [ ] **Step 1: Create the env template**

Create `.env.example`:

```env
# Backend / poller
ALECA_AGENT_URL=http://host.docker.internal:8788
ALECA_REDIS_URL=redis://redis:6379/0
ALECA_RABBITMQ_URL=amqp://aleca:aleca-local@rabbitmq:5672/
ALECA_CENTRIFUGO_API=http://centrifugo:8000/api
ALECA_CENTRIFUGO_API_KEY=local-dev-api-key-change-me
ALECA_CENTRIFUGO_TOKEN_HMAC_SECRET=local-dev-hmac-secret-change-me
ALECA_DATA_DIR=/data
ALECA_TTL_SECONDS=60
ALECA_WFM_PLATFORM=pc
ALECA_LOG_LEVEL=INFO

# Centrifugo (read by the container itself)
CENTRIFUGO_API_KEY=local-dev-api-key-change-me
CENTRIFUGO_TOKEN_HMAC_SECRET=local-dev-hmac-secret-change-me
```

- [ ] **Step 2: Create Redis config**

Create `docker/redis/redis.conf`:

```conf
# Local development — minimal hardening.
appendonly yes
appendfsync everysec
maxmemory 256mb
maxmemory-policy allkeys-lru
save ""
```

- [ ] **Step 3: Create RabbitMQ declarative definitions**

Create `docker/rabbitmq/definitions.json`:

```json
{
  "rabbit_version": "4.0.0",
  "users": [
    {
      "name": "aleca",
      "password": "aleca-local",
      "tags": "administrator"
    }
  ],
  "vhosts": [{ "name": "/" }],
  "permissions": [
    {
      "user": "aleca", "vhost": "/",
      "configure": ".*", "write": ".*", "read": ".*"
    }
  ],
  "exchanges": [
    { "name": "wfm",     "vhost": "/", "type": "topic", "durable": true,  "auto_delete": false },
    { "name": "signals", "vhost": "/", "type": "topic", "durable": true,  "auto_delete": false }
  ],
  "queues": [
    { "name": "wfm.live.orders", "vhost": "/", "durable": true, "auto_delete": false, "arguments": {} },
    { "name": "wfm.snapshots",   "vhost": "/", "durable": true, "auto_delete": false, "arguments": {} },
    { "name": "wfm.commands",    "vhost": "/", "durable": true, "auto_delete": false, "arguments": {} },
    { "name": "signals.new",     "vhost": "/", "durable": true, "auto_delete": false, "arguments": {} }
  ],
  "bindings": [
    { "source": "wfm",     "vhost": "/", "destination": "wfm.live.orders", "destination_type": "queue", "routing_key": "live.orders.*",  "arguments": {} },
    { "source": "wfm",     "vhost": "/", "destination": "wfm.snapshots",   "destination_type": "queue", "routing_key": "snapshots.*",   "arguments": {} },
    { "source": "wfm",     "vhost": "/", "destination": "wfm.commands",    "destination_type": "queue", "routing_key": "commands.*",    "arguments": {} },
    { "source": "signals", "vhost": "/", "destination": "signals.new",     "destination_type": "queue", "routing_key": "new.*",         "arguments": {} }
  ]
}
```

- [ ] **Step 4: Create Centrifugo config**

Create `docker/centrifugo/config.json`:

```json
{
  "engine": "memory",
  "log_level": "info",
  "address": "0.0.0.0",
  "port": 8000,
  "http_api": { "enabled": true },
  "http_api_key": "${CENTRIFUGO_API_KEY}",
  "client": {
    "allowed_origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
    "token": {
      "hmac_secret_key": "${CENTRIFUGO_TOKEN_HMAC_SECRET}"
    }
  },
  "channel": {
    "without_namespace": {
      "presence": false,
      "history_size": 10,
      "history_ttl": "60s"
    },
    "namespaces": [
      {
        "name": "alert",
        "presence": false,
        "history_size": 50,
        "history_ttl": "1h"
      },
      {
        "name": "wfm",
        "presence": false,
        "history_size": 100,
        "history_ttl": "10m"
      },
      {
        "name": "system",
        "presence": false,
        "history_size": 20,
        "history_ttl": "10m"
      }
    ]
  }
}
```

- [ ] **Step 5: Create the compose file (infra only — no backend yet)**

Create `docker-compose.yml`:

```yaml
name: alecaframe

x-backend-env: &backend-env
  ALECA_AGENT_URL: ${ALECA_AGENT_URL:-http://host.docker.internal:8788}
  ALECA_REDIS_URL: redis://redis:6379/0
  ALECA_RABBITMQ_URL: amqp://aleca:aleca-local@rabbitmq:5672/
  ALECA_CENTRIFUGO_API: http://centrifugo:8000/api
  ALECA_CENTRIFUGO_API_KEY: ${CENTRIFUGO_API_KEY:-local-dev-api-key-change-me}
  ALECA_DATA_DIR: /data
  ALECA_TTL_SECONDS: ${ALECA_TTL_SECONDS:-60}
  ALECA_WFM_PLATFORM: ${ALECA_WFM_PLATFORM:-pc}
  ALECA_LOG_LEVEL: ${ALECA_LOG_LEVEL:-INFO}

services:
  redis:
    image: redis:7-alpine
    container_name: aleca-redis
    restart: unless-stopped
    ports: ["127.0.0.1:6379:6379"]
    volumes:
      - redis-data:/data
      - ./docker/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
    command: ["redis-server", "/usr/local/etc/redis/redis.conf"]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  rabbitmq:
    image: rabbitmq:4-management-alpine
    container_name: aleca-rabbitmq
    restart: unless-stopped
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"
    environment:
      RABBITMQ_DEFAULT_USER: aleca
      RABBITMQ_DEFAULT_PASS: aleca-local
      RABBITMQ_LOAD_DEFINITIONS: "true"
      RABBITMQ_DEFINITIONS_FILE: /etc/rabbitmq/definitions.json
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
      - ./docker/rabbitmq/definitions.json:/etc/rabbitmq/definitions.json:ro
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 6

  centrifugo:
    image: centrifugo/centrifugo:v6
    container_name: aleca-centrifugo
    restart: unless-stopped
    ports: ["127.0.0.1:8000:8000"]
    environment:
      CENTRIFUGO_API_KEY: ${CENTRIFUGO_API_KEY:-local-dev-api-key-change-me}
      CENTRIFUGO_TOKEN_HMAC_SECRET: ${CENTRIFUGO_TOKEN_HMAC_SECRET:-local-dev-hmac-secret-change-me}
    volumes:
      - ./docker/centrifugo/config.json:/centrifugo/config.json:ro
    command: ["centrifugo", "-c", "/centrifugo/config.json"]
    ulimits:
      nofile: { soft: 65536, hard: 65536 }
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 6

volumes:
  redis-data:
  rabbitmq-data:
```

- [ ] **Step 6: Bring up the three services and verify health**

```powershell
Copy-Item .env.example .env -Force
docker compose up -d redis rabbitmq centrifugo
Start-Sleep -Seconds 12
docker compose ps
docker compose exec -T redis redis-cli ping
Invoke-RestMethod http://127.0.0.1:15672/api/overview -Credential (New-Object PSCredential('aleca',(ConvertTo-SecureString 'aleca-local' -AsPlainText -Force))) | Select-Object rabbitmq_version
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected:
- `redis-cli ping` returns `PONG`
- RabbitMQ overview returns a version string
- Centrifugo `/health` returns 200 / OK

Leave the stack running for the next task.

- [ ] **Step 7: Commit**

```powershell
git add docker-compose.yml .env.example docker/redis docker/rabbitmq docker/centrifugo
git commit -m "build: add docker-compose infra (redis, rabbitmq, centrifugo)"
```

---

## Task 10: Add backend + poller services to compose

**Files:**
- Modify: `docker-compose.yml` (append two services)

- [ ] **Step 1: Extend `docker-compose.yml`**

In `docker-compose.yml`, append the two services to the existing `services:` block (just before the top-level `volumes:` key):

```yaml
  backend:
    build:
      context: .
      dockerfile: docker/backend/Dockerfile
    container_name: aleca-backend
    restart: unless-stopped
    ports: ["127.0.0.1:8765:8765"]
    environment:
      <<: *backend-env
    volumes:
      - ./data:/data
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      redis: { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
      centrifugo: { condition: service_healthy }
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz',timeout=3).status==200 else 1)"]
      interval: 10s
      timeout: 5s
      retries: 6

  poller:
    build:
      context: .
      dockerfile: docker/poller/Dockerfile
    container_name: aleca-poller
    restart: unless-stopped
    command: ["alecaframe-poller"]
    environment:
      <<: *backend-env
    volumes:
      - ./data:/data:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      redis: { condition: service_healthy }
      rabbitmq: { condition: service_healthy }
```

- [ ] **Step 2: Build and bring up the two new services**

```powershell
docker compose build backend poller
docker compose up -d backend poller
Start-Sleep -Seconds 10
docker compose ps
Invoke-RestMethod http://127.0.0.1:8765/healthz
docker compose logs --tail=20 poller
```

Expected:
- `docker compose ps` shows backend and poller as `running (healthy)` / `running`
- `/healthz` returns `{ok: true, ...}`
- Poller logs show `poller stub starting`

- [ ] **Step 3: Commit**

```powershell
git add docker-compose.yml
git commit -m "build: add backend and poller services to docker-compose"
```

---

## Task 11: SolidJS frontend scaffolding

**Files:**
- Create everything in `frontend/`

- [ ] **Step 1: Initialise the frontend directory**

Create `frontend/package.json`:

```json
{
  "name": "alecaframe-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "@solidjs/router": "^0.15.0",
    "@tanstack/solid-query": "^5.62.0",
    "apexcharts": "^4.3.0",
    "centrifuge": "^5.3.0",
    "solid-apexcharts": "^0.4.0",
    "solid-js": "^1.9.4"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@types/node": "^22.10.0",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.7.0",
    "vite": "^6.0.0",
    "vite-plugin-solid": "^2.11.0"
  }
}
```

- [ ] **Step 2: TypeScript config**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "jsx": "preserve",
    "jsxImportSource": "solid-js",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "resolveJsonModule": true,
    "allowSyntheticDefaultImports": true,
    "types": ["vite/client"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler"
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 3: Vite config**

Create `frontend/vite.config.ts`:

```typescript
import { defineConfig } from "vite";
import solid from "vite-plugin-solid";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [solid(), tailwindcss()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
      "/connection": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: { sourcemap: true, outDir: "dist" },
});
```

- [ ] **Step 4: Tailwind v4 setup**

Create `frontend/tailwind.config.ts`:

```typescript
import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
} satisfies Config;
```

Create `frontend/postcss.config.js`:

```javascript
export default {
  plugins: { autoprefixer: {} },
};
```

- [ ] **Step 5: Entry HTML**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AlecaFrame</title>
  </head>
  <body class="bg-slate-950 text-slate-100">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: CSS entry**

Create `frontend/src/styles.css`:

```css
@import "tailwindcss";

:root {
  font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
  color-scheme: dark;
}
```

- [ ] **Step 7: API client wrapper**

Create `frontend/src/api/client.ts`:

```typescript
/** Thin fetch wrapper. Backend lives under /api (rewritten to backend root by Vite/nginx). */

export class ApiError extends Error {
  constructor(public status: number, public detail: string, public path: string) {
    super(`API ${status} on ${path}: ${detail}`);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = path.startsWith("/api") ? path : `/api${path.startsWith("/") ? "" : "/"}${path}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try {
      detail = JSON.parse(text).detail ?? text;
    } catch {
      /* keep raw */
    }
    throw new ApiError(res.status, detail, url);
  }
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
```

- [ ] **Step 8: App entry + Hello World**

Create `frontend/src/main.tsx`:

```typescript
/* @refresh reload */
import { render } from "solid-js/web";
import { Router, Route } from "@solidjs/router";
import { QueryClient, QueryClientProvider } from "@tanstack/solid-query";

import App from "./App";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, refetchOnWindowFocus: false },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("missing #root");

render(
  () => (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Route path="/" component={App} />
      </Router>
    </QueryClientProvider>
  ),
  root,
);
```

Create `frontend/src/App.tsx`:

```typescript
import { createQuery } from "@tanstack/solid-query";
import { api } from "./api/client";

type ApiInfo = {
  name: string;
  version: string;
  docs_url: string;
  endpoints: string[];
};

type HealthResponse = {
  ok: boolean;
  wfm_username: string | null;
  aleca_version: string | null;
  cache: Record<string, unknown>;
};

export default function App() {
  const info = createQuery(() => ({
    queryKey: ["info"],
    queryFn: () => api<ApiInfo>("/"),
  }));
  const health = createQuery(() => ({
    queryKey: ["healthz"],
    queryFn: () => api<HealthResponse>("/healthz"),
    refetchInterval: 5_000,
  }));

  return (
    <main class="min-h-screen p-8 max-w-4xl mx-auto">
      <h1 class="text-3xl font-bold mb-6">
        AlecaFrame{" "}
        <span class="text-slate-400 text-base font-normal">
          backend v{info.data?.version ?? "…"}
        </span>
      </h1>

      <section class="grid grid-cols-2 gap-4 mb-8">
        <div class="rounded-2xl bg-slate-900 p-4 border border-slate-800">
          <div class="text-slate-400 text-sm">Health</div>
          <div
            class="text-xl font-semibold"
            classList={{
              "text-emerald-400": health.data?.ok === true,
              "text-rose-400": health.data?.ok === false,
              "text-slate-400": !health.data,
            }}
          >
            {health.isLoading ? "checking…" : health.data?.ok ? "online" : "offline"}
          </div>
        </div>
        <div class="rounded-2xl bg-slate-900 p-4 border border-slate-800">
          <div class="text-slate-400 text-sm">WFM user</div>
          <div class="text-xl font-mono">{health.data?.wfm_username ?? "—"}</div>
        </div>
      </section>

      <section>
        <h2 class="text-xl font-semibold mb-3">Endpoints</h2>
        <ul class="space-y-1 font-mono text-sm text-slate-300">
          {(info.data?.endpoints ?? []).map((e) => (
            <li>
              <code class="bg-slate-900 rounded px-2 py-0.5">{e}</code>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
```

- [ ] **Step 9: Frontend `.gitignore`**

Create `frontend/.gitignore`:

```
node_modules
dist
.vite
*.local
```

- [ ] **Step 10: Install deps and run dev server**

```powershell
cd frontend
npm install
npm run dev
```

Expected: Vite starts on `http://127.0.0.1:5173`. Open it in a browser — you should see the dark-themed dashboard with "Endpoints" list (assuming the backend is still running from Task 10; otherwise `/api/` requests will 502 — that's fine, the UI shouldn't crash).

Stop the dev server with Ctrl+C. Return to project root.

```powershell
cd ..
```

- [ ] **Step 11: Update root `.gitignore`**

In the project-root `.gitignore`, add a new section at the end:

```
# Frontend
frontend/node_modules
frontend/dist
frontend/.vite

# Env files
.env
```

- [ ] **Step 12: Commit**

```powershell
git add frontend .gitignore
git commit -m "feat(frontend): scaffold SolidJS app (Vite + Tailwind 4 + TanStack Query)"
```

---

## Task 12: Frontend Dockerfile + nginx proxy

**Files:**
- Create: `docker/frontend/Dockerfile`
- Create: `docker/frontend/nginx.conf`

- [ ] **Step 1: Create nginx config**

Create `docker/frontend/nginx.conf`:

```nginx
worker_processes 1;
events { worker_connections 1024; }

http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  sendfile on;
  keepalive_timeout 65;
  gzip on;
  gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

  upstream backend     { server backend:8765; }
  upstream centrifugo  { server centrifugo:8000; }

  server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # API: /api/* -> backend root
    location /api/ {
      proxy_pass http://backend/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_http_version 1.1;
      proxy_read_timeout 60s;
    }

    # Centrifugo WebSocket
    location /connection/ {
      proxy_pass http://centrifugo/connection/;
      proxy_http_version 1.1;
      proxy_set_header Upgrade $http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_set_header Host $host;
      proxy_read_timeout 1h;
    }

    # SPA fallback
    location / {
      try_files $uri $uri/ /index.html;
    }
  }
}
```

- [ ] **Step 2: Create the Dockerfile**

Create `docker/frontend/Dockerfile`:

```dockerfile
# syntax=docker/dockerfile:1.7
# Build stage: install + tsc + vite build
FROM node:22-alpine AS builder
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# Runtime stage: nginx
FROM nginx:1.27-alpine AS runtime
COPY docker/frontend/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
```

- [ ] **Step 3: Build the image and smoke-test**

From project root:

```powershell
docker build -f docker/frontend/Dockerfile -t alecaframe-frontend:dev .
docker run --rm -d --name fe-test -p 13000:80 alecaframe-frontend:dev
Start-Sleep -Seconds 3
Invoke-RestMethod http://127.0.0.1:13000/ | Select-Object -First 200
docker rm -f fe-test
```

Expected: HTML response that contains `<title>AlecaFrame</title>`.

- [ ] **Step 4: Commit**

```powershell
git add docker/frontend
git commit -m "build: add frontend Dockerfile (node build -> nginx) + proxy config"
```

---

## Task 13: Add frontend to compose

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add the service**

In `docker-compose.yml`, append before the top-level `volumes:` key:

```yaml
  frontend:
    build:
      context: .
      dockerfile: docker/frontend/Dockerfile
    container_name: aleca-frontend
    restart: unless-stopped
    ports: ["127.0.0.1:3000:80"]
    depends_on:
      backend: { condition: service_started }
      centrifugo: { condition: service_started }
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1/"]
      interval: 10s
      timeout: 3s
      retries: 5
```

- [ ] **Step 2: Build and run the full stack**

```powershell
docker compose build frontend
docker compose up -d
Start-Sleep -Seconds 15
docker compose ps
```

Expected: all six services (`redis`, `rabbitmq`, `centrifugo`, `backend`, `poller`, `frontend`) show `running`, most `healthy`.

- [ ] **Step 3: Open in browser**

```powershell
Start-Process http://127.0.0.1:3000
```

Expected: same UI from Task 11, served by nginx; `/api/` calls resolve through the proxy (backend may show empty inventory because no data is decrypted yet — that's expected).

- [ ] **Step 4: Commit**

```powershell
git add docker-compose.yml
git commit -m "build: add frontend service to compose; full stack starts via `docker compose up -d`"
```

---

## Task 14: `start-stack.ps1` launcher

**Files:**
- Create: `scripts/start-stack.ps1`

- [ ] **Step 1: Write the script**

Create `scripts/start-stack.ps1`:

```powershell
<#
.SYNOPSIS
  One-button stack starter: ensures decrypt-agent is running on the host,
  then brings up docker-compose, then waits for backend /healthz.

.NOTES
  Run from the project root.
#>

[CmdletBinding()]
param(
    [switch]$NoAgent,     # skip starting the host agent (already running externally)
    [switch]$Detached,    # leave the script after up
    [int]$AgentPort = 8788,
    [int]$ApiPort   = 8765,
    [int]$WebPort   = 3000
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Item -Path $PSScriptRoot).Parent.FullName
Set-Location $projectRoot

Write-Host "== AlecaFrame stack starter ==" -ForegroundColor Cyan

# --- 1. decrypt-agent ----------------------------------------------------
if (-not $NoAgent) {
    $agentUp = $false
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$AgentPort/healthz" -TimeoutSec 2 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $agentUp = $true }
    } catch { }

    if ($agentUp) {
        Write-Host "decrypt-agent already running on :$AgentPort" -ForegroundColor Green
    } else {
        Write-Host "starting decrypt-agent in a new PowerShell window..." -ForegroundColor Yellow
        Start-Process -FilePath "pwsh" -ArgumentList @(
            "-NoExit", "-NoProfile", "-Command",
            "Set-Location '$projectRoot'; uv run alecaframe-decrypt-agent"
        )
        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline) {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$AgentPort/healthz" -TimeoutSec 1 -UseBasicParsing
                if ($r.StatusCode -eq 200) { $agentUp = $true; break }
            } catch { Start-Sleep -Milliseconds 500 }
        }
        if (-not $agentUp) { throw "decrypt-agent did not become healthy in 30s" }
        Write-Host "decrypt-agent up." -ForegroundColor Green
    }
}

# --- 2. docker compose ---------------------------------------------------
if (-not (Test-Path ".env")) {
    Write-Host "no .env found; copying .env.example -> .env (review before reuse!)" -ForegroundColor Yellow
    Copy-Item .env.example .env
}

Write-Host "docker compose up -d ..." -ForegroundColor Cyan
docker compose up -d

# --- 3. wait for backend -------------------------------------------------
$deadline = (Get-Date).AddSeconds(60)
$apiUp = $false
while ((Get-Date) -lt $deadline) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/healthz" -TimeoutSec 1 -UseBasicParsing
        if ($r.StatusCode -eq 200) { $apiUp = $true; break }
    } catch { Start-Sleep -Milliseconds 500 }
}

if ($apiUp) {
    Write-Host "backend healthy on :$ApiPort" -ForegroundColor Green
} else {
    Write-Warning "backend did not become healthy in 60s; check 'docker compose logs backend'"
}

Write-Host ""
Write-Host "open: http://127.0.0.1:$WebPort" -ForegroundColor Cyan
Write-Host "api:  http://127.0.0.1:$ApiPort/docs" -ForegroundColor Cyan
Write-Host "rmq:  http://127.0.0.1:15672  (aleca / aleca-local)" -ForegroundColor DarkGray

if (-not $Detached) {
    Write-Host ""
    Write-Host "tailing backend + poller logs (Ctrl+C to detach; stack keeps running)" -ForegroundColor DarkGray
    docker compose logs -f backend poller
}
```

- [ ] **Step 2: Execute the script and verify the full path works**

First fully stop the running stack and the agent (if any) so we are testing cold-start.

```powershell
docker compose down
# also: close the decrypt-agent window from Task 4, if open
```

Now run the launcher:

```powershell
$env:AGENT_DUMP_SCRIPT = $null   # let agent use the real script (or set "" if you want stub mode)
./scripts/start-stack.ps1 -Detached
```

Expected:
- A new PowerShell window opens and runs `alecaframe-decrypt-agent` (tray icon appears)
- Compose brings up six services
- Backend reports healthy
- Three URLs printed at the end

- [ ] **Step 3: Tear down**

```powershell
docker compose down
# close the agent window with the tray icon's "Quit" entry
```

- [ ] **Step 4: Commit**

```powershell
git add scripts/start-stack.ps1
git commit -m "feat: add start-stack.ps1 one-button launcher"
```

---

## Task 15: README rewrite

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace README**

Open `README.md` and replace the **Setup**, **Запуск**, **Конфиг (env vars)**, and **Структура** sections with the block below. Keep the rest of the file (intro, Endpoints, Безопасность, etc.) as-is.

```markdown
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
└────────────────┘    │ centrifugo (:8000)                   │
                      └──────────────────────────────────────┘
```

## Установка

```powershell
git clone <repo> ; cd "aleca frame inventory"
uv sync                              # Python deps
Push-Location frontend ; npm install ; Pop-Location   # frontend deps
Copy-Item .env.example .env
```

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
| `ALECA_DATA_DIR` | `/data` | mounted volume с расшифрованным JSON |
| `ALECA_TTL_SECONDS` | `60` | TTL backend-кеша |
| `ALECA_WFM_PLATFORM` | `pc` | `pc` / `xbox` / `ps4` / `switch` |
| `ALECA_LOG_LEVEL` | `INFO` | уровень логов |
| `AGENT_PORT` | `8788` | порт decrypt-agent (host) |
| `AGENT_OUT_DIR` | `./data` (рядом с проектом) | куда писать JSON |

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
│   ├── rabbitmq/definitions.json
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

## Эндпоинты

(см. полный список на `/docs` — Swagger UI. Существующие 17 эндпоинтов
инвентаря работают как раньше. WFM-эндпоинты появляются в фазе B.1.)
```

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs: rewrite README for B.0 dockerised architecture"
```

---

## Task 16: End-to-end smoke test + final polish

**Files:**
- Create: `tests/test_smoke_e2e.py` (optional sanity check after a manual run)

- [ ] **Step 1: Add a marker for slow integration tests**

In `pyproject.toml` under the `[tool.pytest.ini_options]` block extend `addopts`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra -q -m 'not e2e'"
markers = ["e2e: requires a running docker-compose stack"]
```

- [ ] **Step 2: Write the smoke test (skipped by default)**

Create `tests/test_smoke_e2e.py`:

```python
"""End-to-end smoke test against a live stack.

Run manually after `./scripts/start-stack.ps1`:
    uv run pytest tests/test_smoke_e2e.py -m e2e -v
"""
from __future__ import annotations

import pytest
import httpx


@pytest.mark.e2e
def test_backend_healthz() -> None:
    r = httpx.get("http://127.0.0.1:8765/healthz", timeout=3)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


@pytest.mark.e2e
def test_frontend_serves_html() -> None:
    r = httpx.get("http://127.0.0.1:3000/", timeout=3)
    assert r.status_code == 200
    assert "<title>AlecaFrame</title>" in r.text


@pytest.mark.e2e
def test_frontend_proxies_api() -> None:
    """Frontend nginx rewrites /api/ -> backend root."""
    r = httpx.get("http://127.0.0.1:3000/api/healthz", timeout=3)
    assert r.status_code == 200


@pytest.mark.e2e
def test_centrifugo_health() -> None:
    r = httpx.get("http://127.0.0.1:8000/health", timeout=3)
    assert r.status_code == 200


@pytest.mark.e2e
def test_rabbitmq_management() -> None:
    r = httpx.get(
        "http://127.0.0.1:15672/api/overview",
        auth=("aleca", "aleca-local"), timeout=3,
    )
    assert r.status_code == 200
    assert "rabbitmq_version" in r.json()
```

- [ ] **Step 3: Run the full stack and run the smoke tests**

```powershell
./scripts/start-stack.ps1 -Detached
uv run pytest tests/test_smoke_e2e.py -m e2e -v
docker compose down
```

Expected: all five smoke tests pass.

- [ ] **Step 4: Verify the regular test suite still ignores e2e**

```powershell
uv run pytest -v
```

Expected: existing unit tests (`test_config`, `test_decrypt_agent`, `test_bridge`) run; e2e tests are skipped.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml tests/test_smoke_e2e.py
git commit -m "test: add e2e smoke test (gated behind -m e2e)"
```

---

## Definition of Done — Phase B.0

- `./scripts/start-stack.ps1` brings up six services + the tray agent in under 60s
- `http://127.0.0.1:3000` serves the SolidJS UI; "Health" card shows `online`
- `http://127.0.0.1:3000/api/healthz` and `http://127.0.0.1:8765/healthz` both return 200
- `uv run pytest` passes (unit tests)
- `uv run pytest -m e2e` passes against a running stack
- `docker compose down` cleanly stops everything; no leftover named containers
- `git log --oneline` shows ~16 commits, all under the conventional-commits style

---

## Self-Review Notes

**Spec coverage:** every B.0 deliverable from section 5 of the spec has a task:
- ✅ docker-compose with redis/rabbit/centrifugo/backend/poller/frontend (Tasks 9, 10, 13)
- ✅ decrypt-agent runs via tray app (Tasks 3, 4)
- ✅ existing 17 endpoints accessible at `/api/*` and `:8765/*` (Tasks 5, 10, 13)
- ✅ frontend on `:3000` shows Hello World w/ endpoint list (Tasks 11, 13)
- ✅ `start-stack.ps1` (Task 14)
- ✅ No new WFM endpoints in B.0 (intentional)

**Type / name consistency:**
- `AlecaBridge(agent_url=..., data_dir=...)` used identically in `bridge.py`, `main.py`, and `tests/test_bridge.py`
- `Settings.agent_url` used by both `main.py` and the env keys in `docker-compose.yml`
- decrypt-agent paths `/healthz`, `/wfm-token`, `/refresh`, `/toast` consistent across `decrypt_agent/main.py`, `bridge.py`, `Settings`, and the smoke test
- `alecaframe-poller` console script name matches `pyproject.toml` and `CMD` in `docker/poller/Dockerfile` (via the default `CMD ["alecaframe-poller"]`)

**Scope:** no scope creep into B.1 WFM client or signals — the poller is a stub.

**Open assumption to verify during execution:** the `ghcr.io/astral-sh/uv:0.11.14` tag exists. If `docker pull ghcr.io/astral-sh/uv:0.11.14` fails when building, swap to `:latest` (the engineer should pin a known-good tag after this lands).

---

**End of Phase B.0 plan.** Phase B.1 plan to be written after B.0 is merged and live.
