import pytest
import msgspec

from velocix import Velocix, TestClient


class UserOut(msgspec.Struct):
    name: str
    email: str
    password: str
    age: int = 0


class UserWithDefault(msgspec.Struct):
    name: str
    email: str | None = None
    groups: list[str] = msgspec.field(default_factory=list)


class UserRenamed(msgspec.Struct, rename="camel"):
    first_name: str
    email_address: str
    secret: str


async def _get(app, path, **kwargs):
    async with TestClient(app) as client:
        return await client.get(path, **kwargs)


async def _post(app, path, json=None, **kwargs):
    async with TestClient(app) as client:
        return await client.post(path, json=json, **kwargs)


def test_exclude_fields():
    app = Velocix()

    @app.get("/users", response_model=UserOut, response_model_exclude={"password"})
    async def list_users():
        return {"name": "alice", "email": "a@b.com", "password": "secret", "age": 30}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert "password" not in body
    assert body["name"] == "alice"
    assert body["email"] == "a@b.com"


def test_include_fields():
    app = Velocix()

    @app.get("/users", response_model=UserOut, response_model_include={"name", "email"})
    async def list_users():
        return {"name": "alice", "email": "a@b.com", "password": "secret", "age": 30}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert set(body.keys()) == {"name", "email"}


def test_exclude_none():
    app = Velocix()

    @app.get("/users", response_model=UserWithDefault, response_model_exclude_none=True)
    async def get_user():
        return {"name": "alice", "email": None, "groups": []}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert "email" not in body
    assert body["name"] == "alice"
    assert body["groups"] == []


def test_exclude_defaults():
    app = Velocix()

    @app.get(
        "/users",
        response_model=UserWithDefault,
        response_model_exclude_defaults=True,
    )
    async def get_user():
        return {"name": "alice", "email": None, "groups": []}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert body == {"name": "alice"}


def test_exclude_unset():
    app = Velocix()

    @app.get(
        "/users",
        response_model=UserWithDefault,
        response_model_exclude_unset=True,
    )
    async def get_user():
        return {"name": "alice", "email": "a@b.com"}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert body == {"name": "alice", "email": "a@b.com"}


def test_rename_preserving_exclude():
    app = Velocix()

    @app.get(
        "/users",
        response_model=UserRenamed,
        response_model_exclude={"secret"},
    )
    async def get_user():
        return {"first_name": "alice", "email_address": "a@b.com", "secret": "x"}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert "secret" not in body
    assert "first_name" not in body
    assert "firstName" in body
    assert "emailAddress" in body


def test_unknown_field_in_exclude_raises():
    app = Velocix()

    with pytest.raises(ValueError, match="unknown field"):

        @app.get(
            "/users",
            response_model=UserOut,
            response_model_exclude={"nonexistent"},
        )
        async def list_users():
            return {}


def test_no_filter_fast_path():
    app = Velocix()

    @app.get("/users", response_model=UserOut)
    async def list_users():
        return {"name": "alice", "email": "a@b.com", "password": "secret", "age": 30}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert body["password"] == "secret"


def test_whitelist_drops_extra_fields():
    app = Velocix()

    @app.get("/users", response_model=UserOut)
    async def list_users():
        return {
            "name": "alice",
            "email": "a@b.com",
            "password": "secret",
            "age": 30,
            "sensitive_token": "should_not_appear",
        }

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert "sensitive_token" not in body
    assert body["password"] == "secret"


def test_exclude_with_struct_return():
    app = Velocix()

    @app.get("/users", response_model=UserOut, response_model_exclude={"password"})
    async def get_user():
        return UserOut(name="alice", email="a@b.com", password="secret", age=30)

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert "password" not in body
    assert body["name"] == "alice"


def test_combined_include_and_exclude_none():
    app = Velocix()

    @app.get(
        "/users",
        response_model=UserWithDefault,
        response_model_include={"name", "email", "groups"},
        response_model_exclude_none=True,
    )
    async def get_user():
        return {"name": "alice", "email": None, "groups": ["admin"]}

    resp = asyncio_run(_get(app, "/users"))
    assert resp.status_code == 200
    body = msgspec.json.decode(resp.body)
    assert set(body.keys()) == {"name", "groups"}


import asyncio


def asyncio_run(coro):
    return asyncio.run(coro)
