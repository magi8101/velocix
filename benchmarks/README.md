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

## Comparing against Starlette / FastAPI

The comparison apps used for the cross-framework numbers are not committed
(theirs need pinned versions to be meaningful); the methodology is: identical
routes, byte-identical responses, same server, same load, best of 3.
