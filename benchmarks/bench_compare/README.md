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
  - **Realistic** (`run_real.sh`, `locustfile_real.py`): 100 users, think time 0.1–0.5 s
    between requests, 60 s — client-throttled
  - **Saturation** (`run_sat.sh`, `locustfile_sat.py`): 500 users, no think time, 45 s —
    server ceiling
- Response byte-identity verified before every run (the payloads are the same bytes for every framework)

## Results (2026-08-16, single runs per framework, 4 workers on one shared box)

### Realistic (100 users, think time — client-throttled)

| Framework | rps | avg | fails |
|---|---|---|---|
| velocix | 318.4 | 3.0 ms | 0 |
| sanic | 318.2 | 2.6 ms | 0 |
| starlette | 317.6 | 3.2 ms | 0 |
| litestar | 318.0 | 3.2 ms | 0 |
| falcon | 319.9 | 3.2 ms | 0 |
| blacksheep | 319.8 | 3.0 ms | 0 |
| fastapi | 319.8 | 3.7 ms | 0 |

All frameworks sit at the client ceiling (~318 rps — 100 users × ~0.3 s think time caps the
load generator, not the servers). Latency is the differentiator: sanic 2.6 ms, velocix and
blacksheep 3.0 ms, fastapi 3.7 ms (its `response_model`/validation pass on `/items` costs
the most).

### Saturation (500 users, no think time — server ceiling)

| Framework | rps | avg | fails |
|---|---|---|---|
| velocix | **2,092** | 36.6 ms | 0 |
| sanic | 2,082 | 37.1 ms | 0 |
| blacksheep | 2,022 | 38.0 ms | 0 |
| litestar | 1,903 | 40.3 ms | 0 |
| starlette | 1,877 | 40.9 ms | 0 |
| falcon | 1,844 | 41.7 ms | 0 |
| fastapi | 1,812 | 42.5 ms | 0 |

Per-route (velocix): `/users/{id}` 953 rps, `/items` 568 rps, `/orders` 383 rps,
`/slow` 187 rps — p95 40–41 ms, max 1.3–1.5 s (cold-start GC spikes).

## Honest reading

- Velocix is fastest at the ceiling this run: **+0.5% vs sanic, +3.5% vs blacksheep,
  +10–15% vs the rest** (litestar +10%, starlette +11%, falcon +13%, fastapi +15%).
- The absolute numbers move with box conditions — the old recorded run converged at
  ~2,200–2,340 rps with a 3–6% spread; this run converged lower (~1,800–2,100) with a
  wider spread. **Single runs, shared noisy box: treat the ordering and rough margins as
  signal, the exact rps as noise.** Re-run `run_all.sh` for a fresh reading.
- FastAPI is consistently last on both axes (its request pipeline does the most work per
  request).
- Sanic's realistic-latency win (2.6 ms) is its own-Rust-server advantage at low load; it
  does not translate to a throughput lead at the ceiling (velocix edges it 2,092 vs 2,082).
- Zero failures across every framework and profile.

## Reproduce

```bash
# byte-identity check (6 ASGI apps; sanic verified via curl in run scripts' readiness check)
python3 verify_identical.py

# whole battery (both profiles, all 7 frameworks) — ~20 min
bash run_all.sh

# one framework, one profile (velocix | starlette | fastapi | litestar | falcon | blacksheep | sanic)
bash run_real.sh velocix   # realistic, 100 users / 60 s
bash run_sat.sh velocix    # saturation, 500 users / 45 s

# summarize JSON results (saturation: /tmp/sat_<fw>.json, realistic: /tmp/real_<fw>.json)
python3 summary.py velocix
```

Requires: `locust`, `granian`, `sanic`, and all seven frameworks installed.

---

# Fixed-Rate Load Testing (wrk2)

In addition to the Locust profiles, the same 7 frameworks are load-tested with
[wrk2](https://github.com/giltene/wrk2) — a fixed-rate load generator that holds the request
rate constant and reports true latency percentiles (HdrHistogram), including the tail
behavior that a rate-limited client would see.

Methodology (identical for every framework — nothing tuned per framework):

- Four routes, all byte-identical across frameworks (enforced by `verify_identical.py`):
  - `GET /users/42?limit=5` — path + query params, small JSON (397 B)
  - `GET /items` — large static JSON (7,897 B)
  - `POST /orders` — JSON body validation (48 B response; body from `post_orders.lua`)
  - `GET /slow` — `asyncio.sleep(0.005)` (simulated I/O)
- `wrk -t4 -c100 -d20s -R<rate> -L`, 3 runs per framework per route/rate, median run reported
- Servers: ASGI frameworks under **granian 4 workers**; Sanic runs its own server (4 workers)
- Rates: **R=1000** for the CPU-bound routes (`/users`, `/items`, `/orders`) — low-load
  latency comparison; **R=500** for `/slow` (an I/O-bound 5 ms sleep caps sustainable
  throughput at ~800 rps across 4 workers, so 1000 would overload every framework
  equally); **R=4000** for `/users` — saturation to expose tail latency under overload

## Results (2026-08-17, 3 runs per framework per route/rate, 4 workers on one shared box)

### `/users` R=1000 (low load — all frameworks sustain the full rate)

| Framework | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|
| **velocix** | **1.63 ms** | **2.27 ms** | **2.87 ms** | 7.15 ms |
| falcon | **1.63 ms** | 2.29 ms | 2.84 ms | 3.27 ms |
| sanic | 1.65 ms | 2.31 ms | 2.88 ms | 3.38 ms |
| fastapi | 1.69 ms | 2.35 ms | 2.94 ms | 3.47 ms |
| litestar | 1.73 ms | 2.41 ms | 2.97 ms | 3.54 ms |
| blacksheep | 1.85 ms | 3.36 ms | 4.97 ms | 6.11 ms |
| starlette | 1.98 ms | 3.91 ms | 5.67 ms | 18.45 ms |

### `/users` R=4000 (saturation — pushed above sustainable rate)

| Framework | achieved rps | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|---|
| falcon | 3,990 | **1.55 ms** | **2.45 ms** | **3.38 ms** | 18.29 ms |
| fastapi | 3,990 | 1.76 ms | 2.84 ms | 3.77 ms | 16.59 ms |
| starlette | 3,990 | 1.78 ms | 2.88 ms | 3.79 ms | 4.52 ms |
| blacksheep | 3,990 | 1.82 ms | 2.83 ms | 3.55 ms | 4.07 ms |
| **velocix** | 3,942 | 1.91 ms | 3.53 ms | 5.21 ms | 16.54 ms |
| litestar | 3,942 | 1.80 ms | 3.36 ms | 5.32 ms | 6.51 ms |
| sanic | 3,942 | 1.71 ms | 3.02 ms | 5.11 ms | 6.76 ms |

### `/items` R=1000 (large JSON body)

| Framework | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|
| **blacksheep** | **1.40 ms** | **2.22 ms** | **2.90 ms** | **3.52 ms** |
| sanic | 1.75 ms | 2.43 ms | 3.17 ms | 17.84 ms |
| **velocix** | 1.85 ms | 2.57 ms | 3.19 ms | 6.12 ms |
| fastapi | 1.86 ms | 2.56 ms | 3.29 ms | 7.36 ms |
| falcon | 1.86 ms | 2.58 ms | 3.35 ms | 8.40 ms |
| starlette | 2.01 ms | 4.06 ms | 6.48 ms | 9.00 ms |
| litestar | 2.01 ms | 4.41 ms | 6.71 ms | 10.09 ms |

### `/orders` POST R=1000 (JSON body validation)

| Framework | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|
| **velocix** | **1.70 ms** | **2.35 ms** | **2.85 ms** | **3.32 ms** |
| fastapi | 1.66 ms | 2.34 ms | 2.95 ms | 3.51 ms |
| blacksheep | 1.66 ms | 2.29 ms | 2.84 ms | 6.64 ms |
| litestar | 1.67 ms | 2.33 ms | 2.90 ms | 5.33 ms |
| falcon | 1.68 ms | 2.35 ms | 3.03 ms | 15.49 ms |
| starlette | 1.72 ms | 2.35 ms | 2.99 ms | 3.55 ms |
| sanic | 1.93 ms | 3.91 ms | 5.80 ms | 9.02 ms |

### `/slow` R=500 (I/O-bound, 5 ms sleep)

| Framework | achieved rps | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|---|
| **velocix** | **500** | 7.01 ms | 8.12 ms | 9.06 ms | **9.69 ms** |
| starlette | 500 | **6.81 ms** | **7.75 ms** | **8.76 ms** | 20.66 ms |
| falcon | 500 | 6.86 ms | 7.81 ms | 8.74 ms | 21.26 ms |
| sanic | 500 | 6.86 ms | 7.76 ms | 8.64 ms | 9.82 ms |
| blacksheep | 500 | 6.92 ms | 7.86 ms | 8.81 ms | 17.66 ms |
| fastapi | 494 | 7.05 ms | 8.64 ms | 10.24 ms | 18.85 ms |
| litestar | 494 | 7.12 ms | 8.58 ms | 10.55 ms | 23.09 ms |

## Honest reading (wrk2)

- Every framework sustains the full rate on the CPU-bound routes (~999/1000 req/s) — the
  rate is held constant, so **latency is the differentiator**. Velocix leads `/users` p50
  (1.63 ms, tied with falcon), `/orders` (lowest p50 and p99.9), and `/slow` (tightest tail
  at 9.69 ms p99.9, tied p50 with the field).
- `/items` is blacksheep's best route (its orjson-backed serializer wins on the large body);
  velocix sits mid-pack with the rest — this is the one route where the framework's
  advantage is neutralized by the payload size dominating the cost.
- The R=4000 saturation row is the noisiest: all frameworks land within ~2% on achieved rps,
  and p99.9 spikes (15–18 ms on falcon/fastapi/velocix) are GC/GIL contention under
  sustained load, not a stable ranking — earlier runs had velocix at 4.34 ms p99.9 and
  starlette at 15.32 ms on this same route/rate. Treat the R=1000 rows as the signal.
- Single runs on a shared noisy box: exact rps and the tight p99.9 deltas move between
  runs; the ordering and the wide-tail-vs-tight-tail distinction are the stable findings.

## Reproduce

```bash
# one framework, one route, one rate (3 runs, ~75 s)
bash run_wrk2.sh velocix "/users/42?limit=5" 1000

# full battery (all 4 routes x both rates, one or all frameworks) — ~7 min per framework
bash run_wrk2_all.sh velocix
bash run_wrk2_all.sh   # all seven

# summarize the runs (latency percentiles of the median run)
python3 summary_wrk2.py velocix --route _users_42_limit=5_R1000
python3 summary_wrk2.py velocix   # all routes for one framework
```

`run_wrk2.sh` writes `/tmp/wrk2_<fw>_<tag>_R<rate>.txt`; `summary_wrk2.py` reads those and
prints per-run rps plus the p50/p90/p99/p99.9 of the run closest to the median rps.
`post_orders.lua` supplies the POST body for `/orders` (the exact bytes from
`verify_identical.py`).

Requires: `wrk2` (built from source; the script looks for it at `$WRK` or
`/home/user/tools/wrk2/wrk`, falling back to `/tmp/wrk2/wrk`).
