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
from typing import Any, Literal

import httpx

log = logging.getLogger("alecaframe.bridge")


class BridgeError(RuntimeError):
    """Raised when /refresh fails or files cannot be loaded."""


@dataclass
class CacheEntry:
    data: dict[str, Any]
    loaded_at: float  # monotonic seconds
    source: Literal["disk"]


@dataclass
class AlecaBridge:
    """Talks to decrypt-agent for refresh and reads JSON from disk."""

    agent_url: str
    data_dir: Path
    ttl_seconds: int = 60
    refresh_timeout: float = 10.0   # agent's pwsh cold-load is ~5s; 10s gives headroom

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
        """Reload cached entries from on-disk JSON.

        Public so tests can pre-warm the cache and the lifespan can fall back
        when the agent is offline. NOT thread-safe by itself: callers in async
        contexts must hold `self._lock` (both `_ensure_loaded` and `refresh`
        already do this). Synchronous test callers don't need to.

        The `force` parameter is currently unused — kept to make the call sites
        in `_ensure_loaded(force=True)` and `refresh()` (after a successful POST)
        explicit and to allow future selective reload (e.g. only one file).
        """
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
