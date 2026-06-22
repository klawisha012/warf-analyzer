"""RabbitMQ async bus: thin facade over aio-pika.

Provides:
- `publish(exchange, routing_key, payload)` — JSON-serialise and publish
- `subscribe(queue, handler)` — start a background consumer that
  calls handler(parsed_json) for each delivered message
- `aclose()` — graceful shutdown

In tests, set `bus._fake = _InMemoryBus()` and `bus._connected = True` to
short-circuit the real connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

import aio_pika

log = logging.getLogger("alecaframe.infra.broker")

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class _InMemoryBus:
    """Test-only stand-in for RabbitMQ topic routing.

    Bindings come from `docker/rabbitmq/definitions.json` — for tests we
    hardcode the two we use: `wfm` exchange routes `live.orders.*` →
    `wfm.live.orders` queue and `signals` exchange routes `new.*` →
    `signals.new` queue.
    """

    def __init__(self) -> None:
        self._inbox: dict[str, list[str]] = {"wfm.live.orders": [], "signals.new": []}
        self._handlers: dict[str, list[Handler]] = {}
        self._bindings = [
            ("wfm", "live.orders.*", "wfm.live.orders"),
            ("signals", "new.*", "signals.new"),
        ]

    async def publish(self, exchange: str, rk: str, payload: bytes) -> None:
        for ex, pattern, queue in self._bindings:
            if ex == exchange and fnmatch(rk, pattern):
                self._inbox[queue].append(payload.decode("utf-8"))
                for h in self._handlers.get(queue, []):
                    asyncio.create_task(h(json.loads(payload)))

    async def subscribe(self, queue: str, handler: Handler) -> None:
        self._handlers.setdefault(queue, []).append(handler)


@dataclass
class RabbitMQBus:
    url: str
    _connection: Any = field(default=None, init=False, repr=False)
    _channel: Any = field(default=None, init=False, repr=False)
    _connected: bool = field(default=False, init=False, repr=False)
    _fake: _InMemoryBus | None = field(default=None, init=False, repr=False)
    _consumers: list[asyncio.Task] = field(default_factory=list, init=False, repr=False)

    async def connect(self) -> None:
        if self._connected:
            return
        self._connection = await aio_pika.connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=20)
        self._connected = True

    async def publish(
        self, exchange: str, routing_key: str, payload: dict[str, Any]
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if self._fake is not None:
            await self._fake.publish(exchange, routing_key, body)
            return
        await self.connect()
        assert self._channel is not None
        ex = await self._channel.get_exchange(exchange, ensure=False)
        await ex.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=routing_key,
        )

    async def subscribe(self, queue_name: str, handler: Handler) -> None:
        if self._fake is not None:
            await self._fake.subscribe(queue_name, handler)
            return
        await self.connect()
        assert self._channel is not None
        queue = await self._channel.get_queue(queue_name, ensure=False)

        async def _loop() -> None:
            async with queue.iterator() as it:
                async for msg in it:
                    async with msg.process(ignore_processed=False):
                        try:
                            payload = json.loads(msg.body)
                        except Exception as e:
                            log.warning("undecodable message on %s: %s", queue_name, e)
                            continue
                        try:
                            await handler(payload)
                        except Exception as e:
                            log.exception("handler error on %s: %s", queue_name, e)

        self._consumers.append(asyncio.create_task(_loop()))

    async def aclose(self) -> None:
        for t in self._consumers:
            t.cancel()
        self._consumers.clear()
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._connected = False
