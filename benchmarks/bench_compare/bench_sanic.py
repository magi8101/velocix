import asyncio

from sanic import Sanic
from sanic.response import json

app = Sanic("bench")

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


@app.get("/users/<user_id:int>")
async def user(request, user_id: int):
    limit = int(request.args.get("limit", "5"))
    recent = ITEMS[: min(limit, 5)]
    return json({"user": USER, "recent": recent})


@app.post("/orders")
async def orders(request):
    order = request.json
    total = sum(i["qty"] * i["price"] for i in order["items"])
    return json({"customer": order["customer"], "items": len(order["items"]), "total": round(total, 2)})


@app.get("/items")
async def items(request):
    return json({"items": ITEMS, "count": len(ITEMS)})


@app.get("/slow")
async def slow(request):
    await asyncio.sleep(0.005)
    return json({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, workers=4)
