"""SSE auth + rate-limit tests for /api/v1/sse/boards/{name}.

Covered paths:
  - missing token query param → 422
  - invalid / refresh token   → 401
  - blocked access token      → 401
  - connect rate-limit        → 429 before stream starts, keyed by user
  - concurrent stream cap     → 429, slot released on setup failure
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from starlette.requests import ClientDisconnect
from starlette.types import Message, Scope

from app.api.v1.states import _SubscriptionResponse
from app.core import _jwt
from app.core.config import settings
from app.core.ratelimit import ConcurrencyLimiter, sse_stream_limiter, ws_connect_limiter
from app.core.security import (
    blocklist_token,
    create_access_token,
    create_refresh_token,
)
from app.main import app
from app.models.user import User
from app.schemas.board import BoardConfig


def _reset_limiter() -> None:
    ws_connect_limiter._calls.clear()


@pytest.fixture(autouse=True)
def _reset_sse_state():
    _reset_limiter()
    yield
    _reset_limiter()


@pytest.mark.asyncio
async def test_sse_requires_token(client, admin_user):
    response = await client.get("/api/v1/sse/boards/demo")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sse_rejects_refresh_token_instead_of_access(client, admin_user):
    refresh = create_refresh_token(admin_user.user_id)
    response = await client.get(f"/api/v1/sse/boards/demo?token={refresh}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_rejects_blocked_access_token(client, admin_user):
    token = create_access_token(admin_user.user_id)
    payload = _jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    jti = str(payload["jti"])
    blocklist_token(jti, datetime.now(UTC) + timedelta(minutes=5))

    response = await client.get(f"/api/v1/sse/boards/demo?token={token}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_rate_limiter_rejects_connection_floods(client, admin_user, monkeypatch):
    """When the rate limiter reports the client as blocked, the SSE endpoint
    refuses the request before any board or auth lookup.
    """
    token = create_access_token(admin_user.user_id)
    monkeypatch.setattr(ws_connect_limiter, "is_blocked", lambda _key: True)

    response = await client.get(f"/api/v1/sse/boards/demo?token={token}")
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_sse_rejects_invalid_token(client, admin_user):
    response = await client.get("/api/v1/sse/boards/demo?token=garbage")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_rate_limit_is_keyed_by_user_not_proxy_ip(client, admin_user, monkeypatch):
    """Behind the OMD proxy every request comes from loopback; one user's
    reconnect storm must not use up everybody else's budget."""
    token = create_access_token(admin_user.user_id)
    keys: list[str] = []
    monkeypatch.setattr(ws_connect_limiter, "is_blocked", lambda key: keys.append(key) or True)

    response = await client.get(f"/api/v1/sse/boards/demo?token={token}")
    assert response.status_code == 429
    assert keys == [admin_user.name]


@pytest.mark.asyncio
async def test_sse_invalid_token_is_not_counted(client, admin_user, monkeypatch):
    recorded: list[str] = []
    monkeypatch.setattr(ws_connect_limiter, "record", recorded.append)

    response = await client.get("/api/v1/sse/boards/demo?token=garbage")
    assert response.status_code == 401
    assert recorded == []


@pytest.mark.asyncio
async def test_sse_refuses_streams_above_the_concurrency_cap(client, admin_user, monkeypatch):
    token = create_access_token(admin_user.user_id)
    monkeypatch.setattr(
        "app.api.v1.states.board_service.get_board", lambda name: BoardConfig(name=name)
    )
    monkeypatch.setattr(sse_stream_limiter, "try_acquire", lambda _key: False)

    response = await client.get(f"/api/v1/sse/boards/demo?token={token}")
    assert response.status_code == 429


@pytest.mark.asyncio
async def test_sse_releases_the_slot_when_setup_fails(client, admin_user, monkeypatch):
    token = create_access_token(admin_user.user_id)
    limiter = ConcurrencyLimiter(max_per_key=1, max_total=1)
    monkeypatch.setattr("app.api.v1.states.sse_stream_limiter", limiter)
    monkeypatch.setattr(
        "app.api.v1.states.board_service.get_board", lambda name: BoardConfig(name=name)
    )

    def _boom(*_args: object) -> None:
        raise RuntimeError("snapshot store down")

    monkeypatch.setattr("app.api.v1.states.state_service.drop_states_snapshot", _boom)

    with pytest.raises(RuntimeError):
        await client.get(f"/api/v1/sse/boards/demo?token={token}")
    assert limiter.try_acquire(admin_user.name)


@pytest.mark.asyncio
async def test_subscription_closes_when_client_drops_before_the_stream_starts():
    """Starlette sends the headers before it first iterates the stream; a client
    gone at that point never runs the generator, so the response itself must
    release the subscription."""
    closed: list[bool] = []
    started: list[bool] = []

    async def stream() -> AsyncIterator[bytes]:
        started.append(True)
        yield b""

    async def receive() -> dict[str, object]:
        return {"type": "http.disconnect"}

    async def send(_message: object) -> None:
        raise OSError("client went away")

    response = _SubscriptionResponse(stream(), on_close=lambda: closed.append(True), headers={})
    scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    with pytest.raises(ClientDisconnect):
        await response(scope, receive, send)
    assert started == []
    assert closed == [True]


@pytest.mark.asyncio
@pytest.mark.usefixtures("client")
async def test_sse_stream_sends_a_byte_at_once(
    admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """mod_proxy forwards the response headers only together with the first
    body byte; a stream that stays silent until the first tick keeps the
    browser's EventSource from opening."""
    token = create_access_token(admin_user.user_id)
    monkeypatch.setattr(
        "app.api.v1.states.board_service.get_board", lambda name: BoardConfig(name=name)
    )
    monkeypatch.setattr("app.api.v1.states._broadcast_tasks", {"demo": _RunningTask()})
    bodies: list[bytes] = []
    first_body = asyncio.Event()

    async def receive() -> Message:
        if not bodies:
            await asyncio.wait_for(first_body.wait(), timeout=2)
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and message.get("body"):
            bodies.append(cast(bytes, message["body"]))
            first_body.set()

    scope: Scope = {
        "type": "http",
        "asgi": {"spec_version": "2.4", "version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/v1/sse/boards/demo",
        "raw_path": b"/api/v1/sse/boards/demo",
        "query_string": f"token={token}".encode(),
        "headers": [(b"host", b"test")],
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "root_path": "",
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=5)
    assert bodies[0].startswith(b":")
    assert sse_stream_limiter.try_acquire(admin_user.name)
    sse_stream_limiter.release(admin_user.name)


class _RunningTask:
    def done(self) -> bool:
        return False


class TestConcurrencyLimiter:
    def test_caps_per_key(self) -> None:
        limiter = ConcurrencyLimiter(max_per_key=2, max_total=10)
        assert limiter.try_acquire("a") and limiter.try_acquire("a")
        assert not limiter.try_acquire("a")
        assert limiter.try_acquire("b")

    def test_caps_in_total(self) -> None:
        limiter = ConcurrencyLimiter(max_per_key=5, max_total=2)
        assert limiter.try_acquire("a") and limiter.try_acquire("b")
        assert not limiter.try_acquire("c")

    def test_release_frees_a_slot_and_ignores_unknown_keys(self) -> None:
        limiter = ConcurrencyLimiter(max_per_key=1, max_total=1)
        assert limiter.try_acquire("a")
        limiter.release("never-acquired")
        assert not limiter.try_acquire("b")
        limiter.release("a")
        assert limiter.try_acquire("b")
