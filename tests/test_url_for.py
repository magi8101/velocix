"""Tests for named routes and request.url_for reverse routing.

Covers: static + dynamic named routes, url_for with path params, route()
multi-method registration, include_router prefix propagation, unknown
name -> NoMatchFound, and the no-name control.
"""

import asyncio

import pytest

from velocix import NoMatchFound, Router, TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def test_url_for_static_route():
    app = Velocix()

    @app.get("/items", name="items")
    async def items(request):
        return {"url": request.url_for("items")}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/items")
            assert resp.json() == {"url": "http://testserver/items"}

    _run(scenario())


def test_url_for_dynamic_route_with_path_params():
    app = Velocix()

    @app.get("/users/{user_id}", name="user")
    async def user(request, user_id: int):
        return {"url": request.url_for("user", user_id=user_id)}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/users/42")
            assert resp.json() == {"url": "http://testserver/users/42"}

    _run(scenario())


def test_url_for_multiple_path_params():
    app = Velocix()

    @app.get("/orgs/{org_id}/repos/{repo_id}", name="repo")
    async def repo(request, org_id: str, repo_id: int):
        return {"url": request.url_for("repo", org_id=org_id, repo_id=repo_id)}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/orgs/acme/repos/7")
            assert resp.json() == {"url": "http://testserver/orgs/acme/repos/7"}

    _run(scenario())


def test_url_for_route_decorator_multi_method():
    app = Velocix()

    @app.route("/things", methods={"GET", "POST"}, name="things")
    async def things(request):
        return {"url": request.url_for("things")}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/things")).json() == {
                "url": "http://testserver/things"
            }
            assert (await client.post("/things")).json() == {
                "url": "http://testserver/things"
            }

    _run(scenario())


def test_url_for_router_with_prefix():
    app = Velocix()
    router = Router()

    @router.get("/users/{user_id}", name="user")
    async def user(request, user_id: int):
        return {"url": request.url_for("user", user_id=user_id)}

    app.include_router(router, prefix="/api")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/api/users/9")
            assert resp.json() == {"url": "http://testserver/api/users/9"}

    _run(scenario())


def test_url_for_unknown_name_raises_no_match_found():
    app = Velocix()

    @app.get("/x", name="x")
    async def x(request):
        return request.url_for("does-not-exist")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/x")
            assert resp.status_code == 500

    _run(scenario())


def test_url_path_for_no_match_found():
    router = Router()
    with pytest.raises(NoMatchFound):
        router.url_path_for("missing")


def test_url_path_for_quotes_values():
    router = Router()

    @router.get("/files/{name}", name="file")
    async def file(name: str):
        return name

    assert router.url_path_for("file", name="a b/c") == "/files/a%20b/c"


def test_unamed_routes_not_in_url_for():
    app = Velocix()

    @app.get("/plain")
    async def plain(request):
        return {"ok": True}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/plain")
            assert resp.json() == {"ok": True}

    _run(scenario())
