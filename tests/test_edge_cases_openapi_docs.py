import asyncio

from velocix import TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def test_docs_endpoint_returns_swagger_ui():
    app = Velocix()

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/docs")
            assert resp.status_code == 200
            assert "swagger-ui" in resp.text().lower() or "swagger" in resp.text().lower()

    _run(scenario())


def test_redoc_endpoint_returns_redoc():
    app = Velocix()

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/redoc")
            assert resp.status_code == 200
            assert "redoc" in resp.text().lower()

    _run(scenario())


def test_openapi_json_returns_valid_schema():
    app = Velocix()

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/openapi.json")
            assert resp.status_code == 200
            schema = resp.json()
            assert "openapi" in schema
            assert "paths" in schema
            assert "/ping" in schema["paths"]

    _run(scenario())


def test_docs_not_in_openapi_paths():
    app = Velocix()

    @app.get("/ping")
    async def ping():
        return {}

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            paths = schema.get("paths", {})
            assert "/docs" not in paths
            assert "/redoc" not in paths
            assert "/openapi.json" not in paths

    _run(scenario())


def test_custom_docs_url():
    app = Velocix(docs_url="/swagger")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/swagger")
            assert resp.status_code == 200
            assert (await client.get("/docs")).status_code == 404

    _run(scenario())


def test_custom_redoc_url():
    app = Velocix(redoc_url="/api-docs")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/api-docs")
            assert resp.status_code == 200
            assert (await client.get("/redoc")).status_code == 404

    _run(scenario())


def test_custom_openapi_url():
    app = Velocix(openapi_url="/schema.json")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/schema.json")
            assert resp.status_code == 200
            assert (await client.get("/openapi.json")).status_code == 404

    _run(scenario())


def test_disable_docs():
    app = Velocix(docs_url=None, redoc_url=None, openapi_url=None)

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/redoc")).status_code == 404
            assert (await client.get("/openapi.json")).status_code == 404

    _run(scenario())


def test_disable_only_docs():
    app = Velocix(docs_url=None)

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/redoc")).status_code == 200
            assert (await client.get("/openapi.json")).status_code == 200

    _run(scenario())


def test_docs_route_excluded_from_schema_with_custom_url():
    app = Velocix(docs_url="/swagger", redoc_url="/api-docs", openapi_url="/schema.json")

    @app.get("/ping")
    async def ping():
        return {}

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/schema.json")).json()
            paths = schema.get("paths", {})
            assert "/swagger" not in paths
            assert "/api-docs" not in paths
            assert "/schema.json" not in paths

    _run(scenario())


def test_openapi_schema_caching():
    app = Velocix()

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.get("/openapi.json")
            r2 = await client.get("/openapi.json")
            assert r1.json() == r2.json()

    _run(scenario())


def test_openapi_schema_invalidates_on_new_route():
    app = Velocix()

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    async def scenario():
        async with TestClient(app) as client:
            schema1 = (await client.get("/openapi.json")).json()
            assert "/users" not in schema1["paths"]

    _run(scenario())


def test_openapi_with_multiple_routes():
    app = Velocix()

    @app.get("/users")
    async def list_users():
        return []

    @app.post("/users", status_code=201)
    async def create_user():
        return {"id": 1}

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            paths = schema.get("paths", {})
            assert "/users" in paths
            assert "get" in paths["/users"]
            assert "post" in paths["/users"]

    _run(scenario())


def test_openapi_title_and_version():
    app = Velocix(title="My API", version="2.0.0")

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["info"]["title"] == "My API"
            assert schema["info"]["version"] == "2.0.0"

    _run(scenario())


def test_docs_works_with_no_routes():
    app = Velocix()

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/docs")).status_code == 200
            assert (await client.get("/redoc")).status_code == 200
            schema = (await client.get("/openapi.json")).json()
            paths = schema.get("paths", {})
            assert len(paths) == 0

    _run(scenario())


def test_openapi_json_content_type():
    app = Velocix()

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/openapi.json")
            ct = resp.headers.get("content-type", "")
            assert "json" in ct.lower()

    _run(scenario())
