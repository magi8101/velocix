#!/bin/bash
# Live granian benchmark: 4 workers, c=100, n=30K, best of 3.
# Usage: bash benchmarks/run_granian.sh
set -u
cd "$(dirname "$0")"

wait_ready() {
  for i in $(seq 1 30); do
    curl -s -m 1 -o /dev/null "http://127.0.0.1:8000/items" && return 0
    sleep 1
  done
  return 1
}

ab_rps() {
  ab -k -c 100 -n 30000 "$@" 2>/dev/null | grep "Requests per second" | grep -oE '[0-9]+\.[0-9]+' | head -1
}

best3() {
  local best=0
  for i in 1 2 3; do
    v=$(ab_rps "$@")
    if [ -z "$v" ]; then v=0; fi
    best=$(echo "$best $v" | awk '{print ($1>$2)?$1:$2}')
  done
  echo "$best"
}

pkill -f "granian" 2>/dev/null
sleep 2

granian --interface asgi bench_velocix:app --host 127.0.0.1 --port 8000 --workers 4 > /tmp/bench_granian.log 2>&1 &
SRV_PID=$!
if ! wait_ready; then echo "FAILED start"; tail -5 /tmp/bench_granian.log; exit 1; fi
sleep 1

U=$(best3 'http://127.0.0.1:8000/users/42?limit=5')
I=$(best3 'http://127.0.0.1:8000/items')
echo "RESULT users=$U req/s  items=$I req/s"

kill $SRV_PID 2>/dev/null
wait $SRV_PID 2>/dev/null
pkill -f "granian" 2>/dev/null
