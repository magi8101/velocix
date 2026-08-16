"""Tests for Query/Header/Cookie parameter injection (FastAPI-style markers).

Covers: Annotated + classic marker styles, defaults/required/alias, type
conversion, plain params as path-or-query, header underscore conversion,
cookies, 422 on missing required params, Depends + query combos, and the
path-param regression.
"""

import asyncio
from typing import Annotated

from velocix import Cookie, Header, Query, TestClient, Velocix
from velocix.core.depends import Depends


def _run(coro):
    return asyncio.run(coro)


def test_query_with_default():
    app = Velocix()

    @app.get("/items")
    async def items(q: Annotated[str | None, Query()] = None):
        return {"q": q}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items")).json() == {"q": None}
            assert (await client.get("/items", params={"q": "x"})).json() == {"q": "x"}

    _run(scenario())


def test_query_required_missing_is_422():
    app = Velocix()

    @app.get("/items")
    async def items(q: Annotated[str, Query()]):
        return {"q": q}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items")).status_code == 422
            assert (await client.get("/items", params={"q": "x"})).json() == {"q": "x"}

    _run(scenario())


def test_classic_marker_style():
    app = Velocix()

    @app.get("/items")
    async def items(q: str | None = Query(None)):  # type: ignore[assignment]
        return {"q": q}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items")).json() == {"q": None}
            assert (await client.get("/items", params={"q": "x"})).json() == {"q": "x"}

    _run(scenario())


def test_query_type_conversion():
    app = Velocix()

    @app.get("/items")
    async def items(skip: Annotated[int, Query()] = 0, limit: Annotated[int, Query()] = 10):
        return {"skip": skip, "limit": limit}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items")).json() == {"skip": 0, "limit": 10}
            assert (await client.get("/items", params={"skip": "5", "limit": "20"})).json() == {
                "skip": 5,
                "limit": 20,
            }

    _run(scenario())


def test_query_alias():
    app = Velocix()

    @app.get("/items")
    async def items(search: Annotated[str | None, Query(alias="q")] = None):
        return {"search": search}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items", params={"q": "abc"})).json() == {"search": "abc"}
            # bare param name does not match the alias
            assert (await client.get("/items", params={"search": "abc"})).json() == {
                "search": None
            }

    _run(scenario())


def test_plain_param_default_is_query():
    app = Velocix()

    @app.get("/items")
    async def items(limit: int = 10):
        return {"limit": limit}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items")).json() == {"limit": 10}
            assert (await client.get("/items", params={"limit": "3"})).json() == {"limit": 3}

    _run(scenario())


def test_plain_param_in_path_is_path():
    app = Velocix()

    @app.get("/users/{user_id}")
    async def user(user_id: int):
        return {"user_id": user_id}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/users/42")).json() == {"user_id": 42}

    _run(scenario())


def test_plain_required_param_missing_is_422():
    app = Velocix()

    @app.get("/items")
    async def items(q: str):
        return {"q": q}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items")).status_code == 422
            assert (await client.get("/items", params={"q": "x"})).json() == {"q": "x"}

    _run(scenario())


def test_header_with_underscore_conversion():
    app = Velocix()

    @app.get("/secure")
    async def secure(x_token: Annotated[str | None, Header()] = None):
        return {"token": x_token}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/secure")).json() == {"token": None}
            assert (await client.get("/secure", headers={"X-Token": "abc"})).json() == {
                "token": "abc"
            }

    _run(scenario())


def test_header_required_missing_is_422():
    app = Velocix()

    @app.get("/secure")
    async def secure(x_api_key: Annotated[str, Header()]):
        return {"key": x_api_key}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/secure")).status_code == 422
            assert (await client.get("/secure", headers={"X-Api-Key": "k"})).json() == {"key": "k"}

    _run(scenario())


def test_header_alias_and_no_underscore_conversion():
    app = Velocix()

    @app.get("/raw")
    async def raw(x_token: Annotated[str | None, Header(alias="X-Token", convert_underscores=False)] = None):  # noqa: E501
        return {"token": x_token}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/raw", headers={"X-Token": "abc"})).json() == {
                "token": "abc"
            }
            assert (await client.get("/raw", headers={"X-Token": "abc", "x_token": "no"})).json() == {
                "token": "abc"
            }

    _run(scenario())


def test_cookie_with_default():
    app = Velocix()

    @app.get("/prefs")
    async def prefs(theme: Annotated[str, Cookie()] = "light"):
        return {"theme": theme}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/prefs")).json() == {"theme": "light"}
            assert (await client.get("/prefs", headers={"cookie": "theme=dark"})).json() == {
                "theme": "dark"
            }

    _run(scenario())


def test_cookie_required_missing_is_422():
    app = Velocix()

    @app.get("/prefs")
    async def prefs(theme: Annotated[str, Cookie()]):
        return {"theme": theme}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/prefs")).status_code == 422
            assert (await client.get("/prefs", headers={"cookie": "theme=dark"})).json() == {
                "theme": "dark"
            }

    _run(scenario())


def test_depends_with_query_param():
    app = Velocix()

    async def get_prefix(request):
        return "v1"

    @app.get("/items")
    async def items(q: Annotated[str | None, Query()] = None, prefix: str = Depends(get_prefix)):  # type: ignore[assignment]
        return {"q": q, "prefix": prefix}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/items", params={"q": "x"})).json() == {
                "q": "x",
                "prefix": "v1",
            }

    _run(scenario())


def test_path_param_with_request_still_works():
    app = Velocix()

    @app.get("/users/{user_id}")
    async def user(user_id: int, request):
        return {"user_id": user_id, "path": request.path}

    async def scenario():
        async with TestClient(app) as client:
            assert (await client.get("/users/7")).json() == {
                "user_id": 7,
                "path": "/users/7",
            }

    _run(scenario())
