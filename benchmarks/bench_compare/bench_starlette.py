import asyncio

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

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


async def user(request: Request):
    limit = int(request.query_params.get("limit", "5"))
    recent = ITEMS[: min(limit, 5)]
    return JSONResponse({"user": USER, "recent": recent})


async def orders(request: Request):
    order = await request.json()
    total = sum(i["qty"] * i["price"] for i in order["items"])
    return JSONResponse({"customer": order["customer"], "items": len(order["items"]), "total": round(total, 2)})


async def items(request: Request):
    return JSONResponse({"items": ITEMS, "count": len(ITEMS)})


async def slow(request: Request):
    await asyncio.sleep(0.005)
    return JSONResponse({"ok": True})


app = Starlette(routes=[Route("/users/{user_id}", user), Route("/orders", orders, methods=["POST"]), Route("/items", items), Route("/slow", slow)])
