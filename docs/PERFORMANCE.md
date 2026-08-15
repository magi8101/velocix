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
