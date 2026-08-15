import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import msgspec

from velocix import create_app
from velocix.validation import validate_json

app = create_app()

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


class OrderItem(msgspec.Struct):
    sku: str
    qty: int
    price: float


class OrderIn(msgspec.Struct):
    customer: str
    items: list[OrderItem]


@app.get("/users/{user_id}")
async def user(user_id: int, request):
    limit = int(request.query_params.get("limit", "5"))
    recent = ITEMS[: min(limit, 5)]
    return {"user": USER, "recent": recent}


@app.post("/orders")
async def orders(request):
    body = await request.body()
    order = validate_json(body, OrderIn)
    total = sum(i.qty * i.price for i in order.items)
    return {"customer": order.customer, "items": len(order.items), "total": round(total, 2)}


@app.get("/items")
async def items(request):
    return {"items": ITEMS, "count": len(ITEMS)}


@app.get("/slow")
async def slow(request):
    await asyncio.sleep(0.005)
    return {"ok": True}
