#!/usr/bin/env bash
# =============================================================================
# Nemotron Financial Survey Demo — Interactive Environment Setup
# Generates a .env file for your target deployment.
# Usage: ./setup-env.sh [--preset local-mock|local-vllm|k8s|docker]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"
REPO_DATA_DIR="$SCRIPT_DIR/data"
DEFAULT_PARQUET_PATH=""

# ── colours ──────────────────────────────────────────────────────────────────
bold=$'\033[1m'; green=$'\033[32m'; yellow=$'\033[33m'; cyan=$'\033[36m'; reset=$'\033[0m'

header() { echo; echo "${bold}${cyan}=== $* ===${reset}"; echo; }
info()   { echo "  ${green}✓${reset}  $*"; }
warn()   { echo "  ${yellow}⚠${reset}   $*"; }
ask()    { printf "  ${bold}%s${reset} [%s]: " "$1" "$2"; }

# ── parse preset flag ────────────────────────────────────────────────────────
PRESET="${1:-}"
[[ "$PRESET" == --preset=* ]] && PRESET="${PRESET#--preset=}"
[[ "$PRESET" == "--preset" ]] && { PRESET="${2:-}"; shift; } 2>/dev/null || true

# ── greeting ─────────────────────────────────────────────────────────────────
clear
echo "${bold}Nemotron Financial Survey Demo — Environment Setup${reset}"
echo "Generates .env for your deployment environment."
echo
echo "Presets:"
echo "  1) local-mock   — No GPU, mock LLM responses (dev / demo offline)"
echo "  2) local-vllm   — GPU on this machine, vLLM running locally"
echo "  3) k8s          — Kubernetes / Run:ai pod (H100, port-forward access)"
echo "  4) docker       — Docker Compose stack"
echo "  5) custom       — Enter every value manually"
echo

# ── select preset ────────────────────────────────────────────────────────────
if [[ -z "$PRESET" ]]; then
  ask "Select preset (1-5)" "2"
  read -r choice
  case "$choice" in
    1) PRESET="local-mock" ;;
    2) PRESET="local-vllm" ;;
    3) PRESET="k8s" ;;
    4) PRESET="docker" ;;
    *) PRESET="custom" ;;
  esac
fi

header "Preset: $PRESET"

# ── defaults per preset ───────────────────────────────────────────────────────
case "$PRESET" in
  local-mock)
    DEFAULT_VLLM_URL="http://localhost:8000/v1"
    DEFAULT_VLLM_MODEL="nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    DEFAULT_MOCK_LLM="true"
    DEFAULT_DATA_DIR="$REPO_DATA_DIR"
    DEFAULT_PARQUET="$DEFAULT_PARQUET_PATH"
    DEFAULT_BACKEND_HOST="127.0.0.1"
    DEFAULT_BACKEND_PORT="8080"
    DEFAULT_CONCURRENCY="4"
    ;;
  local-vllm)
    DEFAULT_VLLM_URL="http://localhost:8000/v1"
    DEFAULT_VLLM_MODEL="nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    DEFAULT_MOCK_LLM="false"
    DEFAULT_DATA_DIR="$REPO_DATA_DIR"
    DEFAULT_PARQUET="$DEFAULT_PARQUET_PATH"
    DEFAULT_BACKEND_HOST="127.0.0.1"
    DEFAULT_BACKEND_PORT="8080"
    DEFAULT_CONCURRENCY="4"
    ;;
  k8s)
    DEFAULT_VLLM_URL="http://localhost:8000/v1"
    DEFAULT_VLLM_MODEL="nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    DEFAULT_MOCK_LLM="false"
    DEFAULT_DATA_DIR="$REPO_DATA_DIR"
    DEFAULT_PARQUET="$DEFAULT_PARQUET_PATH"
    DEFAULT_BACKEND_HOST="0.0.0.0"
    DEFAULT_BACKEND_PORT="8080"
    DEFAULT_CONCURRENCY="4"
    ;;
  docker)
    DEFAULT_VLLM_URL="http://vllm:8000/v1"
    DEFAULT_VLLM_MODEL="nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    DEFAULT_MOCK_LLM="false"
    DEFAULT_DATA_DIR="$REPO_DATA_DIR"
    DEFAULT_PARQUET="$DEFAULT_PARQUET_PATH"
    DEFAULT_BACKEND_HOST="0.0.0.0"
    DEFAULT_BACKEND_PORT="8080"
    DEFAULT_CONCURRENCY="4"
    ;;
  *)
    DEFAULT_VLLM_URL="http://localhost:8000/v1"
    DEFAULT_VLLM_MODEL="nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    DEFAULT_MOCK_LLM="false"
    DEFAULT_DATA_DIR="$REPO_DATA_DIR"
    DEFAULT_PARQUET="$DEFAULT_PARQUET_PATH"
    DEFAULT_BACKEND_HOST="0.0.0.0"
    DEFAULT_BACKEND_PORT="8080"
    DEFAULT_CONCURRENCY="4"
    ;;
esac

# ── interactive prompts ───────────────────────────────────────────────────────
header "LLM Settings"

ask "vLLM server URL" "$DEFAULT_VLLM_URL"
read -r VLLM_URL; VLLM_URL="${VLLM_URL:-$DEFAULT_VLLM_URL}"

ask "Model name" "$DEFAULT_VLLM_MODEL"
read -r VLLM_MODEL; VLLM_MODEL="${VLLM_MODEL:-$DEFAULT_VLLM_MODEL}"

ask "Mock LLM (true = no GPU needed)" "$DEFAULT_MOCK_LLM"
read -r MOCK_LLM; MOCK_LLM="${MOCK_LLM:-$DEFAULT_MOCK_LLM}"

ask "LLM temperature" "0.7"
read -r LLM_TEMPERATURE; LLM_TEMPERATURE="${LLM_TEMPERATURE:-0.7}"

ask "Max tokens per answer" "512"
read -r LLM_MAX_TOKENS; LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-512}"

ask "Max tokens for report generation" "4096"
read -r REPORT_MAX_TOKENS; REPORT_MAX_TOKENS="${REPORT_MAX_TOKENS:-4096}"

ask "Max tokens for deep-dive follow-up chat responses" "2048"
read -r FOLLOWUP_MAX_TOKENS; FOLLOWUP_MAX_TOKENS="${FOLLOWUP_MAX_TOKENS:-2048}"

ask "Concurrent LLM calls (semaphore)" "$DEFAULT_CONCURRENCY"
read -r LLM_CONCURRENCY; LLM_CONCURRENCY="${LLM_CONCURRENCY:-$DEFAULT_CONCURRENCY}"

header "Data Settings"

ask "Data directory (history DB + parquet)" "$DEFAULT_DATA_DIR"
read -r DATA_DIR; DATA_DIR="${DATA_DIR:-$DEFAULT_DATA_DIR}"

ask "Parquet path (blank = auto-download from HuggingFace)" "$DEFAULT_PARQUET"
read -r PERSONA_PARQUET_PATH; PERSONA_PARQUET_PATH="${PERSONA_PARQUET_PATH:-$DEFAULT_PARQUET}"

HISTORY_DB_PATH="$DATA_DIR/history.db"

info "HISTORY_DB    = $HISTORY_DB_PATH"

header "Server Settings"

ask "Backend bind host" "$DEFAULT_BACKEND_HOST"
read -r BACKEND_HOST; BACKEND_HOST="${BACKEND_HOST:-$DEFAULT_BACKEND_HOST}"

ask "Backend port" "$DEFAULT_BACKEND_PORT"
read -r BACKEND_PORT; BACKEND_PORT="${BACKEND_PORT:-$DEFAULT_BACKEND_PORT}"

# ── write .env ────────────────────────────────────────────────────────────────
header "Writing $ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "$ENV_FILE.bak"
  warn "Existing .env backed up to .env.bak"
fi

cat > "$ENV_FILE" <<EOF
# Generated by setup-env.sh — preset: $PRESET
# $(date -u +"%Y-%m-%dT%H:%M:%SZ")

# LLM
VLLM_URL=$VLLM_URL
VLLM_MODEL=$VLLM_MODEL
MOCK_LLM=$MOCK_LLM
LLM_TEMPERATURE=$LLM_TEMPERATURE
LLM_MAX_TOKENS=$LLM_MAX_TOKENS
REPORT_MAX_TOKENS=$REPORT_MAX_TOKENS
FOLLOWUP_MAX_TOKENS=$FOLLOWUP_MAX_TOKENS
LLM_CONCURRENCY=$LLM_CONCURRENCY

# Data
DATA_DIR=$DATA_DIR
PERSONA_PARQUET_PATH=$PERSONA_PARQUET_PATH
HISTORY_DB_PATH=$HISTORY_DB_PATH

# Server
BACKEND_HOST=$BACKEND_HOST
BACKEND_PORT=$BACKEND_PORT
CORS_ORIGINS=["*"]
EOF

info ".env written."

# ── next-step hints ───────────────────────────────────────────────────────────
header "Next Steps"

case "$PRESET" in
  local-mock)
    echo "  Mock mode — no GPU required."
    echo
    echo "  Start the app:"
    echo "    cd $(dirname "$SCRIPT_DIR") || cd $SCRIPT_DIR"
    echo "    ./start.sh"
    ;;
  local-vllm)
    echo "  Make sure vLLM is running before starting the app:"
    echo
    echo "    vllm serve $VLLM_MODEL \\"
    echo "      --host 0.0.0.0 --port 8000 \\"
    echo "      --max-model-len 8192 --gpu-memory-utilization 0.9"
    echo
    echo "  Then:"
    echo "    ./start.sh"
    ;;
  k8s)
    echo "  Inside a Run:ai / K8s pod:"
    echo
    echo "    # Launch vLLM (background)"
    echo "    vllm serve $VLLM_MODEL \\"
    echo "      --host 0.0.0.0 --port 8000 \\"
    echo "      --max-model-len 8192 --gpu-memory-utilization 0.9 &"
    echo
    echo "    # Wait for model to load, then:"
    echo "    ./start.sh"
    echo
    echo "  Port-forward from your laptop:"
    echo "    kubectl port-forward pod/<pod-name> 8080:8080"
    ;;
  docker)
    echo "  Start the full stack:"
    echo "    docker compose up"
    ;;
esac

echo
echo "${bold}${green}Done!${reset}  Edit $ENV_FILE to make any manual adjustments."
echo
