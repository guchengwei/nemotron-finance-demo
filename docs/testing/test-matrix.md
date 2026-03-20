# Test Matrix

## Backend

| Scope | Command | Notes |
| --- | --- | --- |
| Full backend suite | `cd backend && . venv/bin/activate && pytest -q` | Current baseline includes parser, SSE, report, history, and text-analysis coverage |
| Mock E2E API coverage | `cd backend && . venv/bin/activate && pytest -q tests/test_e2e_mock.py` | Fast API-level end-to-end validation without real vLLM |
| Real-LLM API coverage | `cd backend && . venv/bin/activate && pytest -q tests/test_real_llm_e2e.py` | Requires reachable real model server |

## Frontend

| Scope | Command | Notes |
| --- | --- | --- |
| Unit/component suite | `cd frontend && npm test` | Vitest + jsdom |
| Focused unit file | `cd frontend && npx vitest run <path>` | Preferred during TDD steps |
| Mock Playwright | `cd frontend && npm run test:e2e` | Uses preview server on port `3000` |
| Real-LLM Playwright | `cd frontend && npm run test:e2e:real-llm` | Uses backend `8180` and frontend `3100` via dedicated config |

## Setup/Smoke Checks

| Scope | Command | Notes |
| --- | --- | --- |
| Full app smoke run | `./start.sh` | Builds frontend and serves through backend |
| Env generation | `./setup-env.sh --preset local-mock` | Creates repo-root `.env` |
| Real parser path check | `test -f backend/vllm_plugins/nemotron_nano_v2_reasoning_parser.py` | Confirms tracked plugin path exists |
