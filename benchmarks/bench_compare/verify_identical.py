import asyncio
import sys

sys.path.insert(0, ".")

MODS = ["bench_velocix", "bench_starlette", "bench_fastapi", "bench_litestar", "bench_falcon", "bench_blacksheep"]


async def call(app, method, path, body=None):
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path.split("?")[0],
        "raw_path": path.split("?")[0].encode(),
        "query_string": path.split("?")[1].encode() if "?" in path else b"",
        "root_path": "",
        "headers": [(b"host", b"localhost"), (b"content-type", b"application/json")] if body else [(b"host", b"localhost")],
        "client": ("127.0.0.1", 1234),
        "server": ("127.0.0.1", 8000),
    }
    received = []

    async def send(msg):
        if msg["type"] == "http.response.start":
            received.append(("start", msg["status"], tuple(msg["headers"])))
        elif msg["type"] == "http.response.body":
            received.append(("body", msg.get("body", b"")))

    async def recv():
        if body is not None:
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.request", "body": b"", "more_body": False}

    try:
        await app(scope, recv, send)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    status = next((s[1] for s in received if s[0] == "start"), None)
    body_bytes = b"".join(s[1] for s in received if s[0] == "body")
    return status, body_bytes


async def main():
    apps = {}
    for m in MODS:
        try:
            mod = __import__(m)
            apps[m] = mod.app
        except Exception as e:
            print(f"{m:20s} IMPORT FAIL: {type(e).__name__}: {e}")
            return

    cases = [
        ("GET", "/users/42?limit=3"),
        ("GET", "/items"),
        ("GET", "/slow"),
        ("POST", "/orders", b'{"customer":"Acme Corp","items":[{"sku":"SKU-0001","qty":2,"price":1.25},{"sku":"SKU-0002","qty":5,"price":3.75}]}'),
    ]
    results = {c[1]: {} for c in cases}
    for m, app in apps.items():
        for c in cases:
            body = c[2] if len(c) > 2 else None
            r = await call(app, c[0], c[1], body)
            results[c[1]][m] = r

    ok = True
    for path, res in results.items():
        base = None
        for m in MODS:
            v = res[m]
            if isinstance(v, str):
                print(f"{path:60s} {m:20s} {v}")
                ok = False
                continue
            if base is None:
                base = (v[0], v[1])
                print(f"{path:60s} {m:20s} status={v[0]} len={len(v[1])}")
            elif v != base:
                print(f"{path:60s} {m:20s} MISMATCH status={v[0]} len={len(v[1])} vs base {base[0]}/{len(base[1])}")
                ok = False
            else:
                print(f"{path:60s} {m:20s} status={v[0]} len={len(v[1])} (match)")
    print("\nALL BYTE-IDENTICAL" if ok else "\nMISMATCHES FOUND")


asyncio.run(main())
