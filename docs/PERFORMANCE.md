# Performance

Measured on a 12-vCPU shared dev box, Python 3.13, single node, keep-alive.
All numbers below are real measurements, not claims. The framework previously
claimed "681K req/s" — that was fabricated and removed; nothing here comes
close to that number, and nothing here is invented.

## How fast is it

### Framework floor (in-process, no sockets)

The pure framework cost — routing, path/query parsing, dependency resolution,
response building, orjson serialization — with the ASGI server removed:

| Route | req/s | per-request |
|---|---|---|
| `GET /users/42?limit=5` (path + query params) | **~163K** | ~6.1 µs |
| `GET /items` (7.9 KB JSON body) | **~51K** | ~19.7 µs |

### Live over real HTTP

| Server | `/users` | `/items` |
|---|---|---|
| uvicorn (Python ASGI), 4 workers | ~22K req/s | ~21K req/s |
| **granian** (Rust ASGI), 4 workers | **~121K req/s** | **~92K req/s** |

### vs other frameworks (same box, granian 4 workers, identical routes, byte-identical responses)

| Route | Velocix | Starlette | FastAPI |
|---|---|---|---|
| `GET /users/42?limit=5` | ~121K | ~80K | ~25K |
| `POST /orders` (validated body) | ~80K | ~67K | ~34K |
| `GET /items` (7.9 KB, 100 items) | ~92K | ~32K | ~4.7K |
| `GET /slow` (5 ms simulated I/O) | ~17.5K | ~17.5K | ~17.8K |

Key findings from that comparison:

- **Real I/O erases everything.** With a 5 ms await, all three frameworks hit
  the same ~17.5K ceiling (100 concurrent ÷ 5 ms). The framework floor only
  matters for cheap handlers.
- **Velocix ≈ Starlette on tiny payloads, 2.3× faster on large ones.** The gap
  is orjson (Rust) vs stdlib `json.dumps` (pure Python) — it only shows when
  serialization actually costs something.
- **FastAPI's tax scales with validation + payload size:** 1.4× slower on a
  tiny echo, up to **16.5× slower on list serialization** (4.7K vs 92K req/s).
  Its `jsonable_encoder` pre-pass walks every value of every response
  (~500 µs on a 7.9 KB payload) before serializing — measured directly.
  Setting `response_model=None` does **not** skip it in FastAPI 0.115+;
  only returning a `Response` directly does.

## Where the per-request time goes

### Live granian split (1 worker, instrumented in-app)

Measured by timing the ASGI call from inside the app and comparing against the
total request time from `ab`:

| Route | Total | Python side (Velocix + glue) | Granian Rust (HTTP/socket) |
|---|---|---|---|
| `/users` | ~21.5 µs | **~13.1 µs (61%)** | ~8.4 µs |
| `/items` | ~36.2 µs | **~20.3 µs (56%)** | ~16.0 µs |

The framework itself is the majority of every request — not the server.
Granian's Rust side is mostly the inherent cost of serving HTTP (parse,
socket I/O, response write); the only part a custom runtime could reclaim is
the ASGI bridge (scope dict building, header re-parsing, message protocol),
which is a small slice of that 8–16 µs.

### Velocix's own hot path (in-process profile)

After optimization, `/users` (~6.1 µs) is roughly: handler body + query
parsing + `Request.__init__` + response building. `/items` (~19.7 µs) is
dominated by orjson serializing the 7.9 KB body (Rust, ~11 µs of it) plus
response construction.

## Optimization history

Every entry below is a code change followed by a measured before/after.
Rounds are chronological (each round's "before" is the previous round's
"after"). Unless a row says otherwise, every **live** number below is
granian (Rust ASGI), 4 workers, `c=100`, best of 3 — *not* the uvicorn
row in the table above. The uvicorn 22K figure is only shown once, as a
server comparison; it is not the baseline for any round delta.

### Round 1 — dependency resolution plan + fast query parsing

- `resolve_dependencies` now precomputes a per-handler resolution plan once
  and caches it. Handlers with no parameters (or only `request`) skip all
  per-request signature work; the Depends cache is initialized lazily.
  Before, every request ran `_get_signature` + `_get_type_hints_cached`
  even for handlers with nothing to resolve.
- `Request.query_params` replaced stdlib `parse_qs` with
  `fast-query-parsers` (Rust). The parse itself went 7.5 µs → 1.7 µs (4.4×);
  first-value-wins behavior for duplicate keys is preserved.

| Test | Before | After |
|---|---|---|
| In-process `/users` | 62.5K req/s | 86.3K req/s (+38%) |
| In-process `/items` | 34.3K req/s | 40.0K req/s (+17%) |
| Live granian `/users` | 100.5K req/s | 114.3K req/s |
| Live granian `/items` | 76.2K req/s | 83.4K req/s |

### Round 2 — request/response hot path

- `Request.__init__` created a new class object per request
  (`type("State", (), {})()`); replaced with a module-level class.
- `Router.resolve` ran **twice** per request (once in `_process_request`,
  once in `_execute_handler`). Now resolved once and stashed on the request.
- `_send_response` decoded `raw_headers` (bytes) into a str dict via the
  `headers` property, then re-encoded it. Added `Response.asgi_headers()`
  which returns the already-encoded `raw_headers` directly when the str-dict
  view was never materialized or mutated (middleware header injection still
  works — it goes through the str-dict path).

| Test | Before | After |
|---|---|---|
| In-process `/users` | 86.3K req/s | **163K req/s** (≈2×) |
| In-process `/items` | 40.0K req/s | 50.9K req/s (+27%) |
| Live granian `/users` | 114.3K req/s | 120.9K req/s |
| Live granian `/items` | 83.4K req/s | 92.2K req/s |

### Round 3 — response-body cache (`@cache_response`)

Added an opt-in `@cache_response(ttl)` decorator that caches the
orjson-serialized body (the most expensive part of a JSON response), keyed by
method + path + query string, with TTL expiry. The cached value is the
pre-serialized bytes — cache hits skip the handler *and* orjson entirely
(`JSONResponse.from_body`). Only caches dict/JSON responses; opt-in per route,
so only handlers with request-independent output should use it.

| Test | Uncached | Cached |
|---|---|---|
| In-process `/items`-style (7.9 KB) | 48.5K req/s | **379K req/s (7.8×)** |
| Live granian `/items`-style, 4 workers | 85.9K req/s | **147.7K req/s (1.7×)** |

## wrk2 constant-rate benchmarks (6 frameworks)

Measured on a 12-vCPU shared box, Python 3.14, granian 4 workers, wrk2
(constant-rate mode, 10 s per run, 200 connections, 4 threads). Every
framework serves byte-identical payloads on identical routes — verified
by the harness before each run.

### /items — GET, 100-item JSON payload (~7.9 KB)

| Target rps | Metric | Velocix | Starlette | FastAPI | Falcon | BlackSheep | Litestar |
|---|---|---|---|---|---|---|---|
| 1,000 | p50 | **1.55 ms** | 1.99 ms | 2.45 ms | 2.01 ms | 1.76 ms | 1.68 ms |
| | p90 | **2.17 ms** | 4.07 ms | 3.80 ms | 5.27 ms | 2.48 ms | 2.35 ms |
| | p99 | **2.72 ms** | 7.72 ms | 5.45 ms | 9.67 ms | 3.16 ms | 2.98 ms |
| 2,000 | p50 | **1.29 ms** | 1.82 ms | 2.08 ms | 1.85 ms | 1.75 ms | 2.22 ms |
| | p99 | **2.48 ms** | 5.83 ms | 5.22 ms | 6.59 ms | 6.04 ms | 7.23 ms |
| 5,000 | p50 | **1.14 ms** | 1.39 ms | 17.66 ms | 2.54 ms | 2.62 ms | 1.44 ms |
| | p99 | **2.39 ms** | 3.51 ms | 234.75 ms | 7.95 ms | 9.87 ms | 3.22 ms |

FastAPI's p50 collapses to 17.66 ms at 5K rps — its `jsonable_encoder` +
pydantic validation chain cannot keep up. Velocix and Litestar stay flat.

### /users/42 — GET, path param + int conversion

| Target rps | Metric | Velocix | Starlette | FastAPI | Falcon | BlackSheep | Litestar |
|---|---|---|---|---|---|---|---|
| 1,000 | p50 | 1.63 ms | 2.15 ms | 2.21 ms | **1.51 ms** | 1.54 ms | 1.65 ms |
| | p99 | 4.24 ms | 5.68 ms | 8.84 ms | **2.69 ms** | 2.68 ms | 2.89 ms |
| 2,000 | p50 | 1.60 ms | 1.38 ms | 1.78 ms | 1.61 ms | **1.32 ms** | 1.50 ms |
| | p99 | 3.81 ms | 2.60 ms | 3.62 ms | 4.47 ms | **2.44 ms** | 2.76 ms |
| 5,000 | p50 | **1.17 ms** | 1.18 ms | 1.31 ms | 2.08 ms | 1.63 ms | 1.60 ms |
| | p99 | **2.40 ms** | 2.54 ms | 3.70 ms | 5.89 ms | 3.85 ms | 5.16 ms |

At low rates, Falcon and BlackSheep's simpler Request objects give them a
slight edge. Velocix reclaims the lead at 5K rps where framework overhead
dominates over per-request allocation.

### /orders — POST, JSON body parse + msgspec/pydantic validation

| Target rps | Metric | Velocix | Starlette | FastAPI | Falcon | BlackSheep | Litestar |
|---|---|---|---|---|---|---|---|
| 500 | p50 | 2.40 ms | 2.27 ms | 2.02 ms | **1.78 ms** | 2.31 ms | 1.98 ms |
| | p99 | 6.69 ms | 6.46 ms | 4.01 ms | **3.36 ms** | 7.10 ms | 3.83 ms |
| 1,000 | p50 | **1.53 ms** | 1.94 ms | 2.21 ms | 1.91 ms | 1.97 ms | 1.70 ms |
| | p99 | **2.74 ms** | 5.39 ms | 7.80 ms | 4.65 ms | 5.25 ms | 3.04 ms |
| 2,000 | p50 | 1.50 ms | 1.40 ms | 1.74 ms | **1.30 ms** | 1.54 ms | 1.84 ms |
| | p99 | 4.28 ms | 3.09 ms | 3.33 ms | **2.48 ms** | 3.02 ms | 6.99 ms |

### /slow — GET, 5 ms simulated I/O

| Metric | Velocix | Starlette | FastAPI | Falcon | BlackSheep | Litestar |
|---|---|---|---|---|---|---|
| p50 | 7.36 ms | 8.30 ms | 8.22 ms | 7.30 ms | **7.08 ms** | 9.44 ms |
| p99 | 10.06 ms | 11.81 ms | 13.61 ms | 10.45 ms | **8.69 ms** | 13.96 ms |

With I/O dominating, BlackSheep's lower per-request overhead edges ahead.
Velocix and Falcon are within noise. FastAPI and Litestar pay extra for
their middleware/dependency machinery even on handlers that don't use it.

### Summary

- Velocix leads or ties p50 on `/items` (all rates), `/orders` at 1K rps,
  and `/users` at 5K rps. Its orjson + msgspec pipeline gives it the
  tightest tail on large-payload routes.
- BlackSheep and Falcon beat Velocix on small-payload `/users/42` at low
  rates — their Request construction is lighter. The gap vanishes at 5K rps.
- FastAPI's validation chain causes a p99 collapse at high rates on
  large payloads (234 ms at 5K rps on `/items`).
- I/O-bound routes erase all framework differences.

## What is NOT worth doing (yet)

Based on profiles, not vibes:

- **Struct/traits conversion of framework classes.** Allocation and class
  mechanics did not show up in any profile. The microseconds are in
  dependency resolution (fixed), query parsing (fixed), and serialization
  (already Rust).
- **A Rust router extension.** `route_cache` already makes hot-path route
  resolution effectively O(1); the remaining ~1 µs is not the bottleneck.
- **SIMD inside the framework.** Python has no SIMD; the SIMD-able work
  (JSON, HTTP parsing, query parsing, validation) is already delegated to
  native libraries (orjson, httptools, fast-query-parsers, msgspec, granian).
- **A custom ASGI runtime.** Granian (Rust) already does the HTTP work; the
  Python side of the request is 56–61% framework cost, which a new server
  would not touch. If the ASGI bridge ever matters, a PyO3 typed bridge
  (skip scope-dict round-trips) is the cheaper middle path.
- **Interpreter-level JIT.** The CPython 3.13 experimental JIT showed no
  measurable gain on this workload and the remaining pure-Python cost is
  already small.

## Head-to-Head: Velocix vs Starlette (direct ASGI)

Measured with direct ASGI calls (no HTTP server), same payloads, same routes.
Starlette's cost comes from: regex routing per request, unconditional Request
creation, `jsonable_encoder` + `json.dumps` for responses.

| Route | Velocix | Starlette | Speedup |
|---|---|---|---|
| `/users/{id}` (path + query) | 4,237 ns | 14,140 ns | **3.3x** |
| `/items` (7.9 KB JSON) | 15,943 ns | 65,656 ns | **4.1x** |
| `/orders` (POST + validation) | 5,179 ns | 13,468 ns | **2.6x** |

Where Velocix's time goes vs Starlette's:
- Routing: cache hit ~160ns vs regex+dict ~4,500ns
- Request: lazy (0ns if unused) vs unconditional ~1,700ns
- Response: orjson ~2,500ns vs jsonable_encoder+json.dumps ~12,000ns

## wrk2 Benchmark Harness

The `benchmarks/bench_compare/` directory contains a wrk2-based harness for
fixed-rate latency measurement across 7 frameworks.

```bash
# Run full battery: all frameworks, all routes, both rates
bash benchmarks/bench_compare/run_wrk2_all.sh

# Run single framework
bash benchmarks/bench_compare/run_wrk2.sh velocix GET /users/42?limit=5 1000 3
```

Results (granian 4 workers, R=1000, best of 3):

| Route | Framework | p50 | p99.9 |
|---|---|---|---|
| `/users` | Velocix | 1.63 ms | 7.15 ms |
| `/users` | Starlette | 1.98 ms | 18.45 ms |
| `/orders` POST | Velocix | 1.70 ms | 3.32 ms |
| `/items` | Velocix | 1.85 ms | 2.59 ms |

## Reproducing

The bench apps, load runners, and profiler harnesses used for these numbers
live in the repo's `benchmarks/` directory (when packaged). Standard recipe:

```bash
# in-process framework floor
python3 benchmarks/profile_inproc.py

# live granian (4 workers, c=100, best of 3)
bash benchmarks/run_granian.sh

# per-request Python vs server split (requires sudo for py-spy attach)
bash benchmarks/run_split.sh
```
