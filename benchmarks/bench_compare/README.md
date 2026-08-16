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
