# Nemotron Finance Demo

Japanese overview: [README.ja.md](README.ja.md)

Agent-first demo application for running financial-product survey simulations against the `nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese` model and the Nemotron Personas Japan dataset. The app supports mock-mode development, real vLLM-backed survey runs, report generation, follow-up chat, and persisted survey history.

## Current Capabilities

- Persona filtering and sampling from the Nemotron Personas dataset
- Multi-question survey runs with streaming answers
- Optional thinking-mode rendering for parser-backed vLLM responses
- Report generation with qualitative summaries and top-pick personas
- Follow-up chat per persona with persisted history replay
- Mock-mode and real-LLM E2E coverage

## Start Here

- Agent setup and local workflow: [`docs/agents/agent-setup.md`](docs/agents/agent-setup.md)
- Architecture and code map: [`docs/architecture/code-map.md`](docs/architecture/code-map.md)
- E2E execution plan: [`docs/testing/e2e-test-plan.md`](docs/testing/e2e-test-plan.md)
- Test matrix and commands: [`docs/testing/test-matrix.md`](docs/testing/test-matrix.md)
- Archived investigation notes and legacy plans: [`docs/archive/`](docs/archive/)

## Quick Start

### Mock Mode

```bash
./setup-env.sh --preset local-mock
./start.sh
```

Open `http://localhost:8080`.

### Real vLLM Mode

Use the tracked reasoning parser plugin that now lives in this repo:

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

./setup-env.sh --preset local-vllm
./start.sh
```

## Development Commands

```bash
# Backend tests
cd backend && . venv/bin/activate && pytest -q

# Frontend unit tests
cd frontend && npm test

# Frontend mock E2E
cd frontend && npm run test:e2e

# Frontend real-LLM E2E
cd frontend && npm run test:e2e:real-llm
```

## Repo Map

```text
backend/
  main.py                  FastAPI entrypoint and readiness endpoints
  routers/                 Personas, survey, report, follow-up, history APIs
  llm.py                   Streaming/generation orchestration
  report_parsing.py        Qualitative report parsing and normalization helpers
  vllm_plugins/            Repo-owned Nemotron reasoning parser plugin
  tests/                   Backend unit/integration/E2E coverage

frontend/
  src/components/          Main UI workflow components
  src/hooks/               Survey and SSE hooks
  src/config/              Shared survey preset/default config
  e2e/                     Playwright suites for mock and real-LLM runs
```

## Notes

- `start.sh` builds the frontend and serves it from the FastAPI backend.
- Real-LLM flows require a reachable local vLLM server and a valid `.env`.
- Historical notes were moved under `docs/archive/` so active docs stay operational.
