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
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("decrypt_agent")
_background_tasks: set[asyncio.Task[None]] = set()

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
    stdout = stdout_b.decode("utf-8-sig", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(f"pwsh exit {proc.returncode}: {stdout or stderr}")
    lines = stdout.splitlines()
    if not lines:
        raise RuntimeError("pwsh exited 0 but produced no stdout")
    try:
        return json.loads(lines[-1])
    except Exception as e:
        raise RuntimeError(f"could not parse pwsh output: {e!r}; raw={stdout!r}") from e


async def _show_toast(req: ToastRequest) -> None:
    """Schedule a Windows toast. Lazy import keeps tests/cross-platform clean."""
    try:
        from win10toast_click import ToastNotifier  # type: ignore[import-untyped]
    except ImportError as e:
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
        except Exception as e:
            log.exception("refresh failed")
            raise HTTPException(500, f"dump script failed: {e}") from e
        return RefreshResult(**result)

    @app.post("/toast", status_code=202)
    async def toast(req: ToastRequest) -> dict[str, str]:
        t = asyncio.create_task(_show_toast(req))
        _background_tasks.add(t)
        t.add_done_callback(_background_tasks.discard)
        return {"status": "scheduled"}

    return app


# default app for `uvicorn decrypt_agent.main:app`
app = build_app()
