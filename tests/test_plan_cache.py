"""Regression tests for the id()-keyed dependency-plan caches.

After a handler is garbage collected, CPython can hand its id() to a new
handler. The plan caches used to key purely on id(), so a fresh handler
could inherit a dead handler's plan — including a stale response-cache TTL
and wrong parameter injection. Entries now pin the callable and re-check
identity, so a recycled id() is never trusted.
"""

import asyncio

from velocix import TestClient, Velocix, cache_response
from velocix.core import depends


def test_stale_plan_cache_entry_is_never_reused():
    """A cache entry whose stored handler is not the current one is rebuilt."""

    async def handler_a(request):
        return {"a": 1}

    async def handler_b(request):
        return {"b": 2}

    # Plant a stale entry for handler_b's id pointing at handler_a's plan
    # (simulates the id()-recycling scenario deterministically).
    depends._plan_cache[id(handler_b)] = (
        handler_a,
        ((("request", "request", None),), True, 60.0, 1, 201, None, None, None),
    )

    (
        plan,
        needs_request,
        cache_ttl,
        call_mode,
        status_code,
        response_model,
        response_class,
        response_filter,
    ) = depends.get_plan_and_needs_request(handler_b)
    assert cache_ttl is None  # rebuilt from handler_b, not the stale entry
    assert status_code is None
    assert response_model is None
    assert response_filter is None
    assert response_class is None
    assert plan == (("request", "request", None),)


def test_repeated_plan_build_hits_cache():
    """A second resolution for the same handler must not rebuild.

    Regression: the plan-build loop was once dedented out of the cache-miss
    branch, so a second call for the same handler hit the cache and crashed
    on an undefined variable.
    """

    async def handler(request, user_id: int):
        return {"user_id": user_id}

    plan1 = depends.get_resolution_plan(handler)
    plan2 = depends.get_resolution_plan(handler)
    assert plan1 == plan2 == (("request", "request", None), ("user_id", "path", (int, depends._NO_DEFAULT)))


def _cached_app(ttl: float = 60.0):
    app = Velocix()

    @app.get("/cached")
    @cache_response(ttl=ttl)
    async def cached(request):
        return {"value": 42}

    @app.get("/uncached")
    async def uncached(request):
        return {"value": 7}

    return app


async def _get(app, path):
    async with TestClient(app) as client:
        return await client.get(path)


def test_end_to_end_id_reuse_never_leaks_stale_ttl():
    """Create + destroy cached handlers to force id() recycling, then verify a
    fresh uncached handler never inherits a stale cached plan."""

    for _ in range(6):
        app = _cached_app(60.0)
        asyncio.run(_get(app, "/cached"))
        del app

    app = _cached_app()
    response = asyncio.run(_get(app, "/uncached"))
    assert response.status_code == 200
    assert "etag" not in response.headers
