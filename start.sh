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
DATA_DIR="${DATA_DIR:-/workspace/data}"
mkdir -p "$DATA_DIR"

echo "[2/4] Starting backend (port 8080)..."
cd "$REPO_DIR/backend"
source venv/bin/activate
export PYTHONPATH="$REPO_DIR/backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --env-file "$REPO_DIR/.env" &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
sleep 3
echo "  Backend ready."

# Seed demo history
echo "[3/4] Seeding demo history..."
cd "$REPO_DIR/backend"
python -c "
import os, sys
sys.path.insert(0, '.')
from scripts.seed_demo_history import seed_history
seed_history()
" || echo "  (Seeding skipped — may already exist)"

# Frontend
echo "[4/4] Starting frontend (port 3000)..."
cd "$REPO_DIR/frontend"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run dev -- --host 0.0.0.0 --port 3000 &
FRONTEND_PID=$!
echo "Frontend PID: $FRONTEND_PID"

echo ""
echo "=== Started! ==="
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8080"
echo "API docs: http://localhost:8080/docs"
echo ""
echo "Press Ctrl+C to stop."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
