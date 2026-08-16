import asyncio

from litestar import Litestar, get, post
from msgspec import Struct

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


class OrderItem(Struct):
    sku: str
    qty: int
    price: float


class OrderIn(Struct):
    customer: str
    items: list[OrderItem]


@get("/users/{user_id:int}")
async def user(user_id: int, limit: int = 5) -> dict:
    recent = ITEMS[: min(limit, 5)]
    return {"user": USER, "recent": recent}


@post("/orders", status_code=200)
async def orders(data: OrderIn) -> dict:
    total = sum(i.qty * i.price for i in data.items)
    return {"customer": data.customer, "items": len(data.items), "total": round(total, 2)}


@get("/items")
async def items() -> dict:
    return {"items": ITEMS, "count": len(ITEMS)}


@get("/slow")
async def slow() -> dict:
    await asyncio.sleep(0.005)
    return {"ok": True}


app = Litestar([user, orders, items, slow])
