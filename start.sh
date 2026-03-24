#!/bin/bash
# Nemotron Financial Survey Demo — startup script
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=8080
cd "$REPO_DIR"

echo "=== Nemotron Financial Survey Demo ==="
echo ""

classify_backend_port_owner() {
    python3 "$REPO_DIR/backend/start_sh_restart.py" classify-port --port "$BACKEND_PORT" --repo-dir "$REPO_DIR"
}

stop_existing_repo_backend() {
    local owner_status owner_kind owner_pids pid cmd
    owner_status="$(classify_backend_port_owner)"
    set -- $owner_status
    owner_kind="${1:-none}"
    shift || true
    owner_pids=("$@")

    case "$owner_kind" in
        none)
            return 0
            ;;
        repo-owned)
            echo "  Stopping existing backend on port ${BACKEND_PORT}: ${owner_pids[*]}"
            kill "${owner_pids[@]}" 2>/dev/null || true
            for _ in $(seq 1 30); do
                owner_status="$(classify_backend_port_owner)"
                set -- $owner_status
                if [ "${1:-none}" = "none" ]; then
                    echo "  Existing backend stopped."
                    return 0
                fi
                sleep 1
            done
            echo "ERROR: Existing repo-owned backend on port ${BACKEND_PORT} did not exit."
            exit 1
            ;;
        other)
            echo "ERROR: Port ${BACKEND_PORT} is already in use by a non-repo process."
            for pid in "${owner_pids[@]}"; do
                cmd="$(ps -o args= -p "$pid" 2>/dev/null || true)"
                echo "  PID $pid: ${cmd:-<unknown>}"
            done
            exit 1
            ;;
        *)
            echo "ERROR: Unexpected port-owner classification: $owner_kind"
            exit 1
            ;;
    esac
}

# Backend setup
echo "[1/4] Installing Python dependencies..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

# Ensure data dir exists
DATA_DIR="${DATA_DIR:-$REPO_DIR/data}"
mkdir -p "$DATA_DIR"

echo "[2/4] Starting backend (port ${BACKEND_PORT})..."
stop_existing_repo_backend
cd "$REPO_DIR/backend"
source venv/bin/activate
export PYTHONPATH="$REPO_DIR/backend"
python -m uvicorn main:app --host 0.0.0.0 --port "$BACKEND_PORT" --env-file "$REPO_DIR/.env" &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

echo -n "  Waiting for backend..."
for i in $(seq 1 120); do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo
        echo "ERROR: Backend process exited during startup."
        wait "$BACKEND_PID"
        exit 1
    fi
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${BACKEND_PORT}/ready" 2>/dev/null || true)
    if [ "$STATUS" = "200" ]; then
        echo " ready."
        break
    fi
    if [ "$STATUS" = "500" ]; then
        echo
        echo "ERROR: Database initialization failed. Check logs for details."
        exit 1
    fi
    sleep 5
    echo -n "."
    if [ "$i" -eq 120 ]; then
        echo
        echo "ERROR: Backend did not become ready after 600s."
        exit 1
    fi
done

# Seed demo history
echo "[3/4] Seeding demo history..."
cd "$REPO_DIR/backend"
# Export .env so seed script inherits the same config as uvicorn
set -a
. "$REPO_DIR/.env"
set +a
python -c "
import os, sys
sys.path.insert(0, '.')
from scripts.seed_demo_history import seed_history
seed_history()
" || echo "  (Seeding skipped — may already exist)"

# Frontend
echo "[4/4] Preparing frontend..."
cd "$REPO_DIR/frontend"
if [ ! -d "node_modules" ] || [ "package.json" -nt "node_modules" ] || [ "package-lock.json" -nt "node_modules" ]; then
    echo "  Installing/updating frontend dependencies..."
    npm install
else
    echo "  Frontend dependencies are up to date."
fi
echo "  Building frontend..."
npm run build

echo ""
echo "=== Started! ==="
echo "App:      http://localhost:${BACKEND_PORT}"
echo "API docs: http://localhost:${BACKEND_PORT}/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID 2>/dev/null; exit" INT TERM
wait
