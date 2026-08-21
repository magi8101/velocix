import asyncio
import json

from velocix import TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def test_tags_appear_in_openapi():
    app = Velocix()

    @app.get("/users", tags=["admin"])
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            path_op = schema["paths"]["/users"]["get"]
            assert "tags" in path_op
            assert "admin" in path_op["tags"]

    _run(scenario())


def test_multiple_tags():
    app = Velocix()

    @app.get("/users", tags=["admin", "users", "internal"])
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/users"]["get"]["tags"] == ["admin", "users", "internal"]

    _run(scenario())


def test_summary_in_openapi():
    app = Velocix()

    @app.get("/users", summary="List all users")
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/users"]["get"]["summary"] == "List all users"

    _run(scenario())


def test_description_in_openapi():
    app = Velocix()

    @app.get("/users", description="Returns a paginated list of all registered users.")
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/users"]["get"]["description"] == "Returns a paginated list of all registered users."

    _run(scenario())


def test_deprecated_in_openapi():
    app = Velocix()

    @app.get("/old", deprecated=True)
    async def old_endpoint():
        return {}

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/old"]["get"].get("deprecated") is True

    _run(scenario())


def test_include_in_schema_false_excludes_from_openapi():
    app = Velocix()

    @app.get("/visible")
    async def visible():
        return {}

    @app.get("/hidden", include_in_schema=False)
    async def hidden():
        return {}

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert "/visible" in schema["paths"]
            assert "/hidden" not in schema["paths"]

    _run(scenario())


def test_operation_id_in_openapi():
    app = Velocix()

    @app.get("/users", operation_id="listAllUsers")
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/users"]["get"]["operationId"] == "listAllUsers"

    _run(scenario())


def test_auto_generated_operation_id():
    app = Velocix()

    @app.get("/users")
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            op_id = schema["paths"]["/users"]["get"]["operationId"]
            assert op_id is not None
            assert len(op_id) > 0

    _run(scenario())


def test_auto_generated_summary_from_name():
    app = Velocix()

    @app.get("/users")
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            summary = schema["paths"]["/users"]["get"]["summary"]
            assert summary is not None
            assert len(summary) > 0

    _run(scenario())


def test_auto_generated_description_from_docstring():
    app = Velocix()

    @app.get("/users")
    async def list_users():
        """This endpoint returns all users in the system."""
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            desc = schema["paths"]["/users"]["get"]["description"]
            assert "all users" in desc.lower()

    _run(scenario())


def test_summary_overrides_auto_generated():
    app = Velocix()

    @app.get("/users", summary="Custom Summary")
    async def list_users():
        """This docstring should not appear as description."""
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/users"]["get"]["summary"] == "Custom Summary"

    _run(scenario())


def test_deprecated_route_still_serves_requests():
    app = Velocix()

    @app.get("/old", deprecated=True)
    async def old_endpoint():
        return {"status": "ok"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/old")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    _run(scenario())


def test_include_in_schema_false_still_serves_requests():
    app = Velocix()

    @app.get("/hidden", include_in_schema=False)
    async def hidden():
        return {"visible": True}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/hidden")
            assert resp.status_code == 200
            assert resp.json() == {"visible": True}

    _run(scenario())


def test_multiple_metadata_params_combined():
    app = Velocix()

    @app.get(
        "/users",
        tags=["admin", "v2"],
        summary="List users v2",
        description="Enhanced user listing with filtering.",
        deprecated=False,
        operation_id="listUsersV2",
    )
    async def list_users():
        return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            op = schema["paths"]["/users"]["get"]
            assert op["tags"] == ["admin", "v2"]
            assert op["summary"] == "List users v2"
            assert op["description"] == "Enhanced user listing with filtering."
            assert op.get("deprecated") is not True
            assert op["operationId"] == "listUsersV2"

    _run(scenario())


def test_tags_on_post_route():
    app = Velocix()

    @app.post("/users", tags=["admin"], status_code=201)
    async def create_user():
        return {"id": 1}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/users")
            assert resp.status_code == 201
            schema = (await client.get("/openapi.json")).json()
            assert "admin" in schema["paths"]["/users"]["post"]["tags"]

    _run(scenario())


def test_all_http_methods_get_openapi_metadata():
    app = Velocix()

    @app.get("/r", tags=["get-tag"])
    async def h(): return {}

    @app.post("/r", tags=["post-tag"])
    async def h2(): return {}

    @app.put("/r", tags=["put-tag"])
    async def h3(): return {}

    @app.delete("/r", tags=["delete-tag"])
    async def h4(): return {}

    @app.patch("/r", tags=["patch-tag"])
    async def h5(): return {}

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            path = schema["paths"]["/r"]
            assert "get" in path
            assert "post" in path
            assert "put" in path
            assert "delete" in path
            assert "patch" in path
            assert "get-tag" in path["get"]["tags"]
            assert "post-tag" in path["post"]["tags"]
            assert "put-tag" in path["put"]["tags"]
            assert "delete-tag" in path["delete"]["tags"]
            assert "patch-tag" in path["patch"]["tags"]

    _run(scenario())


def test_multiple_deprecated_routes():
    app = Velocix()

    @app.get("/v1/users", deprecated=True, tags=["v1"])
    async def v1_users(): return []

    @app.get("/v2/users", deprecated=False, tags=["v2"])
    async def v2_users(): return []

    async def scenario():
        async with TestClient(app) as client:
            schema = (await client.get("/openapi.json")).json()
            assert schema["paths"]["/v1/users"]["get"].get("deprecated") is True
            assert schema["paths"]["/v2/users"]["get"].get("deprecated") is not True

    _run(scenario())
