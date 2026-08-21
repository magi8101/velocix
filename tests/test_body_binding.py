"""Tests for request-body model binding.

Covers: msgspec Struct params, dict params, missing/invalid bodies → 422
with structured errors, optional bodies, body + query/request combos, and
the scalar-param control (scalars stay query, not body).
"""

import asyncio
from typing import Annotated

import msgspec

from velocix import Query, TestClient, Velocix
from velocix.core.params import Body


def _run(coro):
    return asyncio.run(coro)


class OrderIn(msgspec.Struct):
    customer: str
    qty: int


def test_struct_body_param():
    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn):
        return {"customer": order.customer, "qty": order.qty}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post("/orders", json={"customer": "Ada", "qty": 3})
            assert response.status_code == 200
            assert response.json() == {"customer": "Ada", "qty": 3}

    _run(scenario())


def test_missing_body_is_422():
    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn):
        return {"customer": order.customer}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post("/orders")
            assert response.status_code == 422

    _run(scenario())


def test_invalid_body_is_422_with_errors():
    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn):
        return {"customer": order.customer}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post("/orders", json={"customer": "Ada", "qty": "not-an-int"})
            assert response.status_code == 422
            body = response.json()
            assert body["error"]["status_code"] == 422
            # msgspec 0.19 exposes only the message; it includes the location
            assert any("qty" in err.get("msg", "") for err in body["error"]["context"]["errors"])

    _run(scenario())


def test_optional_struct_body():
    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn | None = None):
        return {"order": None if order is None else order.customer}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.post("/orders")).json() == {"order": None}
            assert (await client.post("/orders", json={"customer": "Ada", "qty": 1})).json() == {
                "order": "Ada"
            }

    _run(scenario())


def test_dict_body_param():
    app = Velocix()

    @app.post("/echo")
    async def echo(payload: dict):
        return {"received": payload}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post("/echo", json={"a": 1, "b": [2, 3]})
            assert response.status_code == 200
            assert response.json() == {"received": {"a": 1, "b": [2, 3]}}

    _run(scenario())


def test_body_with_query_param():
    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn, tag: Annotated[str | None, Query()] = None):
        return {"customer": order.customer, "tag": tag}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post(
                "/orders", json={"customer": "Ada", "qty": 2}, params={"tag": "rush"}
            )
            assert response.json() == {"customer": "Ada", "tag": "rush"}

    _run(scenario())


def test_body_with_request_param():
    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn, request):
        return {"customer": order.customer, "path": request.path}

    async def scenario():
        async with TestClient(app) as client:
            response = await client.post("/orders", json={"customer": "Ada", "qty": 2})
            assert response.json() == {"customer": "Ada", "path": "/orders"}

    _run(scenario())


def test_scalar_params_stay_query():
    app = Velocix()

    @app.get("/items")
    async def items(limit: int = 10, name: str = "x"):
        return {"limit": limit, "name": name}

    async def scenario():
        async with TestClient(app) as client:
            # scalars must NOT be treated as body params
            response = await client.get("/items", params={"limit": "5", "name": "abc"})
            assert response.status_code == 200
            assert response.json() == {"limit": 5, "name": "abc"}

    _run(scenario())


# --- Multi-body and Body(embed=True) tests ---


class UserIn(msgspec.Struct):
    username: str
    full_name: str | None = None


def test_multi_body_auto_embed():
    """Two Struct params auto-embed into {"order": ..., "user": ...}."""
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(item_id: int, order: OrderIn, user: UserIn):
        return {"item_id": item_id, "customer": order.customer, "username": user.username}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={
                    "order": {"customer": "Ada", "qty": 2},
                    "user": {"username": "dave"},
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {"item_id": 1, "customer": "Ada", "username": "dave"}

    _run(scenario())


def test_multi_body_validation_error():
    """Invalid field in one of multiple bodies → 422."""
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(item_id: int, order: OrderIn, user: UserIn):
        return {"item_id": item_id}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={
                    "order": {"customer": "Ada", "qty": "not-int"},
                    "user": {"username": "dave"},
                },
            )
            assert resp.status_code == 422

    _run(scenario())


def test_multi_body_missing_field():
    """Missing one of multiple body fields → 422."""
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(item_id: int, order: OrderIn, user: UserIn):
        return {"item_id": item_id}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={"order": {"customer": "Ada", "qty": 2}},
            )
            assert resp.status_code == 422

    _run(scenario())


def test_multi_body_with_query_param():
    """Multi-body + query param in the same handler."""
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(
        item_id: int,
        order: OrderIn,
        user: UserIn,
        tag: Annotated[str | None, Query()] = None,
    ):
        return {"item_id": item_id, "tag": tag, "customer": order.customer}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1?tag=rush",
                json={
                    "order": {"customer": "Ada", "qty": 2},
                    "user": {"username": "dave"},
                },
            )
            assert resp.json() == {"item_id": 1, "tag": "rush", "customer": "Ada"}

    _run(scenario())


def test_body_embed_explicit():
    """Body(embed=True) on a single Struct wraps it in {"order": ...}."""
    app = Velocix()

    @app.post("/orders")
    async def create(order: Annotated[OrderIn, Body(embed=True)]):
        return {"customer": order.customer, "qty": order.qty}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post(
                "/orders",
                json={"order": {"customer": "Ada", "qty": 3}},
            )
            assert resp.status_code == 200
            assert resp.json() == {"customer": "Ada", "qty": 3}

    _run(scenario())


def test_body_embed_wrong_key():
    """Body(embed=True) with wrong key → 422."""
    app = Velocix()

    @app.post("/orders")
    async def create(order: Annotated[OrderIn, Body(embed=True)]):
        return {"customer": order.customer}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post(
                "/orders",
                json={"wrong_key": {"customer": "Ada", "qty": 3}},
            )
            assert resp.status_code == 422

    _run(scenario())


def test_scalar_body_marker():
    """Body() on a scalar forces it into the JSON body."""
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(
        item_id: int,
        order: OrderIn,
        importance: Annotated[int, Body()] = 0,
    ):
        return {"item_id": item_id, "customer": order.customer, "importance": importance}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={
                    "order": {"customer": "Ada", "qty": 2},
                    "importance": 5,
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {"item_id": 1, "customer": "Ada", "importance": 5}

    _run(scenario())


def test_optional_body_in_multi():
    """Optional body param missing from payload → uses default."""
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(
        item_id: int,
        order: OrderIn,
        importance: Annotated[int, Body()] = 0,
    ):
        return {"item_id": item_id, "importance": importance}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={"order": {"customer": "Ada", "qty": 2}},
            )
            assert resp.status_code == 200
            assert resp.json() == {"item_id": 1, "importance": 0}

    _run(scenario())
