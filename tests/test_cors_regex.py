"""Tests for CORSMiddleware allow_origin_regex.

Covers: regex match/mismatch, compiled pattern, combined with an
allow_origins list, credentials flag, and OPTIONS preflight.
"""

import asyncio
import re
from functools import partial

from velocix import CORSMiddleware, TestClient, Velocix


def _run(coro):
    return asyncio.run(coro)


def _app(**cors_kwargs):
    app = Velocix()

    @app.get("/ping")
    async def ping(request):
        return {"pong": True}

    @app.route("/ping", methods={"OPTIONS"})
    async def ping_options(request):
        return {}

    app.add_middleware(partial(CORSMiddleware, **cors_kwargs))
    return app


def test_origin_matching_regex_allowed():
    app = _app(allow_origins=[], allow_origin_regex=r"https://.*\.example\.com")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping", headers={"Origin": "https://app.example.com"})
            assert resp.status_code == 200
            assert resp.headers["access-control-allow-origin"] == "https://app.example.com"

    _run(scenario())


def test_origin_not_matching_regex_blocked():
    app = _app(allow_origins=[], allow_origin_regex=r"https://.*\.example\.com")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping", headers={"Origin": "https://evil.com"})
            assert resp.status_code == 200
            assert "access-control-allow-origin" not in resp.headers

    _run(scenario())


def test_compiled_pattern_accepted():
    app = _app(allow_origins=[], allow_origin_regex=re.compile(r"^https://(app|api)\.example\.com$"))

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping", headers={"Origin": "https://api.example.com"})
            assert resp.headers["access-control-allow-origin"] == "https://api.example.com"
            blocked = await client.get("/ping", headers={"Origin": "https://cdn.example.com"})
            assert "access-control-allow-origin" not in blocked.headers

    _run(scenario())


def test_regex_combined_with_allow_origins():
    app = _app(
        allow_origins=["https://trusted.example.com"],
        allow_origin_regex=r"https://.*\.example\.net",
    )

    async def scenario():
        async with TestClient(app) as client:
            by_list = await client.get("/ping", headers={"Origin": "https://trusted.example.com"})
            assert by_list.headers["access-control-allow-origin"] == "https://trusted.example.com"
            by_regex = await client.get("/ping", headers={"Origin": "https://x.example.net"})
            assert by_regex.headers["access-control-allow-origin"] == "https://x.example.net"
            blocked = await client.get("/ping", headers={"Origin": "https://evil.com"})
            assert "access-control-allow-origin" not in blocked.headers

    _run(scenario())


def test_credentials_header_with_regex_match():
    app = _app(
        allow_origins=[],
        allow_origin_regex=r"https://.*\.example\.com",
        allow_credentials=True,
    )

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.get("/ping", headers={"Origin": "https://app.example.com"})
            assert resp.headers["access-control-allow-origin"] == "https://app.example.com"
            assert resp.headers["access-control-allow-credentials"] == "true"

    _run(scenario())


def test_preflight_options_with_regex():
    app = _app(allow_origins=[], allow_origin_regex=r"https://.*\.example\.com")

    async def scenario():
        async with TestClient(app) as client:
            resp = await client.request(
                "OPTIONS", "/ping", headers={"Origin": "https://app.example.com"}
            )
            assert resp.status_code == 204
            assert resp.headers["access-control-allow-origin"] == "https://app.example.com"
            assert "access-control-allow-methods" in resp.headers

    _run(scenario())
