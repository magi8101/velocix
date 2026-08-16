"""Tests for response background tasks (BackgroundTask wiring).

Covers: async/sync tasks, args/kwargs, plain/JSON/streaming/file responses,
error swallowing, and the no-background control path.
"""

import asyncio
import threading

from velocix import TestClient, Velocix
from velocix.core.response import (
    BackgroundTask,
    FileResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)


def _run(coro):
    return asyncio.run(coro)


def test_async_background_runs_after_plain_response():
    events = []

    async def bg():
        events.append("bg")

    app = Velocix()

    @app.get("/")
    async def index(request):
        return Response("ok", background=BackgroundTask(bg))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.text() == "ok"
            # Background completed synchronously within the request cycle.
            assert events == ["bg"]

    _run(scenario())


def test_sync_background_runs_in_worker_thread():
    threads = []

    def bg():
        threads.append(threading.current_thread())

    app = Velocix()

    @app.get("/")
    async def index(request):
        return Response("ok", background=BackgroundTask(bg))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
        assert len(threads) == 1
        assert threads[0] is not threading.main_thread()

    _run(scenario())


def test_background_receives_args_and_kwargs():
    seen = []

    async def bg(a, b, c=3):
        seen.append((a, b, c))

    app = Velocix()

    @app.get("/")
    async def index(request):
        return Response("ok", background=BackgroundTask(bg, 1, 2, c=4))

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/")
        assert seen == [(1, 2, 4)]

    _run(scenario())


def test_background_on_json_response():
    events = []

    async def bg():
        events.append("bg")

    app = Velocix()

    @app.get("/")
    async def index(request):
        return JSONResponse({"ok": True}, background=BackgroundTask(bg))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.json() == {"ok": True}
            assert events == ["bg"]

    _run(scenario())


def test_background_on_streaming_response():
    events = []

    async def bg():
        events.append("bg")

    async def gen():
        yield b"chunk-1"
        yield b"chunk-2"

    app = Velocix()

    @app.get("/")
    async def index(request):
        return StreamingResponse(gen(), background=BackgroundTask(bg))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.body == b"chunk-1chunk-2"
            assert events == ["bg"]

    _run(scenario())


def test_background_on_file_response(tmp_path):
    events = []
    file_path = tmp_path / "data.txt"
    file_path.write_bytes(b"file-content")

    async def bg():
        events.append("bg")

    app = Velocix()

    @app.get("/")
    async def index(request):
        return FileResponse(file_path, background=BackgroundTask(bg))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.body == b"file-content"
            assert events == ["bg"]

    _run(scenario())


def test_background_exception_is_swallowed():
    async def bg():
        raise RuntimeError("boom")

    app = Velocix()

    @app.get("/")
    async def index(request):
        return Response("ok", background=BackgroundTask(bg))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.text() == "ok"

    _run(scenario())


def test_no_background_no_error():
    app = Velocix()

    @app.get("/")
    async def index(request):
        return Response("ok")

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert response.text() == "ok"

    _run(scenario())
