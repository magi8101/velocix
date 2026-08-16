import asyncio

from fastapi import FastAPI, Request

app = FastAPI()

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


@app.get("/users/{user_id}")
async def user(user_id: int, request: Request, limit: int = 5):
    recent = ITEMS[: min(limit, 5)]
    return {"user": USER, "recent": recent}


@app.post("/orders")
async def orders(request: Request):
    order = await request.json()
    total = sum(i["qty"] * i["price"] for i in order["items"])
    return {"customer": order["customer"], "items": len(order["items"]), "total": round(total, 2)}


@app.get("/items")
async def items(request: Request):
    return {"items": ITEMS, "count": len(ITEMS)}


@app.get("/slow")
async def slow(request: Request):
    await asyncio.sleep(0.005)
    return {"ok": True}
