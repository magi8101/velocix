import asyncio

from velocix import Router, TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def test_include_router_with_tags():
    app = Velocix()
    router = Router()

    @router.get("/users")
    async def list_users():
        return []

    @router.post("/users")
    async def create_user():
        return {}

    app.include_router(router, tags=["users"])

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            paths = schema.get("paths", {})
            assert "/users" in paths
            assert "get" in paths["/users"]
            assert "post" in paths["/users"]

    _run(scenario())


def test_include_router_with_prefix_and_tags():
    app = Velocix()
    router = Router()

    @router.get("/items")
    async def list_items():
        return []

    app.include_router(router, prefix="/api/v1", tags=["items"])

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/api/v1/items")
            assert resp.status_code == 200

    _run(scenario())


def test_include_router_tags_applied_to_routes():
    app = Velocix()
    router = Router()

    @router.get("/ping")
    async def ping():
        return {}

    app.include_router(router, tags=["health"])

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping")
            assert resp.status_code == 200

    _run(scenario())


def test_include_router_without_tags():
    app = Velocix()
    router = Router()

    @router.get("/ping")
    async def ping():
        return {}

    app.include_router(router)

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping")
            assert resp.status_code == 200

    _run(scenario())


def test_openapi_tag_descriptions():
    app = Velocix(
        tags=[
            {"name": "users", "description": "User management endpoints"},
            {"name": "items", "description": "Item catalog endpoints"},
        ]
    )

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            tags = schema.get("tags", [])
            assert len(tags) == 2
            assert tags[0]["name"] == "users"
            assert tags[0]["description"] == "User management endpoints"
            assert tags[1]["name"] == "items"
            assert tags[1]["description"] == "Item catalog endpoints"

    _run(scenario())


def test_openapi_tag_descriptions_empty():
    app = Velocix()

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            tags = schema.get("tags", [])
            assert len(tags) == 0

    _run(scenario())


def test_include_router_multiple_routers_different_tags():
    app = Velocix()
    users_router = Router()
    items_router = Router()

    @users_router.get("/users")
    async def list_users():
        return []

    @items_router.get("/items")
    async def list_items():
        return []

    app.include_router(users_router, prefix="/api", tags=["users"])
    app.include_router(items_router, prefix="/api", tags=["items"])

    async def scenario():
        async with TestClient(app) as client:
            resp1 = await client.get("/api/users")
            assert resp1.status_code == 200
            resp2 = await client.get("/api/items")
            assert resp2.status_code == 200

    _run(scenario())


def test_include_router_tags_with_handler_tags():
    app = Velocix()

    @app.get("/users")
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/users")
            assert resp.status_code == 200

    _run(scenario())
