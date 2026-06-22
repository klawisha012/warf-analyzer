"""RabbitMQBus tests — producer publishes, consumer dispatches."""

from __future__ import annotations

import asyncio
import json

import pytest

from alecaframe_api.infra.broker import RabbitMQBus


@pytest.mark.asyncio
async def test_publish_then_consume_roundtrip() -> None:
    """Use the in-memory fake transport to verify publish + dispatch flow."""
    bus = RabbitMQBus(url="amqp://fake")
    received: list[dict] = []

    async def handler(msg: dict) -> None:
        received.append(msg)

    from alecaframe_api.infra.broker import _InMemoryBus

    fake = _InMemoryBus()
    bus._fake = fake
    bus._connected = True

    await bus.subscribe("wfm.live.orders", handler)
    await bus.publish(
        "wfm",
        "live.orders.kronen_prime_blade",
        {"slug": "kronen_prime_blade", "min_price": 35},
    )
    await asyncio.sleep(0.05)
    assert received == [{"slug": "kronen_prime_blade", "min_price": 35}]


@pytest.mark.asyncio
async def test_publish_serialises_json() -> None:
    bus = RabbitMQBus(url="amqp://fake")
    from alecaframe_api.infra.broker import _InMemoryBus

    fake = _InMemoryBus()
    bus._fake = fake
    bus._connected = True
    await bus.publish("wfm", "live.orders.x", {"a": 1, "b": [2, 3]})
    raw = fake._inbox["wfm.live.orders"][-1]
    assert json.loads(raw) == {"a": 1, "b": [2, 3]}
