# Velocix Runtime (Design)

Status: **design document, not implemented.** Nothing in this file is a shipped
capability. Measured facts are cited from `docs/PERFORMANCE.md`; everything
else is a target or a plan, and labeled as such.

This document plans a custom HTTP runtime for Velocix — a Rust engine that
embeds CPython, replaces granian/uvicorn as the server, and speaks a
Velocix-native protocol instead of ASGI. It exists because the measurements in
`docs/PERFORMANCE.md` show the framework is the majority of every cheap
request, and part of that cost is the ASGI bridge itself.

---

## Why this project exists (measured)

From `docs/PERFORMANCE.md` — live granian, 1 worker, in-app timing:

| Route | Total | Python side (Velocix + glue) | Granian Rust (HTTP/socket) |
|---|---|---|---|
| `/users` | ~21.5 µs | ~13.1 µs (61%) | ~8.4 µs |
| `/items` | ~36.2 µs | ~20.3 µs (56%) | ~16.0 µs |

The framework is the majority of every request. But most of that 13–20 µs is
Velocix's own work (resolution, glue, serialization) — work a new server does
not touch. The only part a runtime can reclaim is the **ASGI bridge**: the
round-trips between the server's Rust side and the Python side.

### What the ASGI bridge costs

Today, per request:

1. granian parses HTTP in Rust, then **builds a generic scope dict** (method,
   path, headers as bytes tuples, query string, etc.)
2. Velocix constructs `Request` **from that dict** — re-parsing headers,
   query, etc.
3. handler runs, returns `Response`
4. Velocix **builds ASGI message dicts** (`http.response.start`,
   `http.response.body`)
5. granian reads those dicts back and writes the socket

Measured bridge cost (in-process simulation): **~4–8 µs/request** — the scope
dict construction, header re-parse into `Request`, and the response-dict
round-trip. That is the entire prize a runtime can claim on the Python side.
The remaining ~8–16 µs of granian's Rust time is inherent HTTP serving (parse,
socket I/O, write) — a new runtime does that work too, it just doesn't make it
disappear.

---

## The design in one paragraph

Three tiers. **Tier 1** serves `@cache_response` routes entirely from Rust
memory — Python never runs, which turns cacheable routes into pure HTTP
serving. **Tier 2** replaces the ASGI bridge with a typed ABI: Rust constructs
the Python `Request` pre-filled and extracts `(status, headers, body)` from
the returned `Response` directly — no scope dicts, no re-parses. **Tier 3**
attacks the GIL contention measured in every saturation test via
sub-interpreters, then free-threaded CPython.

---

## Tier 1 — Rust-owned responses (Python never runs)

The `@cache_response(ttl)` decorator already exists (Python side): it caches
the orjson-serialized body keyed by method + path + query, and cache hits skip
the handler and orjson entirely. Measured: **379K req/s in-process with Python
still doing the work** (7.8× uncached).

Tier 1 promotes that cache into the engine. At route registration, the engine
sees `__response_cache_ttl__` on the handler and takes ownership: it runs the
handler once, serializes, and stores `(status, headers, body)` **in Rust
memory**. A request to that route is then: parse → match → serve bytes from
memory → done. No interpreter, no GIL, no Python objects.

- The opt-in contract already encodes the correctness rule: a cached route
  must not read auth, headers, or cookies. The engine enforces it at
  registration by only accepting routes with `__response_cache_ttl__` and no
  request-dependent dependencies.
- Cache invalidation is the Python dict's TTL, moved to a Rust map with the
  same semantics.
- **Target: 10–100× current live numbers on cacheable routes** (from ~35K
  req/s per worker to the raw HTTP ceiling — hundreds of thousands per
  worker). This is the one number granian structurally cannot produce,
  because granian always runs the app.
- This is the proof-of-value milestone (M0). It has none of the compiler
  complexity of the other tiers.

## Tier 2 — typed ABI for dynamic routes

The native protocol. Replaces both ASGI round-trips:

**Today (granian + ASGI):** Rust parses HTTP → builds generic scope dict →
Python builds `Request` from that dict (re-parsing headers, query) → handler →
Python builds response dicts → Rust reads dicts → writes socket.

**Native:** Rust parses HTTP → **directly constructs the Python `Request`**
with pre-filled slots (method, path, pre-parsed query, raw headers as bytes
tuples, body buffer) → calls `app.handle_request(request)` → handler returns
`Response` → engine extracts `(status, raw_headers, body)` → writes straight
to socket.

This kills the scope dict, the header re-parse, and the response-dict
round-trip — the measured ~4–8 µs/req bridge cost. The `Request` object is
still built (the handler needs it), but Rust fills it in one shot via the
C-API (`PyObject_Call` with pre-built arguments — plain PyO3, no codegen).

- **Target: ~1.5–2× on dynamic routes in-process** (10 µs → ~5–6 µs
  framework floor). Live impact will be smaller — every optimization round so
  far showed sockets dominating, so only a slice of the framework win
  survives under real HTTP. The win grows when the box is CPU-bound at high
  concurrency.
- The ASGI `__call__` stays in place untouched, so the framework remains
  runnable on uvicorn/granian. The native path is additive.

## Tier 3 — concurrency

Every saturation test showed GIL contention as the throughput wall. The
runtime plans for, in order:

1. **Worker processes** (like granian today) — measured near-linear: 4 → 12
   workers ≈ 3×.
2. **Sub-interpreters** (CPython 3.12+): several interpreters per process,
   cutting process overhead. granian supports this; the embed pattern is
   proven.
3. **Free-threaded CPython (3.13t)**: removes the GIL wall entirely. If the
   engine embeds correctly (GIL released around all I/O, no C-API state shared
   across interpreters), CPU-bound throughput multiplies by cores instead of
   collapsing into contention.

Tier 1 needs no GIL at all — that path is pure Rust regardless of interpreter.

---

## Why there is no LLVM runtime JIT

LLVM has exactly three possible jobs here. Two happen automatically, one was a
mislabel.

1. **Build-time compiler — automatic.** Rust compiles through LLVM. The
   engine's HTTP parser, socket loop, cache, and bridge are LLVM machine code
   from day one. PGO adds ~10–20% on the native path for free. This is not a
   decision; it's just having a compiler.

2. **Runtime JIT of per-handler dispatch shims — dropped.** The idea was
   compiling the ~6 µs of Python glue (resolve → plan → call → response
   build) around each handler into native code. The honest assessment:
   - The shim would be generated **once at startup** per handler, never per
     request — one-time specialization, not hot-path compilation. "JIT" was
     the wrong word.
   - The glue it targets dies with **static** code: a dispatch table built at
     registration, and the engine calling the handler via `PyObject_Call`
     with pre-built argument tuples. That is plain PyO3 — no codegen.
   - The async runtime itself is static code; recompiling it per request
     would be pure waste.

3. **What LLVM fundamentally cannot do:** make the Python handler body fast.
   A shim can only call *into* CPython faster; the handler is still
   interpreted Python. JIT-compiling Python bodies is PyPy's multi-decade
   project. Even with LLVM in, dynamic routes keep a Python floor.

**Conclusion:** LLVM remains the build-time backend (automatic, free). The
runtime-JIT idea was mislabeled glue-removal, and the glue-removal happens
without it. None of the three tiers depends on codegen.

---

## Native protocol vs ASGI compatibility

Decision: **native protocol first** (a Velocix-native `handle_request`
interface), with the ASGI `__call__` retained as a compatibility path.

| | ASGI-compatible (drop-in) | Velocix-native |
|---|---|---|
| Replaces | uvicorn; captures only part of the bridge | Everything ASGI saves **plus** scope dicts, header re-parse, message protocol (~4–8 µs/req) |
| Who can run on it | Any ASGI app | Only Velocix apps (fine — it's Velocix's runtime) |
| Effort | ~2 months to MVP | +1 month on top |

The measured prize for the native protocol is the full bridge cost; the
ASGI-compat path only captures part of it.

---

## Milestones

- **M0 — Tier 1 proof of value.** Rust workspace skeleton: tokio event loop,
  TCP accept, keep-alive, PyO3 embed, cached routes served from Rust memory
  without Python. Get the 10–100× number on the board early.
- **M1 — HTTP/1.1 complete + Tier 2.** httparse, chunked encoding,
  backpressure, keep-alive; Rust-side `Request` construction and the
  `handle_request` fast path. Replaces uvicorn/granian for Velocix apps.
- **M2 — streaming + WebSockets.** Streaming responses across the GIL
  boundary; WebSocket upgrade path.
- **M3 — HTTP/2 + TLS.** `h2` and `rustls`. Bolt-on; does not change the
  native-protocol design.
- **M4 — sub-interpreters, then free-threaded CPython.**

M0 and M1 are HTTP/1.1 + keep-alive only. No HTTP/2, TLS, or WebSockets until
M2/M3 — they don't change the design and they're not needed to prove the
tiers.

---

## The hard parts (honest)

1. **Streaming across the GIL boundary** — a `StreamingResponse` needs the
   Rust side to pull chunks from a Python async iterator: release the GIL
   between chunk reads, apply backpressure, detect client disconnect without
   deadlocking the event loop. Where most naive runtimes break.
2. **Embedding correctness** — GIL discipline, reference counting at the
   boundary, sub-interpreter isolation. granian's source is the in-domain
   reference for all of it.
3. **Tier 1 correctness** — the engine must refuse routes that read
   per-request state, or it serves wrong data. The opt-in
   `__response_cache_ttl__` contract encodes this; the engine enforces it at
   registration.
4. **Scope discipline** — the native protocol is only worth it if it stays
   tight. Every feature added to the bridge re-imports ASGI-shaped costs.

---

## Expected outcomes (targets, not measurements)

| Route class | Target |
|---|---|
| Cacheable routes (Tier 1) | **10–100×** current live — Python structurally absent |
| Dynamic routes (Tier 2) | **1.5–2.5×** end-to-end; more when CPU-bound |
| Concurrency (Tier 3) | Near-linear with cores once the GIL wall is gone |

### What it will NOT do

- **Dynamic handler bodies stay Python.** A `json.dumps`-heavy route is
  bounded by Python regardless of the engine.
- **No raw-language speedup of Python itself.** The engine's gains come from
  removing work (bridge round-trips, GIL contention, Python on cached paths),
  not from making Python faster.
- **No SIMD story.** Everything SIMD-able is already native (orjson, httparse,
  fast-query-parsers, msgspec). The remaining costs are allocations and glue,
  which SIMD does not fix.
- **No JIT.** See the LLVM section above.
- **A single client cannot saturate Tier 1.** Demonstrating it needs
  distributed load generation.

---

## Open decisions

- **Worker/threading model detail** — exact sub-interpreter scheduling and
  whether Tier 1 shares one Rust event loop across all interpreters.
- **`handle_request` calling convention** — exact signature of the native
  entry point (e.g. `app.handle_request(request) -> Response`).
- **Cache ownership** — whether Tier 1 replaces the Python `_response_cache`
  entirely or keeps both (Python dict for non-native servers, Rust map for
  the engine).

---

## Relationship to other docs

- `docs/PERFORMANCE.md` — what is measured today (the baseline this design
  builds on).
- `docs/INTERNALS.md` — how the framework works today (the ASGI path this
  design keeps as a compatibility layer).
