"""CentrifugoPublisher tests — HTTP publish + JWT token minting."""
from __future__ import annotations

import time

import jwt
import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.infra.push import CentrifugoPublisher


@pytest.fixture
def publisher() -> CentrifugoPublisher:
    return CentrifugoPublisher(
        api_url="http://centri.test/api",
        api_key="test-api-key",
        token_hmac_secret="test-hmac",
    )


def test_mint_token_signs_user_with_exp(publisher: CentrifugoPublisher) -> None:
    token = publisher.mint_user_token("alice", ttl_seconds=60)
    payload = jwt.decode(token, "test-hmac", algorithms=["HS256"])
    assert payload["sub"] == "alice"
    assert payload["exp"] - payload["iat"] == 60


@pytest.mark.asyncio
async def test_publish_posts_with_api_key(publisher: CentrifugoPublisher, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="http://centri.test/api", method="POST", json={"result": {}})
    await publisher.publish("wfm.orders.kronen_prime_blade", {"slug": "kronen_prime_blade", "min": 35})
    req = httpx_mock.get_request()
    assert req.headers["X-API-Key"] == "test-api-key"
    import json as _j
    body = _j.loads(req.content)
    assert body["method"] == "publish"
    assert body["params"]["channel"] == "wfm.orders.kronen_prime_blade"
    assert body["params"]["data"]["slug"] == "kronen_prime_blade"


@pytest.mark.asyncio
async def test_publish_swallows_5xx(publisher: CentrifugoPublisher, httpx_mock: HTTPXMock) -> None:
    """Centrifugo down should NOT bring down the backend — log and move on."""
    httpx_mock.add_response(url="http://centri.test/api", method="POST", status_code=500, text="boom")
    # Should not raise.
    await publisher.publish("any.channel", {"k": "v"})
