#!/bin/bash
# Full wrk2 battery: all 4 bench routes x both rates, three runs each.
# Identical workload for every framework (the payloads are the same bytes,
# enforced by verify_identical.py) -- nothing here is tuned per framework.
#
# Usage: bash run_wrk2_all.sh [framework]
#   framework: velocix | starlette | fastapi | litestar | falcon | blacksheep | sanic
#              (default: run all seven)
set -u
cd "$(dirname "$0")"

if [ $# -ge 1 ]; then
  FWS=("$1")
else
  FWS=(velocix starlette fastapi litestar falcon blacksheep sanic)
fi

for fw in "${FWS[@]}"; do
  echo "== $fw: /users R1000 =="
  bash run_wrk2.sh "$fw" "/users/42?limit=5" 1000
  echo "== $fw: /users R4000 =="
  bash run_wrk2.sh "$fw" "/users/42?limit=5" 4000
  echo "== $fw: /items R1000 =="
  bash run_wrk2.sh "$fw" "/items" 1000
  echo "== $fw: /orders POST R1000 =="
  bash run_wrk2.sh "$fw" "/orders" 1000 POST
  echo "== $fw: /slow R500 =="
  bash run_wrk2.sh "$fw" "/slow" 500
done
echo "BATTERY COMPLETE"
