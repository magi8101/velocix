"""Measure the in-process framework floor (no sockets, no server).

Usage: python3 benchmarks/profile_inproc.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_velocix import app  # noqa: E402


async def bench(scope, n=20000):
    async def recv():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(msg):
        sent.append(msg)

    t0 = time.perf_counter()
    for _ in range(n):
        await app(scope, recv, send)
    dt = time.perf_counter() - t0
    return n / dt


def mk_scope(path, qs=""):
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": qs.encode(),
        "headers": [(b"host", b"127.0.0.1"), (b"user-agent", b"ab")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }


async def main():
    routes = [
        ("/users", mk_scope("/users/42", "limit=5")),
        ("/items", mk_scope("/items")),
    ]
    print("=== in-process ASGI loop (no sockets), req/s ===")
    for label, scope in routes:
        rps = await bench(scope)
        print(f"{label:8s} {rps:8.0f} req/s  ({1e6 / rps:.2f} us/request)")


asyncio.run(main())
