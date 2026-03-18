# Nemotron Financial Survey Demo

A web application for event booth demos showcasing **NVIDIA Nemotron-Nano-9B-v2-Japanese** with the **Nemotron-Personas-Japan** dataset (1M Japanese personas). Simulates AI-driven financial market research surveys — select personas by demographic profile, run a multi-question survey with live streaming responses, and generate an analytical report.

![NVIDIA dark theme UI — persona selection, live survey streaming, report dashboard]

## Features

- **1 Million Personas** — filter by age, sex, prefecture, occupation, education, financial literacy
- **Live Survey Streaming** — watch each persona answer questions in real time with SSE
- **Thinking Mode** — collapsible `<think>` reasoning blocks per answer
- **Report Dashboard** — score overview, demographic breakdown charts, top picks
- **Follow-up Chat** — deep-dive conversations with individual personas post-survey
- **Survey History** — all runs persisted, reloadable from the sidebar
- **Mock Mode** — runs offline without a GPU for development and demo prep

---

## Architecture

```
┌─────────────────────┐     SSE / REST      ┌──────────────────────┐
│  Frontend           │ ──────────────────► │  Backend             │
│  Vite + React 18    │                     │  FastAPI + Python    │
│  TypeScript         │ ◄────────────────── │  Port 8080           │
│  Tailwind CSS       │                     │                      │
│  Recharts + Zustand │                     │  Pandas DataFrame    │
│  Served via backend │                     │  Deprecated SQLite   │
│                     │                     │  history store only  │
└─────────────────────┘                     └──────────┬───────────┘
                                                       │ OpenAI API
                                                       ▼
                                            ┌──────────────────────┐
                                            │  vLLM                │
                                            │  Nemotron-Nano-9B-v2 │
                                            │  Port 8000           │
                                            └──────────────────────┘
```

---

## Quick Start

### Option A — Mock Mode (no GPU required)

Ideal for development, demo preparation, or any environment without a GPU.

```bash
git clone https://github.com/guchengwei/nemotron-finance-demo.git
cd nemotron-finance-demo

# Interactive env setup — choose preset "1) local-mock"
./setup-env.sh

# Start the backend and build the frontend bundle
./start.sh
```

Open http://localhost:8080

### Option B — Local GPU with vLLM

Requires an NVIDIA GPU with ≥ 24 GB VRAM (tested on H100 80 GB).

```bash
# 1. Install vLLM (if not already installed)
pip install vllm

# 2. Launch vLLM (downloads ~18 GB model on first run)
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese \
  --host 0.0.0.0 --port 8000 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.9 \
  --mamba_ssm_cache_dtype float32 \
  --trust-remote-code

# 3. Configure environment — choose preset "2) local-vllm"
./setup-env.sh

# 4. Start the app
./start.sh
```

---

## Environment Setup

### Interactive (recommended)

```bash
./setup-env.sh
```

Guides you through all settings and writes `.env`. Presets:

| Preset | Description |
|--------|-------------|
| `local-mock` | No GPU, mock responses, repo-local data directory `./data` |
| `local-vllm` | GPU on localhost, vLLM on port 8000; same default repo-local data paths |
| `k8s` | Kubernetes / Run:ai pod; same default paths, different host/runtime settings |
| `docker` | Docker Compose stack; same default paths, different host/runtime settings |
| `custom` | Manual entry for every setting |

### Manual

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
$EDITOR .env
```

### Full Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_URL` | `http://localhost:8000/v1` | OpenAI-compatible vLLM endpoint |
| `VLLM_MODEL` | `nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese` | Model name registered in vLLM |
| `MOCK_LLM` | `false` | `true` = offline mock mode, no vLLM needed |
| `LLM_TEMPERATURE` | `0.7` | Generation temperature |
| `LLM_MAX_TOKENS` | `512` | Max tokens per survey answer |
| `REPORT_MAX_TOKENS` | `4096` | Max tokens for report generation |
| `FOLLOWUP_MAX_TOKENS` | `2048` | Max tokens for deep-dive follow-up chat responses |
| `LLM_CONCURRENCY` | `4` | Simultaneous LLM calls (asyncio semaphore) |
| `DATA_DIR` | `./data` | Default directory for the deprecated history store file and persona parquet data, resolved relative to the repo |
| `PERSONA_PARQUET_PATH` | _(blank)_ | Default is blank for all presets; blank = auto-download into the default data location |
| `HISTORY_DB_PATH` | `$DATA_DIR/history.db` | Deprecated SQLite-backed survey history store path |
| `BACKEND_HOST` | `0.0.0.0` | Uvicorn bind host |
| `BACKEND_PORT` | `8080` | Uvicorn port |
| `CORS_ORIGINS` | `["*"]` | JSON array of allowed CORS origins |

---

## Kubernetes / Run:ai Setup

This is the primary deployment target — an H100 pod with the model served locally.

### 1. Submit a Run:ai job

```yaml
# runai-job.yaml
apiVersion: run.ai/v1
kind: RunaiJob
metadata:
  name: nemotron-finance-demo
spec:
  template:
    spec:
      containers:
        - name: demo
          image: nvcr.io/nvidia/pytorch:24.03-py3
          resources:
            limits:
              nvidia.com/gpu: "1"
          volumeMounts:
            - name: data-vol
              mountPath: /genai/finance/data
      volumes:
        - name: data-vol
          persistentVolumeClaim:
            claimName: finance-demo-pvc
```

### 2. Inside the pod

```bash
# Clone the repo
git clone https://github.com/guchengwei/nemotron-finance-demo.git /genai/finance
cd /genai/finance

# Install Node.js 20+ if not present
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Configure for K8s environment
./setup-env.sh --preset k8s

# Launch vLLM in background
vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese \
  --host 0.0.0.0 --port 8000 \
  --max-model-len 16384 \
  --gpu-memory-utilization 0.9 \
  --mamba_ssm_cache_dtype float32 \
  --dtype bfloat16 \
  --trust-remote-code &

# Wait for model load (check: curl http://localhost:8000/v1/models)

# Start the demo app
./start.sh
```

### 3. Port-forward from laptop

```bash
kubectl port-forward pod/<pod-name> 8080:8080

# or with Run:ai CLI
runai exec <job-name> -- bash
```

Open http://localhost:8080

---

## Docker Compose Setup

> Note: A `docker-compose.yml` is provided for local development. GPU passthrough requires NVIDIA Container Toolkit.

```bash
# With GPU (requires nvidia-container-toolkit)
docker compose up

# Mock mode — no GPU
MOCK_LLM=true docker compose up app
```

`docker-compose.yml` services:
- `app` — FastAPI backend serving the built frontend
- `vllm` — vLLM server (requires GPU, optional with mock mode)

---

## First Run — Persona Data

On startup the backend loads the persona parquet file into an in-memory pandas DataFrame:

1. **Auto-download** (no `PERSONA_PARQUET_PATH` set): downloads the dataset from HuggingFace Hub (`nvidia/Nemotron-Personas-Japan`, ~1.7 GB parquet) and loads all 1M rows into memory.
2. **From local parquet** (`PERSONA_PARQUET_PATH` set): loads directly from the specified file into memory.

This one-time download takes 5–15 minutes. On subsequent starts the parquet file is loaded directly from disk into memory (no re-download needed).

To pre-download before the event:
```bash
# Manually trigger parquet download/init
cd backend
source venv/bin/activate
python -c "import asyncio; from db import init_db; asyncio.run(init_db())"
```

---

## Scripts

### Seed demo history

Pre-populate 3 completed survey runs so the history sidebar is non-empty on arrival:

```bash
cd backend && source venv/bin/activate
python scripts/seed_demo_history.py
```

Runs are seeded idempotently (won't duplicate on re-run).

### Generate financial extensions

Enrich a batch of personas with AI-generated financial profiles (investment experience, concerns, income bracket):

```bash
cd backend && source venv/bin/activate
python scripts/generate_financial_extensions.py --count 10000
```

Requires vLLM running (or set `MOCK_LLM=true` in `.env` first).

---

## Development

### Backend only

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
MOCK_LLM=true uvicorn main:app --reload --port 8080 --env-file ../.env
```

API docs: http://localhost:8080/docs

### Frontend only

```bash
cd frontend
npm install
npm run dev   # proxies /api → http://localhost:8080
```

### TypeScript build check

```bash
cd frontend && npm run build
```

---

## Project Structure

```
nemotron-finance-demo/
├── .env.example              # Configuration template
├── .env                      # Local config (gitignored)
├── setup-env.sh              # Interactive env setup script
├── start.sh                  # One-command startup
│
├── backend/
│   ├── main.py               # FastAPI app + lifespan
│   ├── config.py             # Pydantic Settings
│   ├── db.py                 # Deprecated SQLite-backed history store helpers
│   ├── llm.py                # vLLM client, mock mode, stream splitting
│   ├── models.py             # Pydantic request/response models
│   ├── prompts.py            # All LLM prompt templates (Japanese)
│   ├── requirements.txt
│   └── routers/
│       ├── personas.py       # GET /api/personas/filters|sample
│       ├── survey.py         # POST /api/survey/run  (SSE)
│       ├── report.py         # POST /api/report/generate
│       ├── followup.py       # POST /api/followup/ask  (SSE)
│       └── history.py        # GET|DELETE /api/history
│   └── scripts/
│       ├── seed_demo_history.py
│       └── generate_financial_extensions.py
│
└── frontend/
    ├── index.html
    ├── vite.config.ts
    └── src/
        ├── App.tsx
        ├── api.ts
        ├── store.ts          # Zustand global state
        ├── types.ts
        ├── hooks/
        │   ├── useSurvey.ts  # SSE survey orchestration
        │   └── useSSE.ts
        ├── utils/
        │   ├── scoreParser.ts
        │   └── chartHelpers.ts
        └── components/
            ├── Layout.tsx / Sidebar.tsx / StepIndicator.tsx
            ├── FilterPanel.tsx / PersonaCards.tsx / PersonaDetailModal.tsx
            ├── SurveyConfig.tsx / SurveyRunner.tsx / SurveyProgress.tsx
            ├── ReportDashboard.tsx / DemographicCharts.tsx / TopPickCard.tsx
            └── FollowUpChat.tsx
```

---

## Dataset

**Nemotron-Personas-Japan** (`nvidia/Nemotron-Personas-Japan` on HuggingFace Hub)

- 1,000,000 synthetic Japanese personas
- 23 columns including: name (extracted from `persona` text), age, sex (`男`/`女`), prefecture, region, occupation, `education_level`, `career_goals_and_ambitions`, skills, hobbies, cultural background, and more
- Financial extension table (`persona_financial_context`) optionally enriched via the generate script

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

The Nemotron-Personas-Japan dataset and Nemotron-Nano-9B-v2-Japanese model are subject to their respective NVIDIA licenses on HuggingFace Hub.
