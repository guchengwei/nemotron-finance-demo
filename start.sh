#!/bin/bash
# Nemotron Financial Survey Demo — startup script
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

echo "=== Nemotron Financial Survey Demo ==="
echo ""

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

echo "[2/4] Starting backend (port 8080)..."
cd "$REPO_DIR/backend"
source venv/bin/activate
export PYTHONPATH="$REPO_DIR/backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --env-file "$REPO_DIR/.env" &
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
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ready 2>/dev/null || true)
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
echo "App:      http://localhost:8080"
echo "API docs: http://localhost:8080/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID 2>/dev/null; exit" INT TERM
wait
