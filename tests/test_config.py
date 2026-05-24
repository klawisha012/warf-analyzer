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


def test_wfm_base_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALECA_WFM_BASE_URL", raising=False)
    s = reload_settings()
    assert s.wfm_base_url == "https://api.warframe.market/v1"


def test_wfm_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALECA_WFM_BASE_URL", "https://mock.wfm.test/v1")
    s = reload_settings()
    assert s.wfm_base_url == "https://mock.wfm.test/v1"
