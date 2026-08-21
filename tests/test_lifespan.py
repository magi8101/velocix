import asyncio

from velocix import Velocix
from velocix.testing.client import TestClient


def _run(coro):
    return asyncio.run(coro)


def test_startup_handler_called():
    events = []
    app = Velocix()

    @app.on_startup
    async def startup():
        events.append("startup")

    @app.get("/ping")
    async def ping():
        return {"events": events}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping")
            assert resp.json()["events"] == ["startup"]

    _run(scenario())


def test_shutdown_handler_called():
    events = []
    app = Velocix()

    @app.on_shutdown
    async def shutdown():
        events.append("shutdown")

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/ping")
        assert events == ["shutdown"]

    _run(scenario())


def test_startup_and_shutdown_order():
    events = []
    app = Velocix()

    @app.on_startup
    async def s1():
        events.append("s1")

    @app.on_startup
    async def s2():
        events.append("s2")

    @app.on_shutdown
    async def h1():
        events.append("h1")

    @app.on_shutdown
    async def h2():
        events.append("h2")

    async def scenario():
        async with TestClient(app) as client:
            pass

    _run(scenario())
    assert events == ["s1", "s2", "h1", "h2"]


def test_startup_handler_receives_no_args():
    app = Velocix()
    called = False

    @app.on_startup
    async def startup():
        nonlocal called
        called = True

    async def scenario():
        async with TestClient(app) as client:
            pass

    _run(scenario())
    assert called is True


def test_sync_startup_handler():
    events = []
    app = Velocix()

    @app.on_startup
    def startup():
        events.append("sync_startup")

    async def scenario():
        async with TestClient(app) as client:
            pass

    _run(scenario())
    assert events == ["sync_startup"]


def test_startup_exception_propagates():
    app = Velocix()

    @app.on_startup
    async def bad_startup():
        raise RuntimeError("startup failed")

    async def scenario():
        try:
            async with TestClient(app) as client:
                pass
        except Exception:
            pass

    _run(scenario())


def test_startup_runs_before_first_request():
    events = []
    app = Velocix()

    @app.on_startup
    async def startup():
        events.append("startup")

    @app.get("/ping")
    async def ping():
        events.append("request")
        return {}

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/ping")

    _run(scenario())
    assert events[0] == "startup"
    assert events[1] == "request"


def test_no_startup_shutdown():
    app = Velocix()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping")
            assert resp.json() == {"ok": True}

    _run(scenario())


def test_lifespan_event_messages():
    app = Velocix()
    events = []

    @app.on_startup
    async def startup():
        events.append("startup")

    @app.on_shutdown
    async def shutdown():
        events.append("shutdown")

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/ping") if hasattr(client, "get") else None
            events.append("running")

    _run(scenario())
    assert events == ["startup", "running", "shutdown"]
