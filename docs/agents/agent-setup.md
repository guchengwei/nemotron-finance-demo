# Agent Setup

## Purpose

Use this document as the operational entrypoint for working in this repo. It favors exact commands, current file locations, and verification steps over prose.

## Baseline Environment

- Python 3.12 for the backend virtual environment
- Node.js 20+ for the frontend toolchain
- Optional MeCab for Japanese text-analysis features
- Optional local vLLM server for real-LLM survey/report/follow-up flows

## Local Setup

### 1. Create or refresh `.env`

```bash
./setup-env.sh --preset local-mock
```

Use `local-vllm` instead of `local-mock` when a local model server is available.

### 2. Backend environment

```bash
cd backend
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
```

### 3. Frontend environment

```bash
cd frontend
npm install
```

## Startup Paths

### Full app

```bash
./start.sh
```

This installs Python deps, prepares the frontend bundle, starts FastAPI on port `8080`, and serves the SPA from the backend.

### Backend only

```bash
cd backend
. venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8080 --env-file ../.env
```

### Frontend only

```bash
cd frontend
npm run dev
```

## Real vLLM Requirement

The tracked parser plugin is here:

```text
backend/vllm_plugins/nemotron_nano_v2_reasoning_parser.py
```

Use it when starting vLLM:

```bash
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese \
  --host 0.0.0.0 --port 8000 \
  --trust-remote-code \
  --max-model-len 131072 \
  --max-num-seqs 64 \
  --gpu-memory-utilization 0.90 \
  --reasoning-parser-plugin backend/vllm_plugins/nemotron_nano_v2_reasoning_parser.py \
  --reasoning-parser nemotron_nano_v2 \
  --mamba-ssm-cache-dtype float32
```

## Verification Commands

```bash
cd backend && . venv/bin/activate && pytest -q
cd frontend && npm test
cd frontend && npm run test:e2e
cd frontend && npm run test:e2e:real-llm
```

## Working Rules For Agents

- Prefer a git worktree for implementation work when the main workspace is dirty.
- Treat `docs/` as agent-facing operational documentation; move historical notes into `docs/archive/`.
- Treat `backend/vllm_plugins/` as the canonical home for repo-owned vLLM extensions.
- Keep README files concise; put deep operational detail in `docs/`.
