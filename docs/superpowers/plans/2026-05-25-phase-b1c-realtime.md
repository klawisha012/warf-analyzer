# Phase B.1c: Real-time wiring (WS + RabbitMQ + Centrifugo) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Wire WFM's WebSocket order-book stream → RabbitMQ → backend consumer → Redis cache update → Centrifugo channel → frontend live-update. After B.1c, opening a page subscribes to the slugs it shows, and any change on warframe.market reflects in the UI within ~1 second without a page refresh.

**Architecture:**

```
WFM /socket  →  poller (WFMSocketClient)  →  publish RabbitMQ "wfm.live.orders"
                                                          │ durable queue
                                                          ▼
                                          backend consumer task (in lifespan)
                                                          │
                                                          ├─ update Redis cached order book
                                                          └─ Centrifugo HTTP /publish "wfm.orders.{slug}"
                                                                                  │ Centrifugo WS
                                                                                  ▼
                                                                 frontend `centrifuge-js` subscriber
                                                                                  │
                                                                                  └─ invalidate TanStack query for visible slug
```

**Tech Stack:** Python 3.13 + aio-pika + redis.asyncio + httpx (Centrifugo HTTP publish) + PyJWT (HS256 for client tokens) + APScheduler (already a hidden dep — explicitly added in this phase). Frontend: `centrifuge` JS client (already installed in B.0).

---

## File Map

**Create:**
- `src/alecaframe_api/infra/push.py` — `CentrifugoPublisher` (HTTP publish + JWT mint)
- `src/alecaframe_api/infra/broker.py` — `RabbitMQ` producer/consumer (aio-pika)
- `src/alecaframe_api/wfm/socket.py` — `WFMSocketClient` (long-running WS, reconnect)
- `src/alecaframe_api/wfm/consumer.py` — backend consumer that drains `wfm.live.orders`
- `src/alecaframe_api/wfm/me_router.py` — minimal new endpoint for Centrifugo token issuance (split off router.py to keep it focused)
- `tests/test_infra_push.py`
- `tests/test_infra_broker.py`
- `tests/test_wfm_consumer.py`
- `frontend/src/api/centrifuge.ts`
- `frontend/src/hooks/useSlugChannel.ts`

**Modify:**
- `pyproject.toml` — add `aio-pika>=9.5`, `pyjwt>=2.9`, `apscheduler>=3.10`
- `src/alecaframe_api/config.py` — add `centrifugo_token_ttl_seconds: int = 3600`
- `src/alecaframe_api/wfm/poller.py` — replace stub with real APScheduler + WS task + broker producer
- `src/alecaframe_api/main.py` — start backend consumer in lifespan; include `me_router`
- `src/alecaframe_api/wfm/router.py` — no changes (but reserve room — token endpoint lives in me_router)
- `frontend/src/routes/Dashboard.tsx` — subscribe to a system channel for `system.refresh`
- `frontend/src/routes/PrimeParts.tsx` — subscribe to top-10 visible slugs
- `frontend/src/routes/Inventory.tsx` — subscribe to top-10 visible slugs
- `README.md` — document real-time channels

**Out of scope (B.2+):** signal engine writing to RabbitMQ `signals.new` topic; alert toasts via decrypt-agent.

---

## Conventions

- **Commit format:** Conventional Commits.
- **Branch:** `feature/b1c-realtime` (already created from master @ 2b1425c).
- **TDD where applicable:** infra modules (push, broker) and wfm/consumer get unit tests. WFM WS client + poller orchestration are exercised by e2e.
- **Working dir:** `B:\Sync\Programming\projects\aleca frame inventory`.

---

## Task 1: Dependencies

**Files:** `pyproject.toml`

- [ ] **Step 1: Add deps**

```powershell
uv add 'aio-pika>=9.5' 'pyjwt>=2.9' 'apscheduler>=3.10' 'websockets>=14.1'
```

- [ ] **Step 2: Verify imports**

```powershell
uv run python -c "import aio_pika, jwt, apscheduler, websockets; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```powershell
git add pyproject.toml uv.lock
git commit -m "build: add aio-pika, pyjwt, apscheduler, websockets for B.1c real-time"
```

---

## Task 2: `infra/push.py` — Centrifugo publisher + JWT minting

**Files:** Create `src/alecaframe_api/infra/push.py`, `tests/test_infra_push.py`

- [ ] **Step 1: Failing tests**

Create `tests/test_infra_push.py`:

```python
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
```

Run, verify fail.

- [ ] **Step 2: Implement**

Create `src/alecaframe_api/infra/push.py`:

```python
"""Centrifugo HTTP publisher + JWT minting for client connection tokens.

Centrifugo v6 server API:
- POST /api  with `{"method": "publish", "params": {"channel": "...", "data": {...}}}`
  authenticated by `X-API-Key` header.
- Clients connect with a JWT signed by `token_hmac_secret`, `sub` = user id,
  `exp` = expiry.

Publish failures are logged at WARNING and swallowed — the realtime pipeline
must never bring down the request path.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

log = logging.getLogger("alecaframe.infra.push")


@dataclass
class CentrifugoPublisher:
    api_url: str          # e.g. http://centrifugo:8000/api
    api_key: str
    token_hmac_secret: str
    timeout: float = 3.0

    def mint_user_token(self, user_id: str, *, ttl_seconds: int = 3600) -> str:
        now = int(time.time())
        payload = {"sub": str(user_id), "iat": now, "exp": now + ttl_seconds}
        return jwt.encode(payload, self.token_hmac_secret, algorithm="HS256")

    async def publish(self, channel: str, data: dict[str, Any]) -> None:
        body = {"method": "publish", "params": {"channel": channel, "data": data}}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.post(
                    self.api_url,
                    json=body,
                    headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                )
                if resp.status_code >= 400:
                    log.warning("centrifugo publish %s status %d: %s",
                                channel, resp.status_code, resp.text[:200])
        except Exception as e:
            log.warning("centrifugo publish %s failed: %s", channel, e)
```

Run tests — 3 pass.

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/infra/push.py tests/test_infra_push.py
git commit -m "feat(infra): add CentrifugoPublisher (HTTP publish + JWT user-token minting)"
```

---

## Task 3: `infra/broker.py` — RabbitMQ producer/consumer

**Files:** Create `src/alecaframe_api/infra/broker.py`, `tests/test_infra_broker.py`

- [ ] **Step 1: Failing tests** (use aiormq mock or in-memory aio-pika)

Create `tests/test_infra_broker.py`:

```python
"""RabbitMQBus tests — producer publishes, consumer dispatches."""
from __future__ import annotations

import asyncio
import json

import pytest

from alecaframe_api.infra.broker import RabbitMQBus


@pytest.mark.asyncio
async def test_publish_then_consume_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use the in-memory fake transport to verify publish + dispatch flow."""
    bus = RabbitMQBus(url="amqp://fake")
    # The real implementation must accept a `transport=` injection that we
    # can swap for a fake. If your aio-pika install doesn't expose one,
    # mock connect_robust directly via monkeypatch.

    received: list[dict] = []

    async def handler(msg: dict) -> None:
        received.append(msg)

    # Connect both producer and consumer to the same fake; in tests we use
    # a simple list-backed bus instead of real aio-pika.
    from alecaframe_api.infra.broker import _InMemoryBus
    fake = _InMemoryBus()
    bus._fake = fake
    bus._connected = True

    await bus.subscribe("wfm.live.orders", handler)
    await bus.publish("wfm", "live.orders.kronen_prime_blade",
                      {"slug": "kronen_prime_blade", "min_price": 35})
    await asyncio.sleep(0.05)   # let consumer drain
    assert received == [{"slug": "kronen_prime_blade", "min_price": 35}]


@pytest.mark.asyncio
async def test_publish_serialises_json() -> None:
    bus = RabbitMQBus(url="amqp://fake")
    from alecaframe_api.infra.broker import _InMemoryBus
    fake = _InMemoryBus()
    bus._fake = fake
    bus._connected = True
    await bus.publish("wfm", "live.orders.x", {"a": 1, "b": [2, 3]})
    raw = fake._inbox["wfm.live.orders"][-1]   # routed by binding to its queue
    assert json.loads(raw) == {"a": 1, "b": [2, 3]}
```

This task is the most likely to need iteration — aio-pika's mocking story is awkward. The fix-it-up loop is:
1. First implement `RabbitMQBus` with `connect_robust` + `publish` + `subscribe`.
2. Add a `_fake: _InMemoryBus | None = None` field that, when set, replaces the real path.
3. `_InMemoryBus` is a tiny dict-of-lists that mimics topic-routing using the binding patterns from `definitions.json`.

- [ ] **Step 2: Implement** (skeleton)

Create `src/alecaframe_api/infra/broker.py`:

```python
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
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any, Awaitable, Callable

import aio_pika

log = logging.getLogger("alecaframe.infra.broker")

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class _InMemoryBus:
    """Test-only stand-in for RabbitMQ topic routing.

    Bindings come from `docker/rabbitmq/definitions.json` — for tests we
    hardcode the two we use: `wfm` exchange routes `live.orders.*` →
    `wfm.live.orders` queue and `signals` → `signals.new`.
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
    _connection: aio_pika.RobustConnection | None = field(default=None, init=False, repr=False)
    _channel: aio_pika.abc.AbstractChannel | None = field(default=None, init=False, repr=False)
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

    async def publish(self, exchange: str, routing_key: str, payload: dict[str, Any]) -> None:
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
```

- [ ] **Step 3: Verify tests pass**

```powershell
uv run pytest tests/test_infra_broker.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```powershell
git add src/alecaframe_api/infra/broker.py tests/test_infra_broker.py
git commit -m "feat(infra): add RabbitMQBus (aio-pika producer/consumer + in-memory test bus)"
```

---

## Task 4: `wfm/socket.py` — WFM WebSocket client

**Files:** Create `src/alecaframe_api/wfm/socket.py`

No unit tests at this layer — exercise via e2e + manual smoke. WFM's WS protocol is documented at https://warframe.market/api_docs (or undocumented; we use the convention: `wss://warframe.market/socket?platform=pc` with `Cookie: JWT=<token>; platform=pc` header).

- [ ] **Step 1: Implement**

Create `src/alecaframe_api/wfm/socket.py`:

```python
"""Long-running WebSocket client for WFM live order updates.

Connects to `wss://warframe.market/socket?platform=pc`, sends a SUBSCRIBE
message per slug, and forwards every order-book event to a user-supplied
handler. Reconnects on disconnect with exponential backoff.

This file is consumed by the poller; backend never imports it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Awaitable, Callable

import websockets

log = logging.getLogger("alecaframe.wfm.socket")

Handler = Callable[[dict], Awaitable[None]]


class WFMSocketClient:
    """Subscribe to live order updates for a list of slugs."""

    def __init__(
        self,
        token_provider: Callable[[], Awaitable[str]],
        platform: str = "pc",
        base_ws: str = "wss://warframe.market/socket",
    ) -> None:
        self._token_provider = token_provider
        self._platform = platform
        self._base_ws = base_ws
        self._slugs: set[str] = set()
        self._stop = asyncio.Event()

    def set_subscription(self, slugs: set[str]) -> None:
        """Update the set of slugs to listen for. Picked up on next reconnect."""
        self._slugs = set(slugs)

    async def run(self, handler: Handler) -> None:
        """Long-running loop with exponential backoff."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                token = await self._token_provider()
                url = f"{self._base_ws}?platform={self._platform}"
                headers = {"Cookie": f"JWT={token}; platform={self._platform}"}
                async with websockets.connect(url, additional_headers=headers, ping_interval=20) as ws:
                    backoff = 1.0
                    # Subscribe to current slug set.
                    for slug in list(self._slugs):
                        await ws.send(json.dumps({
                            "type": "@WS/SUBSCRIBE/NEW_ORDERS", "payload": slug,
                        }))
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        # WFM sends @WS/SUBSCRIBE/NEW_ORDERS responses, plus order events.
                        if msg.get("type", "").endswith("/UPDATE") or msg.get("type", "").endswith("/CREATED"):
                            await handler(msg)
            except Exception as e:
                if self._stop.is_set():
                    return
                jitter = random.uniform(0, 0.5)
                wait = min(60.0, backoff) + jitter
                log.warning("WFM WS error (%s); reconnect in %.1fs", e, wait)
                await asyncio.sleep(wait)
                backoff = min(60.0, backoff * 2)

    def stop(self) -> None:
        self._stop.set()
```

Note: the exact WFM WS protocol message types may differ — the spec says `@WS/SUBSCRIBE/NEW_ORDERS` but reality may need adjustment. Keep this loose; tune at smoke-test time.

- [ ] **Step 2: Smoke import**

```powershell
uv run python -c "from alecaframe_api.wfm.socket import WFMSocketClient; print('ok')"
```

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/wfm/socket.py
git commit -m "feat(wfm): add WFMSocketClient (WS with reconnect + slug subscription)"
```

---

## Task 5: Poller rewrite — APScheduler + WS task + broker producer

**Files:** Replace `src/alecaframe_api/wfm/poller.py`

- [ ] **Step 1: Rewrite**

Replace the entire stub in `src/alecaframe_api/wfm/poller.py` with:

```python
"""Poller worker — long-running process.

Responsibilities (B.1c version):
- Connect to RabbitMQ.
- Bootstrap the slug catalogue from WFM /v1/items (sets the subscription set).
- Open a long-running WFM WebSocket and forward every order event to the
  `wfm.live.orders` topic on RabbitMQ.
- APScheduler: every 30 minutes refresh the slug catalogue + the subscription set.

The slug subscription set comes from:
1. Slugs derived from the user's inventory (read once via decrypt-agent's
   data folder mount — backend already exposes /me/prime-parts-priced, but we
   read JSON directly to avoid a circular HTTP loop).
2. A static watchlist file at `data/watchlist.txt` (one slug per line; optional).

Future: when /me/listings comes in over HTTP, intersect with active listings too.
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx

from alecaframe_api.config import get_settings
from alecaframe_api.infra.broker import RabbitMQBus
from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.client import WFMClient
from alecaframe_api.wfm.slugs import SlugResolver
from alecaframe_api.wfm.socket import WFMSocketClient
import redis.asyncio as redis_lib

log = logging.getLogger("alecaframe.poller")


def _read_inventory_slugs(data_dir: Path, resolver: SlugResolver) -> set[str]:
    """Best-effort: walk lastData.json, resolve unique-names to slugs."""
    path = data_dir / "lastData.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("can't read %s: %s", path, e)
        return set()
    slugs: set[str] = set()
    for key in ("MiscItems", "Recipes", "RawUpgrades"):
        for it in data.get(key) or []:
            slug = resolver.resolve_unique_name(it.get("ItemType") or "")
            if slug:
                slugs.add(slug)
    return slugs


def _read_watchlist(data_dir: Path) -> set[str]:
    path = data_dir / "watchlist.txt"
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


async def _refresh_subscription(
    *,
    wfm_client: WFMClient,
    resolver: SlugResolver,
    socket_client: WFMSocketClient,
    data_dir: Path,
) -> None:
    try:
        items = await wfm_client.get_items()
        resolver.load(items)
    except Exception as e:
        log.warning("WFM /items refresh failed: %s", e)
    slugs = _read_inventory_slugs(data_dir, resolver) | _read_watchlist(data_dir)
    # WFM allows ~50 simultaneous subscriptions. Cap and log.
    if len(slugs) > 50:
        slugs = set(list(slugs)[:50])
    socket_client.set_subscription(slugs)
    log.info("subscription set: %d slugs", len(slugs))


async def _main() -> None:
    s = get_settings()
    logging.basicConfig(
        level=s.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("poller starting; agent=%s redis=%s rabbit=%s", s.agent_url, s.redis_url, s.rabbitmq_url)

    redis_client = redis_lib.from_url(s.redis_url, decode_responses=True)
    wfm_cache = Cache(client=redis_client, key_prefix="wfm")

    async def _token() -> str:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{s.agent_url.rstrip('/')}/wfm-token")
            r.raise_for_status()
            return r.json()["token"]

    wfm_client = WFMClient(
        cache=wfm_cache, base_url=s.wfm_base_url, token_provider=_token,
        platform=s.wfm_platform, language=s.wfm_language,
        rate_limit_per_second=s.wfm_rate_limit_per_second,
    )
    resolver = SlugResolver()
    bus = RabbitMQBus(url=s.rabbitmq_url)
    socket_client = WFMSocketClient(token_provider=_token, platform=s.wfm_platform)

    async def _on_event(msg: dict) -> None:
        slug = msg.get("payload", {}).get("item", {}).get("url_name") or msg.get("payload", {}).get("url_name")
        if not slug:
            return
        await bus.publish("wfm", f"live.orders.{slug}", msg)

    # First-time bootstrap
    await _refresh_subscription(
        wfm_client=wfm_client, resolver=resolver,
        socket_client=socket_client, data_dir=s.data_dir,
    )

    sched = AsyncIOScheduler()
    sched.add_job(
        lambda: asyncio.create_task(_refresh_subscription(
            wfm_client=wfm_client, resolver=resolver,
            socket_client=socket_client, data_dir=s.data_dir,
        )),
        trigger="interval", minutes=30,
    )
    sched.start()

    stop = asyncio.Event()
    def _handler() -> None:
        log.info("shutdown signal received")
        stop.set()
        socket_client.stop()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handler())

    ws_task = asyncio.create_task(socket_client.run(_on_event))
    await stop.wait()
    sched.shutdown(wait=False)
    ws_task.cancel()
    await bus.aclose()
    await wfm_client.aclose()
    await redis_client.aclose()
    log.info("poller stopped")


def run() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
```

- [ ] **Step 2: Verify import + unit tests still 50 green**

```powershell
uv run python -c "from alecaframe_api.wfm.poller import run; print('ok')"
uv run pytest -v
```

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/wfm/poller.py
git commit -m "feat(wfm): poller — WFM WS listener + APScheduler subscription refresh + RabbitMQ producer"
```

---

## Task 6: Backend consumer task

**Files:** Create `src/alecaframe_api/wfm/consumer.py`, `tests/test_wfm_consumer.py`

- [ ] **Step 1: Failing test**

Create `tests/test_wfm_consumer.py`:

```python
"""Backend consumer: drain wfm.live.orders, update Redis, publish to Centrifugo."""
from __future__ import annotations

import pytest

from alecaframe_api.infra.broker import RabbitMQBus, _InMemoryBus
from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.consumer import handle_live_order


@pytest.mark.asyncio
async def test_handle_live_order_publishes_to_centrifugo() -> None:
    import fakeredis.aioredis
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(client=redis, key_prefix="wfm")
    published: list[tuple[str, dict]] = []

    class FakePublisher:
        async def publish(self, channel: str, data: dict) -> None:
            published.append((channel, data))

    await handle_live_order(
        msg={
            "type": "@WS/SUBSCRIBE/NEW_ORDERS/UPDATE",
            "payload": {"item": {"url_name": "kronen_prime_blade"}, "platinum": 33, "order_type": "sell"},
        },
        cache=cache, publisher=FakePublisher(),
    )
    assert len(published) == 1
    chan, data = published[0]
    assert chan == "wfm.orders.kronen_prime_blade"
    assert data["slug"] == "kronen_prime_blade"
    await redis.aclose()


@pytest.mark.asyncio
async def test_handle_live_order_skips_when_no_slug() -> None:
    import fakeredis.aioredis
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(client=redis, key_prefix="wfm")
    published = []

    class FakePublisher:
        async def publish(self, channel: str, data: dict) -> None:
            published.append((channel, data))

    await handle_live_order(
        msg={"type": "@WS/SOMETHING_ELSE", "payload": {}},
        cache=cache, publisher=FakePublisher(),
    )
    assert published == []
    await redis.aclose()
```

- [ ] **Step 2: Implement**

Create `src/alecaframe_api/wfm/consumer.py`:

```python
"""Backend consumer for `wfm.live.orders` topic.

For each event:
1. Extract the slug.
2. Optionally update Redis-cached order book (best effort — full refetch is
   cheaper than incremental merge for the order shapes we use).
3. Publish a Centrifugo event on `wfm.orders.{slug}` so subscribed clients
   know to refetch.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from alecaframe_api.infra.cache import Cache

log = logging.getLogger("alecaframe.wfm.consumer")


class _PublisherProto(Protocol):
    async def publish(self, channel: str, data: dict[str, Any]) -> None: ...


async def handle_live_order(*, msg: dict, cache: Cache, publisher: _PublisherProto) -> None:
    payload = msg.get("payload") or {}
    item = payload.get("item") or {}
    slug = item.get("url_name") or payload.get("url_name")
    if not slug:
        return
    # Invalidate the cached order book so next REST request refetches.
    try:
        for k in (f"orders:{slug}:0", f"orders:{slug}:1"):
            await cache.delete(k)
    except Exception as e:
        log.warning("cache invalidate failed for %s: %s", slug, e)
    await publisher.publish(f"wfm.orders.{slug}", {"slug": slug})
```

Run tests — pass.

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/wfm/consumer.py tests/test_wfm_consumer.py
git commit -m "feat(wfm): backend consumer — invalidate Redis + Centrifugo push per live order"
```

---

## Task 7: `me_router.py` — Centrifugo token endpoint

**Files:** Create `src/alecaframe_api/wfm/me_router.py`

- [ ] **Step 1: Implement**

Create `src/alecaframe_api/wfm/me_router.py`:

```python
"""Endpoints supporting frontend real-time wiring."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alecaframe_api.config import get_settings
from alecaframe_api.infra.push import CentrifugoPublisher
from alecaframe_api.wfm.dependencies import wfm_client  # for username discovery via bridge

router = APIRouter()


@router.get("/me/centrifugo-token", summary="Mint a short-lived JWT for the frontend Centrifugo client")
async def centrifugo_token() -> dict[str, str]:
    s = get_settings()
    # User id = the WFM username from agent meta (fallback: 'local').
    # We re-read it via the singleton bridge module (kept simple to avoid Depends churn).
    from alecaframe_api import main as _m
    meta = (_m.bridge.meta or {}).get("meta") or {}
    user = meta.get("wfm_username") or "local"
    pub = CentrifugoPublisher(
        api_url=s.centrifugo_api,
        api_key=s.centrifugo_api_key,
        token_hmac_secret=s.centrifugo_token_hmac_secret,
    )
    return {"token": pub.mint_user_token(user, ttl_seconds=s.centrifugo_token_ttl_seconds), "user": user}
```

- [ ] **Step 2: Add `centrifugo_token_ttl_seconds` to Settings**

In `src/alecaframe_api/config.py`, find the centrifugo block and add:

```python
    centrifugo_token_ttl_seconds: int = 3600
```

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/wfm/me_router.py src/alecaframe_api/config.py
git commit -m "feat(wfm): /me/centrifugo-token endpoint + ttl setting"
```

---

## Task 8: Wire consumer + me_router into main.py lifespan

**Files:** Modify `src/alecaframe_api/main.py`

- [ ] **Step 1: Edits**

Add imports:

```python
from alecaframe_api.infra.broker import RabbitMQBus
from alecaframe_api.infra.push import CentrifugoPublisher
from alecaframe_api.wfm.consumer import handle_live_order
from alecaframe_api.wfm.me_router import router as me_router
```

In the lifespan, AFTER the existing WFM init block and BEFORE `yield`, add:

```python
    # ----- Real-time subsystem -----
    centrifugo = CentrifugoPublisher(
        api_url=_settings.centrifugo_api,
        api_key=_settings.centrifugo_api_key,
        token_hmac_secret=_settings.centrifugo_token_hmac_secret,
    )
    bus = RabbitMQBus(url=_settings.rabbitmq_url)
    try:
        await bus.connect()
    except Exception as e:
        log.warning("RabbitMQ connect failed at startup: %s; consumer disabled", e)
    else:
        async def _on_live_order(msg: dict) -> None:
            await handle_live_order(msg=msg, cache=wfm_cache, publisher=centrifugo)
        await bus.subscribe("wfm.live.orders", _on_live_order)
```

Add `me_router` include:

```python
app.include_router(me_router)
```

(Place it right after the existing `app.include_router(wfm_router)`.)

Add cleanup on shutdown (after the existing `await wfm_client.aclose()`):

```python
    await bus.aclose()
```

- [ ] **Step 2: Verify imports + tests still pass**

```powershell
uv run pytest -v
```

Expected: 52 passed, 10 deselected (50 old + 2 new from consumer tests; + 3 from push tests + 2 from broker tests = 57 actually — re-run to confirm exact count).

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/main.py
git commit -m "feat(main): wire RabbitMQ consumer + Centrifugo + /me/centrifugo-token in lifespan"
```

---

## Task 9: Frontend Centrifuge client + hook

**Files:** Create `frontend/src/api/centrifuge.ts`, `frontend/src/hooks/useSlugChannel.ts`

- [ ] **Step 1: Centrifuge client**

Create `frontend/src/api/centrifuge.ts`:

```typescript
import { Centrifuge } from "centrifuge";

let _client: Centrifuge | null = null;

export async function getCentrifuge(): Promise<Centrifuge> {
  if (_client && _client.state === "connected") return _client;
  if (_client) {
    return _client;
  }
  const tokenResp = await fetch("/api/me/centrifugo-token");
  if (!tokenResp.ok) throw new Error("centrifugo token fetch failed");
  const { token } = (await tokenResp.json()) as { token: string };
  _client = new Centrifuge("ws://" + location.host + "/connection/websocket", {
    token,
    getToken: async () => {
      const r = await fetch("/api/me/centrifugo-token");
      const j = (await r.json()) as { token: string };
      return j.token;
    },
  });
  _client.connect();
  return _client;
}
```

- [ ] **Step 2: Hook**

Create `frontend/src/hooks/useSlugChannel.ts`:

```typescript
import { createEffect, onCleanup } from "solid-js";
import { useQueryClient } from "@tanstack/solid-query";
import { getCentrifuge } from "../api/centrifuge";

/** Subscribe to wfm.orders.{slug} for each slug currently visible.
 *  On every event, invalidate the relevant query so TanStack refetches. */
export function useSlugChannel(slugs: () => string[]): void {
  const qc = useQueryClient();
  createEffect(() => {
    const current = slugs();
    if (current.length === 0) return;
    let mounted = true;
    const subs: { unsubscribe(): void }[] = [];
    (async () => {
      const cf = await getCentrifuge();
      for (const slug of current) {
        if (!mounted) break;
        const sub = cf.newSubscription(`wfm.orders.${slug}`);
        sub.on("publication", () => {
          // Invalidate all queries whose key includes this slug.
          qc.invalidateQueries({
            predicate: (q) => q.queryKey.some((p) => p === slug),
          });
        });
        sub.subscribe();
        subs.push(sub);
      }
    })();
    onCleanup(() => {
      mounted = false;
      subs.forEach((s) => s.unsubscribe());
    });
  });
}
```

- [ ] **Step 3: typecheck + commit**

```powershell
cd frontend
npm run typecheck
cd ..
git add frontend/src/api/centrifuge.ts frontend/src/hooks/useSlugChannel.ts
git commit -m "feat(frontend): centrifuge client singleton + useSlugChannel subscription hook"
```

---

## Task 10: Wire subscriptions into PrimeParts + Inventory + Dashboard

**Files:** Modify `frontend/src/routes/PrimeParts.tsx`, `Inventory.tsx`, `Dashboard.tsx`

- [ ] **Step 1: PrimeParts subscribe to top-10 by est. value**

In `frontend/src/routes/PrimeParts.tsx`, add the hook import:

```typescript
import { useSlugChannel } from "../hooks/useSlugChannel";
```

After the `totalValue` createMemo, add:

```typescript
  // Real-time: subscribe to the top-10 most valuable visible items.
  useSlugChannel(() => filtered().slice(0, 10).map((it) => it.slug).filter(Boolean) as string[]);
```

- [ ] **Step 2: Inventory subscribe to currently-shown slot**

In `frontend/src/routes/Inventory.tsx`, after the `filtered` createMemo, add the same pattern:

```typescript
import { useSlugChannel } from "../hooks/useSlugChannel";
// ...
useSlugChannel(() => filtered().slice(0, 10).map((it) => it.slug).filter(Boolean) as string[]);
```

- [ ] **Step 3: Dashboard subscribe to widgets' slugs**

In `frontend/src/routes/Dashboard.tsx`, after the queries are defined, add:

```typescript
import { useSlugChannel } from "../hooks/useSlugChannel";
// ...
useSlugChannel(() => [
  ...(wtb.data?.items ?? []).map((m) => m.slug),
  ...(nudges.data?.items ?? []).map((n) => n.slug),
].filter(Boolean));
```

- [ ] **Step 4: typecheck + build + commit**

```powershell
cd frontend
npm run typecheck && npm run build
cd ..
git add frontend/src/routes/PrimeParts.tsx frontend/src/routes/Inventory.tsx frontend/src/routes/Dashboard.tsx
git commit -m "feat(frontend): subscribe visible slugs to live Centrifugo channels"
```

---

## Task 11: README — document channels

**Files:** Modify `README.md`

- [ ] **Step 1: Insert section**

After the "Frontend pages (B.1b)" section, insert:

```markdown
## Real-time channels (B.1c)

Frontend подписывается на `wfm.orders.{slug}` для top-10 видимых items на каждой странице.
Бэкенд consumer'ит RabbitMQ `wfm.live.orders` (durable queue), poller продюсит туда
WFM-WS события, бэкенд invalidate-ит Redis-кеш и публикует в Centrifugo.

Каналы:
| Канал | Кто publish | Кто sub |
|---|---|---|
| `wfm.orders.{slug}` | backend consumer | frontend pages |
| `system.refresh` | (B.2+) | frontend Dashboard |
| `alert.{rule_id}` | (B.3) | frontend |

Auth: backend минтит JWT (`POST /api/me/centrifugo-token`), Centrifugo проверяет HMAC.

При выключённой RabbitMQ backend стартует с warning, live-updates не работают, но REST
работает как раньше.
```

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs: B.1c real-time channels section"
```

---

## Task 12: Final smoke

- [ ] **Step 1: Build + pytest**

```powershell
cd frontend && npm run typecheck && npm run build && cd ..
uv run pytest -v
```

- [ ] **Step 2: Full stack restart + live verify**

```powershell
docker compose build backend poller frontend
docker compose up -d --force-recreate backend poller frontend
Start-Sleep -Seconds 15
```

Open `http://127.0.0.1:3000/`. Browser DevTools → Network tab → verify a `/connection/websocket` request connected.

- [ ] **Step 3: Tear down or leave running**

```powershell
docker compose ps   # confirm all healthy
```

No commit unless something needed fixing.

---

## Definition of Done

- All B.1c unit tests pass (~7 new tests across infra_push, infra_broker, wfm_consumer)
- `pytest -v` total ≈ 57 passed, 10 deselected
- Full stack starts cleanly with `./scripts/start-stack.ps1`
- Frontend opens a Centrifugo WS connection visible in DevTools Network
- When an order changes on warframe.market for a subscribed slug, the corresponding page query invalidates and refetches within ~1s
- README has the real-time-channels table
- B.1 fully complete (B.1a + B.1b + B.1c shipped)

---

## Self-Review Notes

**Spec coverage** (against design doc §6.3 and §9.1):
- ✅ WFM WS listener (poller)
- ✅ RabbitMQ topic `wfm.live.orders` (durable)
- ✅ Backend consumer → Redis invalidate + Centrifugo publish
- ✅ Centrifugo channel `wfm.orders.{slug}`
- ✅ Frontend subscription on visible slugs (≤30)
- ⏭ Signal engine writing to `signals.new` topic — deferred to B.2
- ⏭ Alert toasts via decrypt-agent — deferred to B.3

**Open risks:**
- WFM WS protocol — `@WS/SUBSCRIBE/NEW_ORDERS` may not be the exact message-type; tune at smoke.
- aio-pika mocking in tests uses an in-memory fake; if it diverges from real broker behavior, e2e catches the gap.
- Centrifugo v6 API path is `/api` POST with `X-API-Key`; if v6 changed it again, adjust `infra/push.py`.

---

**End of Phase B.1c plan.** After this lands, Phase B.1 is complete; next is B.2 (history + signals).
