# CLAUDE.md — Nemotron Finance Demo

Persistent context for Claude Code sessions in this repo.

## Project

Financial survey simulation demo. FastAPI backend + React/TypeScript frontend, powered by `nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese`. Persona data from the Nemotron Personas Japan dataset.

## Key Design Decisions

- **Japanese-only persona strings are intentional.** Survey personas, UI labels, and survey content are in Japanese because the underlying model and dataset are Japanese. This is not an i18n gap.
- **Mock mode is for testing only.** `MOCK_VLLM=true` bypasses the real model and is used for local development and E2E tests, not for demo or production use.
- **Repo-owned reasoning parser.** `backend/vllm_plugins/nemotron_nano_v2_reasoning_parser.py` must be passed to vLLM at startup — it is not installed separately.

## Dev Commands

```bash
# Environment setup (testing)
./setup-env.sh --preset local-mock

# Environment setup (real vLLM)
./setup-env.sh --preset local-vllm

# Start full app (builds frontend, serves from FastAPI on :8080)
./start.sh

# Backend tests
cd backend && . venv/bin/activate && pytest -q

# Frontend unit tests
cd frontend && npm test

# Frontend E2E (mock)
cd frontend && npm run test:e2e

# Frontend E2E (real LLM)
cd frontend && npm run test:e2e:real-llm
```

## Real vLLM Startup

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

## Key File Layout

```text
backend/
  main.py             FastAPI entrypoint
  routers/            Personas, survey, report, follow-up, history APIs
  llm.py              Streaming/generation orchestration
  vllm_plugins/       Repo-owned reasoning parser plugin
  tests/              Backend unit/integration/E2E coverage

frontend/
  src/components/     Main UI workflow components
  src/hooks/          Survey and SSE hooks
  e2e/                Playwright suites (mock and real-LLM)

docs/
  agents/agent-setup.md       Full operational setup guide
  architecture/code-map.md    Architecture and code map
  testing/                    E2E test plan and test matrix
```

## Working Rules

- Use `docs/agents/agent-setup.md` as the primary operational reference.
- Keep README files concise; put deep operational detail in `docs/`.
- Prefer git worktrees for implementation work when the main workspace is dirty.
