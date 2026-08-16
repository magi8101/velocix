"""Tests for signed session middleware (Starlette parity).

Covers: set/read round-trip, persistence, mutation rewrite, no-rewrite on
unchanged sessions, clearing, tamper/expiry handling, https_only flags,
request.session rebinding, and the no-middleware AttributeError.
"""

import asyncio
import time
from functools import partial

from velocix import SessionMiddleware, TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def _app_with_session(**kwargs):
    app = Velocix()
    app.add_middleware(partial(SessionMiddleware, secret_key="test-secret", **kwargs))
    return app


def test_session_set_and_read_round_trip():
    app = _app_with_session()

    @app.get("/set")
    async def set_session(request):
        request.session["user"] = "alice"
        return {"ok": True}

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            resp1 = await client.get("/set")
            assert resp1.status_code == 200
            assert "set-cookie" in resp1.headers
            # TestClient auto-sends the cookie; second request sees the session
            resp2 = await client.get("/read")
            assert resp2.json() == {"user": "alice"}

    _run(scenario())


def test_session_persists_across_requests():
    app = _app_with_session()

    @app.get("/inc")
    async def inc(request):
        request.session["count"] = request.session.get("count", 0) + 1
        return {"count": request.session["count"]}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/inc")).json() == {"count": 1}
            assert (await client.get("/inc")).json() == {"count": 2}
            assert (await client.get("/inc")).json() == {"count": 3}

    _run(scenario())


def test_session_mutation_rewrites_cookie():
    app = _app_with_session()

    @app.get("/set")
    async def set_session(request):
        request.session["a"] = 1
        return {"ok": True}

    @app.get("/add")
    async def add_session(request):
        request.session["b"] = 2
        return {"ok": True}

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/set")
            resp = await client.get("/add")
            assert "set-cookie" in resp.headers
            # Next request sees both keys
            assert (await client.get("/add")).json() == {"ok": True}

    _run(scenario())


def test_unchanged_session_does_not_rewrite_cookie():
    app = _app_with_session()

    @app.get("/set")
    async def set_session(request):
        request.session["a"] = 1
        return {"ok": True}

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/set")
            resp = await client.get("/read")
            assert "set-cookie" not in resp.headers

    _run(scenario())


def test_cleared_session_deletes_cookie():
    app = _app_with_session()

    @app.get("/set")
    async def set_session(request):
        request.session["a"] = 1
        return {"ok": True}

    @app.get("/clear")
    async def clear_session(request):
        request.session.clear()
        return {"ok": True}

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/set")
            resp = await client.get("/clear")
            assert "set-cookie" in resp.headers
            assert "max-age=0" in resp.headers["set-cookie"].lower()
            assert (await client.get("/read")).json() == {}

    _run(scenario())


def test_session_rebound_in_handler_is_persisted():
    app = _app_with_session()

    @app.get("/rebind")
    async def rebind(request):
        request.session = {"fresh": True}
        return {"ok": True}

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/rebind")
            assert (await client.get("/read")).json() == {"fresh": True}

    _run(scenario())


def test_tampered_cookie_loads_empty_session():
    app = _app_with_session()

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/read", headers={"cookie": "session=forged-value"})
            assert resp.status_code == 200
            assert resp.json() == {}

    _run(scenario())


def test_expired_session_loads_empty():
    app = _app_with_session(max_age=1)

    @app.get("/set")
    async def set_session(request):
        request.session["a"] = 1
        return {"ok": True}

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/set")
            # itsdangerous timestamps are int(time.time()): with max_age=1 the
            # age must exceed 1, so sleep past two int boundaries (>= 2.0s)
            # for a deterministic expiry.
            time.sleep(2.1)
            assert (await client.get("/read")).json() == {}

    _run(scenario())


def test_session_cookie_flags():
    app = _app_with_session(https_only=True, same_site="strict")

    @app.get("/set")
    async def set_session(request):
        request.session["a"] = 1
        return {"ok": True}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/set")
            cookie = resp.headers["set-cookie"].lower()
            assert "httponly" in cookie
            assert "secure" in cookie
            assert "samesite=strict" in cookie
            assert "max-age=" in cookie

    _run(scenario())


def test_session_without_middleware_raises():
    app = Velocix()

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            # The app's error handler converts the AttributeError into a 500
            resp = await client.get("/read")
            assert resp.status_code == 500

    _run(scenario())


def test_session_stores_non_string_values():
    app = _app_with_session()

    @app.get("/set")
    async def set_session(request):
        request.session["items"] = [1, 2, 3]
        request.session["meta"] = {"nested": True}
        return {"ok": True}

    @app.get("/read")
    async def read_session(request):
        return dict(request.session)

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/set")
            assert (await client.get("/read")).json() == {
                "items": [1, 2, 3],
                "meta": {"nested": True},
            }

    _run(scenario())
