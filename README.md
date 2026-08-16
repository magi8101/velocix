# Velocix

A high-performance ASGI web framework for Python with FastAPI-style ergonomics and a
Starlette-inspired core. Routing, parameter injection, validation, middleware, WebSockets,
OpenAPI, security, and testing utilities — built for measurable speed, not claims.

- Python 3.10+
- Runs on any ASGI server (granian, uvicorn, hypercorn)
- Zero runtime dependencies beyond the fast primitives: `orjson`, `msgspec`,
  `fast-query-parsers`, `xxhash`

---

## Features

**Routing**
- Static, dynamic (`/users/{user_id}`), and typed path params with constraint support
- Named routes and reverse routing: `request.url_for("user", user_id=42)`
- `include_router(router, prefix="/api")` and `app.mount("/static", StaticFiles(...))`
- `status_code=` and `response_model=` on route decorators

**Parameter injection**
- `Query`, `Header`, `Cookie`, `Form`, `File` markers — both `Annotated[...]` and classic
  `= Query(...)` styles
- Request-body binding to msgspec Structs with structured 422 errors
- `Depends` dependency injection with per-request caching

**HTTP**
- Response classes: `Response`, `JSONResponse`, `HTMLResponse`, `PlainTextResponse`,
  `StreamingResponse`, `FileResponse`, `EventStreamResponse` (SSE), `JSONLinesResponse`,
  `RedirectResponse`
- Background tasks run after the response is sent
- `@cache_response` with ETag / `If-None-Match` conditional requests and `Cache-Control`

**Middleware and security**
- `BaseMiddleware` + compiled middleware stack; `CORSMiddleware` (incl. `allow_origin_regex`),
  `TrustedHostMiddleware`, `GZipMiddleware`, `SecurityHeadersMiddleware`, `RequestIDMiddleware`,
  `RateLimitMiddleware`
- Signed session middleware (`SessionMiddleware`) with `request.session`
- JWT auth, password hashing, multipart uploads (`UploadFile`, `MultipartForm`)

**Protocols and tooling**
- WebSockets (text / bytes / JSON, both directions)
- OpenAPI 3.1 generation with Swagger and ReDoc
- `HTTPClient` (httpx-based), `TestClient`, health checks, Prometheus metrics
- Lifespan startup/shutdown handlers, custom exception handlers

---

## Installation

```bash
pip install velocix
```

Requires Python 3.10 or newer and an ASGI server:

```bash
pip install granian   # or: uvicorn, hypercorn
```

---

## Quick Start

```python
from typing import Annotated

from msgspec import Struct

from velocix import Query, TestClient, Velocix
from velocix.core.response import JSONResponse

app = Velocix()


@app.get("/")
async def hello() -> dict:
    return {"message": "Hello World"}


@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    limit: Annotated[int, Query()] = 10,
) -> dict:
    return {"user_id": user_id, "limit": limit}


class OrderIn(Struct):
    customer: str
    qty: int


@app.post("/orders", status_code=201)
async def create_order(order: OrderIn) -> dict:
    return {"customer": order.customer, "qty": order.qty}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
```

---

## Performance

All numbers are real measurements — see [docs/PERFORMANCE.md](docs/PERFORMANCE.md) for the
full methodology and [benchmarks/](benchmarks/) for the reproducible harness. Velocix serves
**byte-identical responses** to every framework compared, on the same routes, under the same
load, on the same box.

### Framework floor (in-process, no sockets)

The pure framework cost — routing, parsing, dependency resolution, serialization — with the
ASGI server removed. Measured on a 12-vCPU shared box, Python 3.13.

| Route | req/s | per-request |
|---|---|---|
| `GET /users/42?limit=5` (path + query params) | ~163K | ~6.1 µs |
| `GET /items` (7.9 KB JSON body) | ~51K | ~19.7 µs |

### Live over real HTTP (granian, 4 workers)

| Server | `/users` | `/items` |
|---|---|---|
| granian (Rust ASGI), 4 workers | ~121K req/s | ~92K req/s |
| uvicorn (Python ASGI), 4 workers | ~22K req/s | ~21K req/s |

### Cross-framework, live (granian 4 workers, identical routes, byte-identical responses)

| Route | Velocix | Starlette | FastAPI |
|---|---|---|---|
| `GET /users/42?limit=5` | ~121K | ~80K | ~25K |
| `POST /orders` (validated body) | ~80K | ~67K | ~34K |
| `GET /items` (7.9 KB, 100 items) | ~92K | ~32K | ~4.7K |
| `GET /slow` (5 ms simulated I/O) | ~17.5K | ~17.5K | ~17.8K |

The `/items` gap is `orjson` (Rust) vs stdlib `json.dumps`; FastAPI's tax scales with
validation and payload size (up to ~16x slower on list serialization, measured directly).
Real I/O erases everything: with a 5 ms await all frameworks hit the same concurrency
ceiling.

### Load test: 7 frameworks under Locust (benchmarks/bench_compare)

Saturation profile — 500 users, no think time, 45 s, 4 workers:

| Framework | rps | avg | fails |
|---|---|---|---|
| Velocix | 2,092 | 36.6 ms | 0 |
| Sanic | 2,082 | 37.1 ms | 0 |
| BlackSheep | 2,022 | 38.0 ms | 0 |
| Litestar | 1,903 | 40.3 ms | 0 |
| Starlette | 1,877 | 40.9 ms | 0 |
| Falcon | 1,844 | 41.7 ms | 0 |
| FastAPI | 1,812 | 42.5 ms | 0 |

Realistic profile — 100 users, think time 0.1-0.5 s, 60 s (client-throttled at ~318 rps;
latency is the differentiator): Sanic 2.6 ms, Velocix 3.0 ms, FastAPI 3.7 ms.

Single runs on a shared box: treat the ordering and margins as signal, exact rps as noise.
Re-run with `bash benchmarks/bench_compare/run_all.sh`.

---

## Code Structure

```
velocix/
├── core/           # ASGI app, router, request/response, dependencies, middleware
├── http/           # HTTP client, multipart parsing
├── security/       # JWT, password hashing, CORS, rate limiting
├── validation/     # msgspec-based validation
├── websocket/      # WebSocket support
├── openapi/        # OpenAPI 3.1 generation, Swagger / ReDoc
├── monitoring/     # Health checks and metrics
├── testing/        # TestClient
└── config/         # Configuration helpers
```

---

## Documentation

- [API Reference](docs/API_REFERENCE.md)
- [User Guide](docs/GUIDE.md)
- [Performance](docs/PERFORMANCE.md)
- [Security](docs/SECURITY.md)
- [Internals](docs/INTERNALS.md)

---

## License

MIT — see the [LICENSE](LICENSE) file.
