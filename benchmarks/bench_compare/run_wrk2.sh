#!/bin/bash
# wrk2 load test for one framework, one route, three runs.
# Usage: bash run_wrk2.sh <framework> <route> [rate]
#   framework: velocix | starlette | fastapi | litestar | falcon | blacksheep | sanic
#   route:     e.g. /users/42?limit=5  or  /items
#   rate:      wrk2 fixed request rate, default 1000
set -u
FW=$1
ROUTE=$2
RATE=${3:-1000}
cd "$(dirname "$0")"
WRK="${WRK:-/home/user/tools/wrk2/wrk}"
if [ ! -x "$WRK" ]; then WRK=/tmp/wrk2/wrk; fi
pkill -f "grania[n]" 2>/dev/null; pkill -f bench_sanic 2>/dev/null; sleep 2
if [ "$FW" = "sanic" ]; then
  sanic bench_sanic:app --host 127.0.0.1 --port 8000 --workers 4 --access-log > /tmp/srv_${FW}.log 2>&1 &
else
  granian --interface asgi bench_${FW}:app --host 127.0.0.1 --port 8000 --workers 4 > /tmp/srv_${FW}.log 2>&1 &
fi
SRV_PID=$!
for i in $(seq 1 30); do curl -s -m 1 -o /dev/null http://127.0.0.1:8000/items && break; sleep 1; done
sleep 1
TAG=$(echo "$ROUTE" | tr '/?&.' '____')
OUT=/tmp/wrk2_${FW}_${TAG}_R${RATE}.txt
: > "$OUT"
for run in 1 2 3; do
  "$WRK" -t4 -c100 -d20s -R${RATE} -L "http://127.0.0.1:8000${ROUTE}" >> "$OUT" 2>&1
  echo "=== RUN $run END ===" >> "$OUT"
  sleep 1
done
kill $SRV_PID 2>/dev/null
pkill -f "grania[n]" 2>/dev/null; pkill -f bench_sanic 2>/dev/null
echo "DONE $FW $ROUTE"
