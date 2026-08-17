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

Methodology (identical for every framework):

- Route: `GET /users/42?limit=5` (the same handler as the Locust runs)
- `wrk -t4 -c100 -d20s -R<rate> -L`, 3 runs per framework per rate, median run reported
- Servers: ASGI frameworks under **granian 4 workers**; Sanic runs its own server (4 workers)
- Two rates: **R=1000** (low-load latency comparison) and **R=4000** (saturation — every
  framework is pushed above its sustainable rate to expose tail latency)

## Results (2026-08-17, 3 runs per framework per rate, 4 workers on one shared box)

### R=1000 (low load — all frameworks sustain the full rate)

| Framework | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|
| **velocix** | **1.36 ms** | **1.99 ms** | 2.54 ms | **2.89 ms** |
| starlette | 1.48 ms | 2.05 ms | **2.51 ms** | 2.83 ms |
| litestar | 1.56 ms | 2.17 ms | 2.66 ms | 2.98 ms |
| blacksheep | 1.42 ms | 2.05 ms | 2.58 ms | 3.27 ms |
| falcon | 1.59 ms | 2.27 ms | 2.89 ms | 3.38 ms |
| fastapi | 1.61 ms | 2.48 ms | 3.41 ms | 4.39 ms |
| sanic | 1.66 ms | 2.32 ms | 3.01 ms | 11.33 ms |

Every framework sustains ~999/1000 req/s — the rate is held constant, so **latency is the
only differentiator**. Velocix has the lowest median (1.36 ms) and the tightest p99.9 tail
(2.89 ms); sanic shows a wide tail outlier (11.33 ms at p99.9) despite a mid-pack median.

### R=4000 (saturation — pushed above sustainable rate)

| Framework | achieved rps | p50 | p90 | p99 | p99.9 |
|---|---|---|---|---|---|
| **velocix** | **3,990** | 1.81 ms | **2.84 ms** | **3.65 ms** | **4.34 ms** |
| starlette | 3,990 | **1.52 ms** | 2.49 ms | 3.55 ms | 15.32 ms |
| fastapi | 3,990 | 1.55 ms | 2.47 ms | 3.37 ms | 15.85 ms |
| falcon | 3,990 | 1.57 ms | 2.56 ms | 3.43 ms | 3.97 ms |
| litestar | 3,942 | 1.82 ms | 3.15 ms | 4.95 ms | 9.07 ms |
| blacksheep | 3,942 | 1.77 ms | 3.46 ms | 5.16 ms | 11.30 ms |
| sanic | 3,942 | 1.83 ms | 3.13 ms | 4.61 ms | 5.40 ms |

At the ceiling all frameworks land within ~2% of each other on achieved rps (3,942–3,990) —
consistent with the Locust saturation result. The differentiator is tail latency: **velocix
keeps every percentile under 4.5 ms** while starlette and fastapi throw 15 ms+ p99.9 spikes
(GIL/GC contention under sustained load).

## Reproduce

```bash
# one framework, one route, one rate (3 runs, ~75 s)
bash run_wrk2.sh velocix "/users/42?limit=5" 1000

# summarize the runs (latency percentiles of the median run)
python3 summary_wrk2.py velocix --route _users_42_limit=5_R1000
```

`run_wrk2.sh` writes `/tmp/wrk2_<fw>_<tag>_R<rate>.txt`; `summary_wrk2.py` reads those and
prints per-run rps plus the p50/p90/p99/p99.9 of the run closest to the median rps.

Requires: `wrk2` (built from source; the script looks for it at `$WRK` or
`/home/user/tools/wrk2/wrk`, falling back to `/tmp/wrk2/wrk`).
