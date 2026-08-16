# Cross-Framework Comparison (Locust)

Velocix vs Starlette vs FastAPI vs Litestar vs Falcon vs BlackSheep vs Sanic, all serving
**byte-identical responses** on 4 routes (verified by `verify_identical.py`):

- `GET /users/{id}?limit=N` — path param + query param, small JSON (397 B)
- `GET /items` — static list of 100 products (7,897 B)
- `POST /orders` — JSON body validation + computation (48 B)
- `GET /slow` — `asyncio.sleep(0.005)` (simulated I/O)

## Setup

- Servers: ASGI frameworks under **granian 4 workers**; Sanic runs its own server (4 workers)
- Two load profiles with **Locust** (all frameworks get the identical workload):
  - **Realistic**: 100 users, think time 0.1–0.5 s between requests, 60 s — client-throttled
  - **Saturation**: 500 users, no think time, 45 s — server ceiling
- Response byte-identity verified before every run (the payloads are the same bytes for every framework)

## Results

### Realistic (100 users, think time — client-throttled)

| Framework | rps | avg | fails |
|---|---|---|---|
| velocix | 319.7 | 3.0 ms | 0 |
| sanic | 317.8 | 2.5 ms | 0 |
| litestar | 319.4 | 3.1 ms | 0 |
| starlette | 318.9 | 3.1 ms | 0 |
| blacksheep | 317.3 | 3.1 ms | 0 |
| falcon | 317.2 | 3.1 ms | 0 |
| fastapi | 317.9 | 3.5 ms | 0 |

All frameworks sit at the client ceiling (~318 rps — 100 users × ~0.3 s think time caps the
load generator, not the servers). Latency is the differentiator: sanic 2.5 ms, velocix 3.0 ms,
fastapi 3.5 ms (its `response_model`/validation pass on `/items` costs the most).

### Saturation (500 users, no think time — server ceiling)

| Framework | rps | avg | fails |
|---|---|---|---|
| velocix | **2,337** | 32.6 ms | 0 |
| sanic | 2,308 | 33.1 ms | 0 |
| blacksheep | 2,291 | 33.4 ms | 0 |
| starlette | 2,267 | 33.7 ms | 0 |
| litestar | 2,246 | 34.0 ms | 0 |
| falcon | 2,221 | 34.4 ms | 0 |
| fastapi | 2,198 | 34.8 ms | 0 |

## Honest reading

- Under saturation on 4 workers this shared box converges at ~2,200–2,340 rps. The spread is
  **3–6%**, not the 2× the in-process framework-floor benchmarks show — because under real HTTP
  the granian server + sockets + GIL contention dominate, and the framework's own per-request
  cost is a smaller slice.
- Velocix is fastest at the ceiling (**+3% vs starlette, +6% vs fastapi, +1% vs sanic**) and
  tied-second on realistic latency.
- FastAPI is consistently last on both axes (its request pipeline does the most work per request).
- Sanic's realistic-latency win (2.5 ms) is its own-Rust-server advantage at low load; it does
  not translate to a throughput lead at the ceiling.

## Reproduce

```bash
# byte-identity check (6 ASGI apps; sanic verified via curl in run_sat.sh readiness check)
python3 verify_identical.py

# saturation for one framework (velocix | starlette | fastapi | litestar | falcon | blacksheep | sanic)
bash run_sat.sh velocix
python3 summary.py velocix
```

Requires: `locust`, `granian`, `sanic`, and all seven frameworks installed.
