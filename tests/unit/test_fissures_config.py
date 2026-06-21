from __future__ import annotations


def test_tg_api_key_reads_unprefixed_env(monkeypatch) -> None:
    monkeypatch.setenv("TG_API_KEY", "12345:secret")
    from alecaframe_api.config import Settings
    s = Settings()
    assert s.tg_api_key == "12345:secret"


def test_fissure_defaults() -> None:
    from alecaframe_api.config import Settings
    s = Settings()
    assert s.fissure_poll_interval_seconds == 60
    assert s.fissure_source_base_url == "https://api.warframestat.us"
