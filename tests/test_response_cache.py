"""Tests for ETag / If-None-Match conditional caching on @cache_response routes.

Covers: etag + cache-control presence, 304 on exact/wildcard/list matches,
200 on mismatch, no etag on uncached routes, and TTL expiry repopulation.
"""

import asyncio

from velocix import TestClient, Velocix, cache_response


def _run(coro):
    return asyncio.run(coro)


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


def test_cached_response_carries_etag_and_cache_control():
    app = _cached_app()

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.get("/cached")
            assert r1.status_code == 200
            assert r1.headers["etag"].startswith('"')
            assert r1.headers["etag"].endswith('"')
            assert "max-age=60" in r1.headers["cache-control"]
            # repeat hit reuses the stored body + etag
            r2 = await client.get("/cached")
            assert r2.json() == {"value": 42}
            assert r2.headers["etag"] == r1.headers["etag"]

    _run(scenario())


def test_matching_if_none_match_returns_304():
    app = _cached_app()

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.get("/cached")
            etag = r1.headers["etag"]
            r2 = await client.get("/cached", headers={"If-None-Match": etag})
            assert r2.status_code == 304
            assert r2.body == b""
            assert r2.headers["etag"] == etag

    _run(scenario())


def test_non_matching_if_none_match_returns_full_body():
    app = _cached_app()

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/cached")
            r2 = await client.get("/cached", headers={"If-None-Match": '"deadbeef"'})
            assert r2.status_code == 200
            assert r2.json() == {"value": 42}

    _run(scenario())


def test_wildcard_if_none_match_returns_304():
    app = _cached_app()

    async def scenario():
        async with TestClient(app) as client:
            await client.get("/cached")
            r2 = await client.get("/cached", headers={"If-None-Match": "*"})
            assert r2.status_code == 304
            assert r2.body == b""

    _run(scenario())


def test_if_none_match_list_matches():
    app = _cached_app()

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.get("/cached")
            etag = r1.headers["etag"]
            r2 = await client.get(
                "/cached", headers={"If-None-Match": f'"aaa", "bbb", {etag}'}
            )
            assert r2.status_code == 304

    _run(scenario())


def test_uncached_route_has_no_etag():
    app = _cached_app()

    async def scenario():
        async with TestClient(app) as client:
            r = await client.get("/uncached")
            assert r.status_code == 200
            assert r.json() == {"value": 7}
            assert "etag" not in r.headers
            assert "cache-control" not in r.headers

    _run(scenario())


def test_cache_expiry_repopulates():
    app = _cached_app(ttl=0.1)

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.get("/cached")
            assert r1.status_code == 200
            await asyncio.sleep(0.15)
            r2 = await client.get("/cached")
            assert r2.status_code == 200
            assert r2.json() == {"value": 42}
            assert "etag" in r2.headers

    _run(scenario())


def test_304_not_returned_for_post():
    app = Velocix()

    @app.post("/cached")
    @cache_response(ttl=60)
    async def cached(request):
        return {"value": 42}

    async def scenario():
        async with TestClient(app) as client:
            r1 = await client.post("/cached")
            etag = r1.headers["etag"]
            r2 = await client.post("/cached", headers={"If-None-Match": etag})
            # conditional semantics are GET/HEAD-only; POST always re-serves
            assert r2.status_code == 200
            assert r2.json() == {"value": 42}

    _run(scenario())
