"""Summarize wrk2 runs produced by run_wrk2.sh.

Reads /tmp/wrk2_<fw>_<tag>.txt files, splits on the "=== RUN n END ==="
markers, and reports achieved rps + latency percentiles per run plus the
median across the three runs.

Usage: python3 summary_wrk2.py <fw> [<fw> ...] [--route <tag>]
"""

import re
import statistics
import sys


def norm_latency(line: str) -> float:
    """'   50.000%    1.01ms' -> 1.01 (ms)"""
    m = re.search(r"([\d.]+)(ms|us|s)", line)
    if not m:
        return 0.0
    val, unit = float(m.group(1)), m.group(2)
    return val * (1000 if unit == "s" else (0.001 if unit == "us" else 1))


def parse_file(path: str):
    runs = []
    try:
        text = open(path).read()
    except FileNotFoundError:
        return None
    blocks = re.split(r"=== RUN \d END ===\n?", text)
    for block in blocks:
        if not block.strip():
            continue
        rps = None
        lat = {}
        for line in block.splitlines():
            m = re.search(r"Requests/sec:\s+([\d.]+)", line)
            if m:
                rps = float(m.group(1))
            m = re.search(r"([\d.]+)%\s+([\d.]+(?:ms|us|s))", line)
            if m:
                lat[m.group(1)] = norm_latency(line)
        if rps is not None:
            runs.append({"rps": rps, "lat": lat})
    return runs


def pct_key(p: str) -> float:
    return float(p.rstrip("%"))


def main():
    fws = [a for a in sys.argv[1:] if not a.startswith("--")]
    route = None
    if "--route" in sys.argv:
        route = sys.argv[sys.argv.index("--route") + 1]
    for fw in fws:
        if route:
            paths = [f"/tmp/wrk2_{fw}_{route}.txt"]
        else:
            import glob

            paths = sorted(glob.glob(f"/tmp/wrk2_{fw}_*.txt"))
        for path in paths:
            runs = parse_file(path)
            if not runs:
                print(f"{path}: no data")
                continue
            tag = path.split("wrk2_")[-1].replace(".txt", "")
            rps_list = [r["rps"] for r in runs]
            med_rps = statistics.median(rps_list)
            print(f"{fw:12s} {tag:14s} runs={len(runs)} "
                  f"rps=[{' '.join(f'{v:.0f}' for v in rps_list)}] median={med_rps:.0f}")
            # latency percentiles of the median run (closest to median rps)
            med_run = min(runs, key=lambda r: abs(r["rps"] - med_rps))
            if med_run["lat"]:
                keys = sorted(med_run["lat"], key=pct_key)
                lat_str = " ".join(f"{k}%:{v:.2f}ms" for k, v in
                                   [(k, med_run["lat"][k]) for k in keys if k in ("50.000", "90.000", "99.000", "99.900")])
                print(f"{'':12s} {'':14s} latency(median run): {lat_str}")


if __name__ == "__main__":
    main()
