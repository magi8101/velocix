import asyncio
from typing import Annotated

import msgspec

from velocix import Query, TestClient, Velocix
from velocix.core.depends import Depends
from velocix.core.params import Body


def _run(coro):
    return asyncio.run(coro)


class OrderIn(msgspec.Struct):
    customer: str
    qty: int


class AddressIn(msgspec.Struct):
    street: str
    city: str


class PaymentIn(msgspec.Struct):
    method: str
    amount: float


def test_three_struct_bodies():
    app = Velocix()

    @app.put("/orders/{order_id}")
    async def update(order_id: int, order: OrderIn, address: AddressIn, payment: PaymentIn):
        return {
            "order_id": order_id,
            "customer": order.customer,
            "city": address.city,
            "method": payment.method,
        }

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/orders/1",
                json={
                    "order": {"customer": "Ada", "qty": 3},
                    "address": {"street": "123 Main", "city": "NYC"},
                    "payment": {"method": "card", "amount": 99.99},
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {
                "order_id": 1,
                "customer": "Ada",
                "city": "NYC",
                "method": "card",
            }

    _run(scenario())


def test_empty_json_body():
    app = Velocix()

    @app.post("/echo")
    async def echo(payload: dict):
        return {"received": payload}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/echo", json={})
            assert resp.status_code == 200
            assert resp.json() == {"received": {}}

    _run(scenario())


def test_nested_struct_body():
    class Inner(msgspec.Struct):
        x: int

    class Outer(msgspec.Struct):
        inner: Inner
        name: str

    app = Velocix()

    @app.post("/nested")
    async def nested(body: Outer):
        return {"name": body.name, "x": body.inner.x}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/nested", json={"inner": {"x": 42}, "name": "test"})
            assert resp.status_code == 200
            assert resp.json() == {"name": "test", "x": 42}

    _run(scenario())


def test_list_body():
    app = Velocix()

    @app.post("/items")
    async def create_items(items: list[dict]):
        return {"count": len(items), "items": items}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/items", json=[{"a": 1}, {"b": 2}])
            assert resp.status_code == 200
            assert resp.json()["count"] == 2

    _run(scenario())


def test_body_with_depends():
    async def get_user_id(request):
        return 42

    app = Velocix()

    @app.post("/orders")
    async def create(order: OrderIn, user_id: int = Depends(get_user_id)):
        return {"customer": order.customer, "user_id": user_id}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/orders", json={"customer": "Ada", "qty": 2})
            assert resp.status_code == 200
            assert resp.json()["user_id"] == 42

    _run(scenario())


def test_three_structs_validation_error_in_second():
    app = Velocix()

    @app.put("/orders/{order_id}")
    async def update(order_id: int, order: OrderIn, address: AddressIn, payment: PaymentIn):
        return {}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/orders/1",
                json={
                    "order": {"customer": "Ada", "qty": 3},
                    "address": {"street": "123 Main", "city": "NYC"},
                    "payment": {"method": "card"},  # missing required amount
                },
            )
            assert resp.status_code == 422

    _run(scenario())


def test_three_structs_missing_third():
    app = Velocix()

    @app.put("/orders/{order_id}")
    async def update(order_id: int, order: OrderIn, address: AddressIn, payment: PaymentIn):
        return {}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/orders/1",
                json={
                    "order": {"customer": "Ada", "qty": 3},
                    "address": {"street": "123 Main", "city": "NYC"},
                },
            )
            assert resp.status_code == 422

    _run(scenario())


def test_multi_body_with_path_and_query():
    app = Velocix()

    @app.put("/orgs/{org_id}/items/{item_id}")
    async def update(
        org_id: int,
        item_id: int,
        order: OrderIn,
        address: AddressIn,
        tag: Annotated[str, Query()] = "anon",
    ):
        return {
            "org_id": org_id,
            "item_id": item_id,
            "customer": order.customer,
            "city": address.city,
            "tag": tag,
        }

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/orgs/1/items/2?tag=bob",
                json={
                    "order": {"customer": "Ada", "qty": 2},
                    "address": {"street": "123 Main", "city": "NYC"},
                },
            )
            assert resp.status_code == 200
            assert resp.json()["org_id"] == 1
            assert resp.json()["tag"] == "bob"
            assert resp.json()["city"] == "NYC"

    _run(scenario())


def test_body_list_of_structs():
    class Tag(msgspec.Struct):
        name: str

    app = Velocix()

    @app.post("/tags")
    async def create_tags(tags: list[Tag]):
        return {"count": len(tags), "names": [t.name for t in tags]}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/tags", json=[{"name": "a"}, {"name": "b"}])
            assert resp.status_code == 200
            assert resp.json() == {"count": 2, "names": ["a", "b"]}

    _run(scenario())


def test_optional_struct_in_multi_body():
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(
        item_id: int,
        order: OrderIn,
        address: AddressIn | None = None,
    ):
        return {"item_id": item_id, "has_address": address is not None}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={"order": {"customer": "Ada", "qty": 2}},
            )
            assert resp.status_code == 200
            assert resp.json()["has_address"] is False

    _run(scenario())


def test_embed_with_depends():
    async def get_token(request):
        return "tok_123"

    app = Velocix()

    @app.post("/orders")
    async def create(
        order: Annotated[OrderIn, Body(embed=True)],
        token: str = Depends(get_token),
    ):
        return {"customer": order.customer, "token": token}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post(
                "/orders",
                json={"order": {"customer": "Ada", "qty": 2}},
            )
            assert resp.status_code == 200
            assert resp.json()["token"] == "tok_123"

    _run(scenario())


def test_scalar_body_with_multi_body():
    app = Velocix()

    @app.put("/items/{item_id}")
    async def update(
        item_id: int,
        order: OrderIn,
        priority: Annotated[int, Body()] = 0,
        label: Annotated[str, Body()] = "default",
    ):
        return {"item_id": item_id, "priority": priority, "label": label}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.put(
                "/items/1",
                json={
                    "order": {"customer": "Ada", "qty": 2},
                    "priority": 5,
                    "label": "urgent",
                },
            )
            assert resp.status_code == 200
            assert resp.json() == {"item_id": 1, "priority": 5, "label": "urgent"}

    _run(scenario())
