import asyncio
from typing import Annotated

import msgspec

from velocix import TestClient, Velocix
from velocix.core.params import Body
from velocix.core.response import HTMLResponse, Response


def _run(coro):
    return asyncio.run(coro)


def test_put_method():
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(item_id: int, name: str):
        return {"item_id": item_id, "name": name}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put("/items/1", params={"name": "widget"})
            assert resp.status_code == 200
            assert resp.json() == {"item_id": 1, "name": "widget"}

    _run(scenario())


def test_patch_method():
    app = Velocix()

    @app.patch("/items/{item_id}")
    async def patch_item(item_id: int, name: str):
        return {"item_id": item_id, "name": name}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.patch("/items/1", params={"name": "new"})
            assert resp.status_code == 200

    _run(scenario())


def test_delete_method():
    app = Velocix()

    @app.delete("/items/{item_id}")
    async def delete_item(item_id: int):
        return {"deleted": item_id}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.delete("/items/1")
            assert resp.status_code == 200
            assert resp.json() == {"deleted": 1}

    _run(scenario())


def test_head_method():
    app = Velocix()

    @app.route("/items", methods={"HEAD"})
    async def head_items():
        return Response(b"", headers={"x-total": "42"})

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.request("HEAD", "/items")
            assert resp.status_code == 200

    _run(scenario())


def test_request_method_property():
    app = Velocix()

    @app.get("/check")
    async def check(request):
        return {"method": request.method}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/check")
            assert resp.json() == {"method": "GET"}

    _run(scenario())


def test_request_path_property():
    app = Velocix()

    @app.get("/deep/nested/path")
    async def deep(request):
        return {"path": request.path}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/deep/nested/path")
            assert resp.json() == {"path": "/deep/nested/path"}

    _run(scenario())


def test_request_query_string():
    app = Velocix()

    @app.get("/search")
    async def search(request):
        return {"qs": request.query_string.decode("utf-8")}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/search?q=hello&limit=10")
            assert resp.json() == {"qs": "q=hello&limit=10"}

    _run(scenario())


def test_request_app_binding():
    app = Velocix()

    @app.get("/app-check")
    async def check(request):
        return {"is_app": request.app is app}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/app-check")
            assert resp.json() == {"is_app": True}

    _run(scenario())


def test_response_class_html():
    app = Velocix()

    @app.get("/page")
    async def page():
        return HTMLResponse("<h1>Hello</h1>")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/page")
            assert resp.status_code == 200
            assert "<h1>" in resp.text()

    _run(scenario())


def test_response_class_custom():
    app = Velocix()

    @app.get("/custom")
    async def custom():
        return HTMLResponse("<p>custom</p>")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/custom")
            assert resp.status_code == 200

    _run(scenario())


def test_route_method_decorator():
    app = Velocix()

    @app.route("/both", methods={"GET", "POST"})
    async def both(request):
        return {"method": request.method}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/both")).json() == {"method": "GET"}
            assert (await client.post("/both")).json() == {"method": "POST"}

    _run(scenario())


def test_default_get_method():
    app = Velocix()

    @app.route("/default")
    async def default():
        return {}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/default")
            assert resp.status_code == 200
            resp = await client.post("/default")
            assert resp.status_code == 405

    _run(scenario())


def test_post_with_json_body_and_path_param():
    class Item(msgspec.Struct):
        name: str
        qty: int

    app = Velocix()

    @app.post("/orgs/{org_id}/items")
    async def create(org_id: int, item: Item):
        return {"org_id": org_id, "name": item.name, "qty": item.qty}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/orgs/5/items", json={"name": "widget", "qty": 10})
            assert resp.status_code == 200
            assert resp.json() == {"org_id": 5, "name": "widget", "qty": 10}

    _run(scenario())


def test_patch_with_body_and_query():
    app = Velocix()

    @app.patch("/users/{user_id}")
    async def patch_user(
        user_id: int,
        name: Annotated[str, Body()] = "anon",
        token: Annotated[str, Body()] = "",
    ):
        return {"user_id": user_id, "name": name, "token": token}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.patch("/users/1", json={"name": "alice", "token": "abc"})
            assert resp.status_code == 200
            assert resp.json() == {"user_id": 1, "name": "alice", "token": "abc"}

    _run(scenario())


def test_multiple_http_methods_same_path():
    app = Velocix()

    @app.get("/resource")
    async def get_resource():
        return {"action": "get"}

    @app.post("/resource")
    async def create_resource():
        return {"action": "create"}

    @app.put("/resource")
    async def update_resource():
        return {"action": "update"}

    @app.delete("/resource")
    async def delete_resource():
        return {"action": "delete"}

    @app.patch("/resource")
    async def patch_resource():
        return {"action": "patch"}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/resource")).json()["action"] == "get"
            assert (await client.post("/resource")).json()["action"] == "create"
            assert (await client.put("/resource")).json()["action"] == "update"
            assert (await client.delete("/resource")).json()["action"] == "delete"
            assert (await client.patch("/resource")).json()["action"] == "patch"

    _run(scenario())


def test_request_url_property():
    app = Velocix()

    @app.get("/items")
    async def items(request):
        return {"url": request.path}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/items")
            assert resp.json()["url"] == "/items"

    _run(scenario())
