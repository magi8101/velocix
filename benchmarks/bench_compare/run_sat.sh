#!/bin/bash
set -u
FW=$1
cd "$(dirname "$0")"
pkill -f "grania[n]" 2>/dev/null; pkill -f bench_sanic 2>/dev/null; sleep 2
rm -f /tmp/sat_${FW}.json
if [ "$FW" = "sanic" ]; then
  sanic bench_sanic:app --host 127.0.0.1 --port 8000 --workers 4 --access-log > /tmp/srv_${FW}.log 2>&1 &
else
  granian --interface asgi bench_${FW}:app --host 127.0.0.1 --port 8000 --workers 4 > /tmp/srv_${FW}.log 2>&1 &
fi
SRV_PID=$!
for i in $(seq 1 30); do curl -s -m 1 -o /dev/null http://127.0.0.1:8000/items && break; sleep 1; done
sleep 1
locust -f locustfile_sat.py --headless -u 500 -r 100 -t 45s --host http://127.0.0.1:8000 --json > /tmp/sat_${FW}.json 2>/dev/null
kill $SRV_PID 2>/dev/null
pkill -f "grania[n]" 2>/dev/null; pkill -f bench_sanic 2>/dev/null
echo "DONE $FW"
