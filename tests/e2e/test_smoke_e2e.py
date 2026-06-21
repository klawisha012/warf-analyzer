"""End-to-end smoke test against a live stack.

Run manually after `./scripts/start-stack.ps1`:
    uv run pytest tests/test_smoke_e2e.py -m e2e -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import httpx

from tests import REPO_ROOT


def _centrifugo_api_key() -> str:
    """Read CENTRIFUGO_API_KEY from .env (dev default if not found)."""
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("CENTRIFUGO_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("CENTRIFUGO_API_KEY", "local-dev-api-key-change-me")


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
    """Centrifugo v6 /metrics returns 404 in this config.
    Use POST /api/info with the API key instead — 200 means node is up."""
    api_key = _centrifugo_api_key()
    r = httpx.post(
        "http://127.0.0.1:8002/api/info",
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        content=b"{}",
        timeout=3,
    )
    assert r.status_code == 200
    assert "result" in r.json()


@pytest.mark.e2e
def test_rabbitmq_management() -> None:
    r = httpx.get(
        "http://127.0.0.1:15672/api/overview",
        auth=("aleca", "aleca-local"), timeout=3,
    )
    assert r.status_code == 200
    assert "rabbitmq_version" in r.json()


@pytest.mark.e2e
def test_wfm_items_listing() -> None:
    r = httpx.get("http://127.0.0.1:8765/wfm/items", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 1000   # WFM catalogue has thousands of slugs


@pytest.mark.e2e
def test_wfm_orders_for_known_slug() -> None:
    r = httpx.get("http://127.0.0.1:8765/wfm/orders/kronen_prime_blade", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "kronen_prime_blade"
    assert "sell" in body and "buy" in body
    assert isinstance(body["sell"]["count_orders"], int)


@pytest.mark.e2e
def test_wfm_orders_unknown_slug_returns_404() -> None:
    r = httpx.get("http://127.0.0.1:8765/wfm/orders/this_does_not_exist", timeout=10)
    assert r.status_code == 404


@pytest.mark.e2e
def test_me_sets_profit() -> None:
    r = httpx.get("http://127.0.0.1:8765/me/sets-profit", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    # Tolerate empty list — depends on user's actual inventory.


@pytest.mark.e2e
def test_proxied_wfm_items_via_frontend() -> None:
    r = httpx.get("http://127.0.0.1:3000/api/wfm/items", timeout=10)
    assert r.status_code == 200
    assert r.json()["total"] > 1000


@pytest.mark.e2e
def test_me_mods_priced() -> None:
    r = httpx.get("http://127.0.0.1:8765/me/mods-priced", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body


@pytest.mark.e2e
def test_me_arcanes_priced() -> None:
    r = httpx.get("http://127.0.0.1:8765/me/arcanes-priced", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
