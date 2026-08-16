import json
import os
import sys


def norm(name):
    if name.startswith("/users/"):
        return "/users/{id}"
    return name.split("?")[0]


def summarize(fw, path):
    if not os.path.exists(path):
        return f"{fw:12s} no results"
    try:
        d = json.load(open(path))
    except Exception as e:
        return f"{fw:12s} parse error: {e}"
    if isinstance(d, dict):
        d = [d]
    routes = {}
    tot = {"reqs": 0, "fails": 0, "time": 0.0}
    for s in d:
        n = norm(s.get("name", ""))
        r = routes.setdefault(n, {"reqs": 0, "fails": 0, "time": 0.0, "max": 0, "resp": []})
        reqs = s.get("num_requests", 0)
        r["reqs"] += reqs
        r["fails"] += s.get("num_failures", 0)
        r["time"] += s.get("total_response_time", 0.0)
        r["max"] = max(r["max"], s.get("max_response_time", 0))
        r["resp"].extend(s.get("response_times", {}).items())
        tot["reqs"] += reqs
        tot["fails"] += s.get("num_failures", 0)
        tot["time"] += s.get("total_response_time", 0.0)
    dur = d[-1]["last_request_timestamp"] - d[0]["start_time"] if len(d) > 1 else 1
    dur = max(dur, 1)
    lines = [f"{fw:12s} rps={tot['reqs']/dur:8.1f}  reqs={tot['reqs']:7d}  fails={tot['fails']:4d}  avg={tot['time']/max(tot['reqs'],1):.1f}ms  (window {dur:.0f}s)"]
    for n in sorted(routes):
        r = routes[n]
        rr = r["reqs"]
        if not rr:
            continue
        rps = rr / dur
        avg = r["time"] / rr
        samples = []
        for ms, cnt in r["resp"]:
            samples.extend([ms] * cnt)
        samples.sort()
        p95 = samples[int(len(samples) * 0.95)] if samples else 0
        lines.append(f"    {n:20s} rps={rps:8.1f} reqs={rr:7d} fails={r['fails']:4d} avg={avg:6.1f}ms p95={p95}ms max={r['max']}ms")
    return "\n".join(lines)


for fw in sys.argv[1:] or ["velocix"]:
    print(summarize(fw, f"/tmp/sat_{fw}.json"))
    print()
