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

### Round 4 — positional dispatch (call_mode 4)

Added a fast dispatch path for handlers whose signature is only `(request,
path_param)`. Instead of building a kwargs dict and splatting it with
`handler(**kwargs)`, call_mode 4 builds a positional tuple and calls
`handler(request, user_id)` directly. This uses CPython's vectorcall fast
path, skipping the dict allocation + keyword-name mapping.

Measured: kwargs path = 289 ns vs positional = 155 ns (46% reduction in
dispatch cost).

| Test | Before | After |
|---|---|---|
| In-process `/users` | ~163K req/s | ~175K req/s |
| wrk2 `/users` p99.9 (R=1000) | 14.48 ms | 3.38 ms |

### Round 5 — opt-in route metrics

Removed the per-request `RouteMetrics` chain from the router hot path.
`RouteMetrics` was never read anywhere in the codebase — `get_metrics()`
was dead code, and `__route_metrics__` was only written to, never read.

Per-request cost removed:
- `CachedRoute.cache_hits += 1` on every cache hit (attribute mutation)
- `time.time()` called 3x on dynamic route first hit (1 redundant)
- `RouteMetrics()` dataclass allocation on every unique dynamic route

| Test | Before | After |
|---|---|---|
| In-process `/users` interleaved A/B | 183K req/s | 194K req/s (+6%) |

### Round 6 — bounded response cache + header scan

Two fixes, both referenced from production frameworks:

1. **Bounded response cache** (pattern from Pallets/cachelib `SimpleCache._prune`):
   `_response_cache` was unbounded — every unique query string created a
   permanent entry. Added `_CACHE_MAX_SIZE` (1024) with eviction on insert:
   sweep expired first, then evict oldest if still over threshold.

2. **Linear scan for If-None-Match** (pattern from Starlette `Headers`):
   `_request_if_none_match` built a full `dict()` from scope headers just
   to do one `.get()`. Replaced with linear scan of the header list.
   Measured: 508ns dict vs 270ns linear at 15 headers (2x faster).

| Test | Before | After |
|---|---|---|
| In-process `/users` median | 4,714 ns | 4,237 ns (-10%) |
| In-process `/users` p99 | 6,467 ns | 5,654 ns (-12.6%) |

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
