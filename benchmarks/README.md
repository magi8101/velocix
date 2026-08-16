# Benchmarks

Reproducible performance harness for Velocix. All numbers in
[docs/PERFORMANCE.md](../docs/PERFORMANCE.md) are produced by these scripts.

## Requirements

- `granian` (the intended server)
- `ab` (ApacheBench) for HTTP load
- `fast-query-parsers`, `orjson` (runtime deps, already in requirements.txt)
- `py-spy` + sudo for the live process split

## In-process framework floor (no sockets)

```bash
python3 benchmarks/profile_inproc.py
```

## Live over granian (4 workers, c=100, best of 3)

```bash
bash benchmarks/run_granian.sh
```

## Comparing against other frameworks

`benchmarks/bench_compare/` is a full Locust harness comparing Velocix against
Starlette, FastAPI, Litestar, Falcon, BlackSheep, and Sanic — all serving
byte-identical responses on 4 routes, under granian 4 workers. Two profiles:
realistic (100 users, think time) and saturation (500 users, no think time).

```bash
bash benchmarks/bench_compare/run_all.sh   # whole battery, ~20 min
bash benchmarks/bench_compare/run_sat.sh velocix
bash benchmarks/bench_compare/run_real.sh velocix
```
