"""Tests for route-decorator metadata: status_code and response_model.

Covers: status_code applied to dict/str/None returns, explicit Response
wins, response_model filtering + validation errors + bypass, combination
with status_code and the response cache, and the no-metadata control.
"""

import asyncio

import msgspec

from velocix import TestClient, Velocix, cache_response
from velocix.core.response import JSONResponse, Response


def _run(coro):
    return asyncio.run(coro)


class Item(msgspec.Struct):
    sku: str
    qty: int


def test_status_code_applied_to_dict_return():
    app = Velocix()

    @app.get("/created", status_code=201)
    async def created(request):
        return {"ok": True}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/created")
            assert response.status_code == 201
            assert response.json() == {"ok": True}

    _run(scenario())


def test_status_code_applied_to_str_return():
    app = Velocix()

    @app.get("/accepted", status_code=202)
    async def accepted(request):
        return "working"

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/accepted")
            assert response.status_code == 202
            assert response.text() == "working"

    _run(scenario())


def test_status_code_applied_to_none_return():
    app = Velocix()

    @app.get("/empty", status_code=201)
    async def empty(request):
        return None

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/empty")
            assert response.status_code == 201
            assert response.body == b""

    _run(scenario())


def test_none_return_without_status_code_is_204():
    app = Velocix()

    @app.get("/nocontent")
    async def nocontent(request):
        return None

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/nocontent")
            assert response.status_code == 204

    _run(scenario())


def test_explicit_response_wins_over_status_code():
    app = Velocix()

    @app.get("/redirect", status_code=201)
    async def redirect(request):
        return Response("moved", status_code=302)

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/redirect")
            assert response.status_code == 302

    _run(scenario())


def test_explicit_jsonresponse_bypasses_response_model():
    app = Velocix()

    @app.get("/bypass", response_model=Item)
    async def bypass(request):
        return JSONResponse({"sku": "A1", "qty": 2, "extra": "kept"})

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/bypass")
            assert response.status_code == 200
            assert response.json() == {"sku": "A1", "qty": 2, "extra": "kept"}

    _run(scenario())


def test_response_model_filters_extra_fields():
    app = Velocix()

    @app.get("/item", response_model=Item)
    async def item(request):
        return {"sku": "A1", "qty": 2, "extra": "drop-me"}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/item")
            assert response.status_code == 200
            assert response.json() == {"sku": "A1", "qty": 2}

    _run(scenario())


def test_response_model_validation_error_is_422():
    app = Velocix()

    @app.get("/item", response_model=Item)
    async def item(request):
        return {"sku": "A1"}  # missing required qty

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/item")
            assert response.status_code == 422
            body = response.json()
            assert body["error"]["status_code"] == 422
            assert any("qty" in err.get("msg", "") for err in body["error"]["context"]["errors"])

    _run(scenario())


def test_response_model_with_status_code():
    app = Velocix()

    @app.post("/item", status_code=201, response_model=Item)
    async def create_item(request):
        return {"sku": "A1", "qty": 2, "extra": "dropped"}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post("/item")
            assert response.status_code == 201
            assert response.json() == {"sku": "A1", "qty": 2}

    _run(scenario())


def test_cached_route_with_status_code():
    app = Velocix()

    @app.get("/cached", status_code=201)
    @cache_response(ttl=60)
    async def cached(request):
        return {"value": 42}

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.get("/cached")
            assert r1.status_code == 201
            assert r1.json() == {"value": 42}
            # cache hit reuses the stored status
            r2 = await client.get("/cached")
            assert r2.status_code == 201

    _run(scenario())


def test_no_metadata_routes_unaffected():
    app = Velocix()

    @app.get("/plain")
    async def plain(request):
        return {"value": 7}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.get("/plain")
            assert response.status_code == 200
            assert response.json() == {"value": 7}

    _run(scenario())
