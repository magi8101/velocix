import asyncio
from dataclasses import dataclass

from blacksheep import Application, FromJSON, get, post

app = Application()

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


@dataclass
class OrderItem:
    sku: str
    qty: int
    price: float


@dataclass
class OrderIn:
    customer: str
    items: list[OrderItem]


@get("/users/{user_id}")
async def user(user_id: int, limit: int = 5):
    recent = ITEMS[: min(limit, 5)]
    return {"user": USER, "recent": recent}


@post("/orders")
async def orders(data: FromJSON[OrderIn]):
    order = data.value
    total = sum(i.qty * i.price for i in order.items)
    return {"customer": order.customer, "items": len(order.items), "total": round(total, 2)}


@get("/items")
async def items():
    return {"items": ITEMS, "count": len(ITEMS)}


@get("/slow")
async def slow():
    await asyncio.sleep(0.005)
    return {"ok": True}
