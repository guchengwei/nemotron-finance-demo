# E2E Test Plan

## Goal

Cover the end-to-end survey workflow in two modes:

- mock mode for fast local regression checks
- real-LLM mode for parser-backed streaming, question generation, reporting, and follow-up behavior

## Mock-Mode Playwright

### Preconditions

- `frontend/node_modules` installed
- built frontend available through Playwright preview flow

### Command

```bash
cd frontend
npm run test:e2e
```

### Covered Flows

- filter panel behavior
- survey flow
- sidebar reset/history reset behavior

## Real-LLM Playwright

### Preconditions

- repo-root `.env` exists
- local vLLM reachable at the configured endpoint
- `MOCK_LLM=false`
- tracked parser plugin path is used by the running vLLM server

### Command

```bash
cd frontend
npm run test:e2e:real-llm
```

### Covered Flows

- startup and filter availability
- question generation against the live model
- single-person survey happy path
- interruption recovery during survey execution
- follow-up deep-dive flow
- quick demo history path

## Backend E2E Coverage

Use backend pytest for API-level mock and real-LLM coverage:

```bash
cd backend
. venv/bin/activate
pytest -q tests/test_e2e_mock.py tests/test_real_llm_e2e.py
```

## Failure Triage

- If mock Playwright fails, first confirm `npm run build` and `npm test` are green.
- If real-LLM Playwright fails, check `/health`, `/ready`, parser plugin path, and local vLLM reachability before changing app code.
- Keep screenshots, traces, and video artifacts from Playwright failures until the regression is explained.
