"""Tests for include_router and mount/StaticFiles.

Covers: merging static + dynamic routes, prefixing, StaticFiles file
serving + content-type + index.html + 404 + traversal blocking, custom
ASGI mount dispatch, and the no-mount control.
"""

import asyncio

from velocix import Router, StaticFiles, TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def test_include_router_merges_routes():
    app = Velocix()
    router = Router()

    @router.get("/ping")
    async def ping(request):
        return {"pong": True}

    @router.get("/users/{user_id}")
    async def user(user_id: int):
        return {"user_id": user_id}

    app.include_router(router)

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/ping")).json() == {"pong": True}
            assert (await client.get("/users/42")).json() == {"user_id": 42}

    _run(scenario())


def test_include_router_with_prefix():
    app = Velocix()
    router = Router()

    @router.get("/ping")
    async def ping(request):
        return {"pong": True}

    app.include_router(router, prefix="/api")

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/api/ping")).json() == {"pong": True}
            assert (await client.get("/ping")).status_code == 404

    _run(scenario())


def test_static_files_serves_file(tmp_path):
    (tmp_path / "app.js").write_text("console.log(1);")
    app = Velocix()
    app.mount("/static", StaticFiles(directory=tmp_path))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/static/app.js")
            assert response.status_code == 200
            assert response.text() == "console.log(1);"
            assert response.headers["content-type"] == "text/javascript"

    _run(scenario())


def test_static_files_index_html(tmp_path):
    (tmp_path / "index.html").write_text("<h1>hi</h1>")
    app = Velocix()
    app.mount("/static", StaticFiles(directory=tmp_path, html=True))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/static/")
            assert response.status_code == 200
            assert response.text() == "<h1>hi</h1>"

    _run(scenario())


def test_static_files_404_for_missing(tmp_path):
    app = Velocix()
    app.mount("/static", StaticFiles(directory=tmp_path))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/static/nope.txt")
            assert response.status_code == 404

    _run(scenario())


def test_static_files_blocks_traversal(tmp_path):
    (tmp_path / "secret.txt").write_text("secret")
    app = Velocix()
    app.mount("/static", StaticFiles(directory=tmp_path))

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/static/../secret.txt")
            assert response.status_code == 404

    _run(scenario())


def test_mount_dispatch_to_custom_asgi_app():
    app = Velocix()

    async def custom_app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"text/plain")],
            }
        )
        await send({"type": "http.response.body", "body": b"custom", "more_body": False})

    app.mount("/custom", custom_app)

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/custom")
            assert response.status_code == 200
            assert response.text() == "custom"

    _run(scenario())


def test_no_mounts_routes_unaffected():
    app = Velocix()

    @app.get("/plain")
    async def plain(request):
        return {"value": 7}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/plain")).json() == {"value": 7}

    _run(scenario())
