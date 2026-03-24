# Nemotron Finance Demo

Japanese overview: [README.ja.md](README.ja.md)

Demo application for financial-product survey simulations powered by the `nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese` model and the Nemotron Personas Japan dataset. It is designed for market-research and event-demo workflows: select personas by demographic profile, run multi-question surveys with live streaming answers, generate a report, and continue with follow-up chat backed by persisted survey history.

## Features

- **Persona Filtering and Sampling**: narrow the Nemotron Personas dataset by demographic and profile fields, then sample respondents for a run
- **Live Survey Streaming**: stream each persona's answer in real time during multi-question survey execution
- **Thinking Mode**: render parser-backed reasoning output for vLLM responses when the model emits it
- **Report Generation**: produce qualitative summaries, polarity-aware insights, and top-pick personas after the survey
- **Follow-up Chat**: continue the conversation with individual personas after the report
- **Persisted Survey History**: reload prior runs and follow-up state from the history store
- **Mock and Real vLLM Modes**: develop offline or run against a local vLLM deployment with the repo-owned reasoning parser plugin

## Architecture

```text
┌─────────────────────┐    SSE / REST APIs    ┌─────────────────────────────┐
│ Frontend            │ ────────────────────► │ Backend                     │
│ React + TypeScript  │                       │ FastAPI + Python            │
│ Vite-built bundle   │ ◄──────────────────── │ Survey/report/follow-up     │
│ Served by backend   │                       │ orchestration               │
└─────────────────────┘                       │ Persona parquet loading     │
                                              │ SQLite history persistence  │
                                              └──────────────┬──────────────┘
                                                             │ OpenAI-compatible API
                                                             ▼
                                              ┌─────────────────────────────┐
                                              │ vLLM                        │
                                              │ Nemotron Nano v2 Japanese   │
                                              │ Repo-owned reasoning parser │
                                              └─────────────────────────────┘
```

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
