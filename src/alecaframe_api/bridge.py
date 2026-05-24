"""Bridge to AlecaFrame's .NET DLL via pwsh subprocess.

Calls scripts/dump_inventory.ps1 to decrypt the AlecaFrame .dat blobs, then
caches the parsed JSON in memory with a TTL.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("alecaframe.bridge")


class BridgeError(RuntimeError):
    """Raised when the pwsh script fails or returns malformed output."""


@dataclass
class CacheEntry:
    data: dict[str, Any]
    loaded_at: float  # monotonic
    source: str  # 'fresh' | 'disk'


@dataclass
class AlecaBridge:
    """Loads decrypted JSON via the pwsh script; caches it in memory."""

    script: Path
    data_dir: Path
    ttl_seconds: int = 60
    pwsh: str = "pwsh"

    _lastdata: CacheEntry | None = field(default=None, init=False, repr=False)
    _deltas: CacheEntry | None = field(default=None, init=False, repr=False)
    _meta: dict[str, Any] | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    # ------------------------------------------------------------------ public

    async def lastdata(self, *, force: bool = False) -> dict[str, Any]:
        """Return parsed lastData.json (full inventory snapshot)."""
        await self._ensure(force=force)
        assert self._lastdata is not None
        return self._lastdata.data

    async def deltas(self, *, force: bool = False) -> dict[str, Any]:
        await self._ensure(force=force)
        assert self._deltas is not None
        return self._deltas.data

    async def refresh(self) -> dict[str, Any]:
        """Force a fresh decrypt run; return the script's JSON result.

        Even if pwsh fails, we still attempt _reload_from_disk so any files
        that DID get written (e.g. lastData succeeded but deltas didn't) end
        up in the in-memory cache.
        """
        async with self._lock:
            try:
                result = await self._invoke_pwsh()
            except BridgeError:
                self._reload_from_disk(force=True)
                raise
            self._reload_from_disk(force=True)
        return result

    @property
    def cache_status(self) -> dict[str, Any]:
        now = time.monotonic()
        def info(c: CacheEntry | None) -> dict[str, Any] | None:
            if c is None:
                return None
            return {
                "loaded_age_seconds": round(now - c.loaded_at, 2),
                "source": c.source,
                "size_top_level_keys": len(c.data) if isinstance(c.data, dict) else None,
            }
        return {
            "lastdata": info(self._lastdata),
            "deltas": info(self._deltas),
            "ttl_seconds": self.ttl_seconds,
            "data_dir": str(self.data_dir),
        }

    @property
    def meta(self) -> dict[str, Any] | None:
        return self._meta

    # ----------------------------------------------------------------- private

    async def _ensure(self, *, force: bool) -> None:
        async with self._lock:
            if force or self._is_stale():
                # On startup we prefer fresh; on subsequent stale reads we try to
                # re-run the pwsh script. If that fails but disk JSON exists, use it.
                try:
                    await self._invoke_pwsh()
                except BridgeError:
                    if not (self.data_dir / "lastData.json").exists():
                        raise
                    log.warning("pwsh refresh failed; falling back to on-disk JSON")
                self._reload_from_disk(force=True)

    def _is_stale(self) -> bool:
        if self._lastdata is None:
            return True
        return (time.monotonic() - self._lastdata.loaded_at) > self.ttl_seconds

    def _reload_from_disk(self, *, force: bool) -> None:
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

    async def _invoke_pwsh(self) -> dict[str, Any]:
        if not self.script.exists():
            raise BridgeError(f"dump script missing: {self.script}")
        cmd = [
            self.pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", str(self.script),
            "-OutDir", str(self.data_dir),
        ]
        log.info("invoking %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        stdout = stdout_b.decode("utf-8", errors="replace").strip()
        stderr = stderr_b.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            raise BridgeError(
                f"pwsh exit {proc.returncode}: {stdout or stderr or '<no output>'}"
            )
        # script writes a single JSON line to stdout
        try:
            return json.loads(stdout.splitlines()[-1])
        except Exception as e:
            raise BridgeError(f"could not parse pwsh output: {e!r}; stdout={stdout!r}")
