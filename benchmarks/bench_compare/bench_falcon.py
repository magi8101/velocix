import asyncio
import json

from falcon.asgi import App as ASGIApp

ITEMS = [
    {"sku": f"SKU-{i:04d}", "name": f"Product {i}", "price": i * 1.25, "stock": i * 7, "active": i % 3 != 0}
    for i in range(1, 101)
]

USER = {
    "id": 42,
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "role": "admin",
    "created": "2024-01-15T10:00:00Z",
    "verified": True,
    "plan": "pro",
    "spend": 1234.56,
}


def dumps(obj):
    return json.dumps(obj, separators=(",", ":")).encode()


class User:
    async def on_get(self, req, resp, user_id):
        limit = req.get_param_as_int("limit", default=5)
        recent = ITEMS[: min(limit, 5)]
        resp.data = dumps({"user": USER, "recent": recent})


class Orders:
    async def on_post(self, req, resp):
        order = json.loads(await req.bounded_stream.read())
        total = sum(i["qty"] * i["price"] for i in order["items"])
        resp.data = dumps({"customer": order["customer"], "items": len(order["items"]), "total": round(total, 2)})


class Items:
    async def on_get(self, req, resp):
        resp.data = dumps({"items": ITEMS, "count": len(ITEMS)})


class Slow:
    async def on_get(self, req, resp):
        await asyncio.sleep(0.005)
        resp.data = dumps({"ok": True})


app = ASGIApp()
app.add_route("/users/{user_id}", User())
app.add_route("/orders", Orders())
app.add_route("/items", Items())
app.add_route("/slow", Slow())
