import asyncio

import msgspec

from velocix import TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


class UserOut(msgspec.Struct):
    name: str
    email: str
    password: str
    age: int = 0
    role: str = "user"


class UserWithDefaults(msgspec.Struct):
    name: str
    bio: str | None = None
    tags: list[str] = msgspec.field(default_factory=list)
    score: int = 0


class Renamed(msgspec.Struct, rename="camel"):
    first_name: str
    last_name: str
    secret_key: str


def test_exclude_on_post_route():
    app = Velocix()

    @app.post("/users", response_model=UserOut, response_model_exclude={"password"})
    async def create():
        return {"name": "alice", "email": "a@b.com", "password": "secret", "age": 30, "role": "admin"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/users")
            body = msgspec.json.decode(resp.body)
            assert "password" not in body
            assert body["name"] == "alice"
            assert body["role"] == "admin"

    _run(scenario())


def test_include_on_post_route():
    app = Velocix()

    @app.post("/users", response_model=UserOut, response_model_include={"name"})
    async def create():
        return {"name": "alice", "email": "a@b.com", "password": "secret"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.post("/users")
            body = msgspec.json.decode(resp.body)
            assert set(body.keys()) == {"name"}

    _run(scenario())


def test_exclude_none_on_struct_return():
    app = Velocix()

    @app.get("/user", response_model=UserWithDefaults, response_model_exclude_none=True)
    async def get_user():
        return UserWithDefaults(name="alice", bio=None, tags=["a"])

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert "bio" not in body
            assert body["name"] == "alice"
            assert body["tags"] == ["a"]

    _run(scenario())


def test_exclude_defaults_non_matching():
    app = Velocix()

    @app.get("/user", response_model=UserWithDefaults, response_model_exclude_defaults=True)
    async def get_user():
        return {"name": "alice", "bio": "hello", "tags": ["x"], "score": 42}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {"name": "alice", "bio": "hello", "tags": ["x"], "score": 42}

    _run(scenario())


def test_exclude_all_fields():
    app = Velocix()

    @app.get(
        "/user",
        response_model=UserOut,
        response_model_include={"name"},
        response_model_exclude={"name"},
    )

    async def get_user():
        return {"name": "alice", "email": "a@b.com", "password": "x"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {}

    _run(scenario())


def test_empty_include_set_no_filter_built():
    app = Velocix()

    @app.get("/user", response_model=UserOut, response_model_include=set())
    async def get_user():
        return {"name": "alice", "email": "a@b.com", "password": "x"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            assert resp.status_code == 200
            body = msgspec.json.decode(resp.body)
            assert body["name"] == "alice"

    _run(scenario())


def test_empty_exclude_set_keeps_everything():
    app = Velocix()

    @app.get("/user", response_model=UserOut, response_model_exclude=set())
    async def get_user():
        return {"name": "alice", "email": "a@b.com", "password": "x", "age": 30, "role": "admin"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body["name"] == "alice"
            assert body["password"] == "x"

    _run(scenario())


def test_exclude_with_rename_on_all_fields():
    app = Velocix()

    @app.get(
        "/user",
        response_model=Renamed,
        response_model_exclude={"first_name", "last_name", "secret_key"},
    )
    async def get_user():
        return {"first_name": "alice", "last_name": "smith", "secret_key": "x"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {}

    _run(scenario())


def test_combined_exclude_and_exclude_none():
    app = Velocix()

    @app.get(
        "/user",
        response_model=UserWithDefaults,
        response_model_exclude={"score"},
        response_model_exclude_none=True,
    )
    async def get_user():
        return {"name": "alice", "bio": None, "tags": [], "score": 0}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {"name": "alice", "tags": []}

    _run(scenario())


def test_combined_exclude_and_exclude_defaults():
    app = Velocix()

    @app.get(
        "/user",
        response_model=UserWithDefaults,
        response_model_exclude={"name"},
        response_model_exclude_defaults=True,
    )
    async def get_user():
        return {"name": "alice", "bio": None, "tags": [], "score": 0}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {}

    _run(scenario())


def test_exclude_on_delete_route():
    app = Velocix()

    @app.delete(
        "/users/{user_id}",
        response_model=UserOut,
        response_model_exclude={"password"},
    )
    async def delete_user(user_id: int):
        return {"name": "alice", "email": "a@b.com", "password": "secret", "age": 30, "role": "admin"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.delete("/users/1")
            body = msgspec.json.decode(resp.body)
            assert "password" not in body

    _run(scenario())


def test_exclude_on_patch_route():
    app = Velocix()

    @app.patch(
        "/users/{user_id}",
        response_model=UserOut,
        response_model_exclude={"email", "password"},
    )
    async def update_user(user_id: int):
        return {"name": "alice", "email": "a@b.com", "password": "secret", "age": 30, "role": "admin"}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.patch("/users/1")
            body = msgspec.json.decode(resp.body)
            assert "email" not in body
            assert "password" not in body
            assert body["name"] == "alice"

    _run(scenario())


def test_exclude_none_does_not_affect_non_none_values():
    app = Velocix()

    @app.get(
        "/user",
        response_model=UserWithDefaults,
        response_model_exclude_none=True,
    )
    async def get_user():
        return {"name": "alice", "bio": "hello", "tags": [], "score": 0}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {"name": "alice", "bio": "hello", "tags": [], "score": 0}

    _run(scenario())


def test_exclude_with_empty_dict_return():
    app = Velocix()

    @app.get("/user", response_model=UserOut, response_model_exclude={"password"})
    async def get_user():
        return {}

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            body = msgspec.json.decode(resp.body)
            assert body == {}

    _run(scenario())


def test_exclude_with_none_return():
    app = Velocix()

    @app.get("/user", response_model=UserOut, response_model_exclude={"password"})
    async def get_user():
        return None

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/user")
            assert resp.status_code == 204

    _run(scenario())


def test_exclude_with_list_return():
    app = Velocix()

    class Item(msgspec.Struct):
        id: int
        name: str

    @app.get("/items", response_model=list[Item])
    async def list_items():
        return [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/items")
            body = msgspec.json.decode(resp.body)
            assert len(body) == 2
            assert body[0]["id"] == 1

    _run(scenario())


def test_unknown_field_in_include_raises():
    import pytest

    app = Velocix()

    with pytest.raises(ValueError, match="unknown field"):

        @app.get("/user", response_model=UserOut, response_model_include={"typo_field"})
        async def get_user():
            return {}

    _run(asyncio.sleep(0))


def test_exclude_and_include_together_validate_fields():
    import pytest

    app = Velocix()

    with pytest.raises(ValueError, match="unknown field"):

        @app.get(
            "/user",
            response_model=UserOut,
            response_model_include={"name"},
            response_model_exclude={"nonexistent"},
        )
        async def get_user():
            return {}

    _run(asyncio.sleep(0))
