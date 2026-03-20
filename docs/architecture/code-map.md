# Code Map

## Runtime Entry Points

- `backend/main.py`: FastAPI app, readiness endpoints, frontend static serving
- `frontend/src/App.tsx`: top-level workflow shell
- `start.sh`: local full-stack startup path
- `setup-env.sh`: local `.env` generation and setup hints

## Backend

- `backend/routers/`: API boundaries for personas, survey, report, follow-up, and history
- `backend/llm.py`: survey/follow-up/report orchestration and stream handling
- `backend/report_parsing.py`: qualitative report JSON repair, extraction, and normalization
- `backend/vllm_plugins/nemotron_nano_v2_reasoning_parser.py`: tracked Nemotron reasoning parser plugin for vLLM
- `backend/persona_store.py` and `backend/db.py`: persona loading and persisted history storage

## Frontend

- `frontend/src/components/`: step screens and workflow UI
- `frontend/src/hooks/useSurvey.ts`: survey orchestration and streaming integration
- `frontend/src/api.ts`: REST and SSE client surface
- `frontend/src/store.ts`: global app state
- `frontend/src/config/surveyPresets.ts`: shared preset and default-question config

## Tests

- `backend/tests/`: backend unit, integration, and parser-related regression coverage
- `frontend/src/**/*.test.ts(x)`: frontend component/unit coverage
- `frontend/e2e/`: Playwright mock-mode and real-LLM flows

## Archive Policy

- Active operational docs live under `docs/agents/`, `docs/testing/`, and `docs/architecture/`
- Legacy plans, debug notes, and evidence snapshots live under `docs/archive/`
