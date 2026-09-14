#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
GH_URL="http://localhost:8989"
GH_LOG="$SCRIPT_DIR/graphhopper.log"
GH_PID=""

cleanup() {
    if [ -n "$GH_PID" ] && kill -0 "$GH_PID" 2>/dev/null; then
        echo "Stopping GraphHopper (pid $GH_PID) ..."
        kill "$GH_PID" 2>/dev/null || true
        wait "$GH_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

echo "[1/3] Setting up Python venv ..."
bash "$SCRIPT_DIR/scripts/setup-venv.sh"

echo "[2/3] Starting GraphHopper server (logs: $GH_LOG) ..."
bash "$SCRIPT_DIR/scripts/run-graphhopper.sh" >"$GH_LOG" 2>&1 &
GH_PID=$!

echo "Waiting for GraphHopper to be ready at $GH_URL ..."
for i in $(seq 1 120); do
    if ! kill -0 "$GH_PID" 2>/dev/null; then
        echo "ERROR: GraphHopper exited early. See $GH_LOG" >&2
        exit 1
    fi
    if curl -sf "$GH_URL/health" >/dev/null 2>&1 \
        || curl -sf "$GH_URL/info" >/dev/null 2>&1; then
        break
    fi
    sleep 2
    if [ "$i" -eq 120 ]; then
        echo "ERROR: GraphHopper did not become ready within 240s. See $GH_LOG" >&2
        exit 1
    fi
done

echo "==============================================================="
echo "Setup Complete"

cat <<EOF

build_matrix.py builds a distance matrix (km) between a store and N
nearby residential buildings, using the local GraphHopper server. Provide
the store's latitude/longitude, the number of stores/buildings to sample,
and the search radius in km.

First activate the venv:
    source "$VENV_DIR/bin/activate"

Then run build_matrix.py, e.g.:
    python scripts/build_matrix.py --lat <store_lat> --lon <store_lon> --n <count> --radius <km>

Sample:
    python scripts/build_matrix.py --lat -37.8136 --lon 144.9631 --n 40 --radius 2.0

GraphHopper will keep running in the background (pid $GH_PID); stop it with:
    kill $GH_PID
EOF

# Keep GraphHopper alive after this script exits so the user can run build_matrix.
trap - EXIT INT TERM
disown "$GH_PID" 2>/dev/null || true
