#!/bin/bash
set -u
cd "$(dirname "$0")"
FWS="velocix starlette fastapi litestar falcon blacksheep sanic"
for FW in $FWS; do
  echo "=== [$FW] saturation ==="
  bash run_sat.sh "$FW" || echo "SAT FAIL $FW"
  echo "=== [$FW] realistic ==="
  bash run_real.sh "$FW" || echo "REAL FAIL $FW"
done
echo "=== ALL DONE ==="
