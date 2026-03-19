# Nemotron Finance Demo — TDD Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 10 known issues in the Nemotron Finance Demo — database startup failures, LLM integration errors, broken UI interactions, laggy performance, and bad visual theme — so the demo runs end-to-end in mock mode.

**Architecture:** Backend fixes focus on config path resolution and SSE error propagation. Frontend fixes address loading states, button responsiveness, streaming visibility, and performance. Theme redesign replaces the NVIDIA dark palette with a professional finance-grade design. All changes are TDD: failing test first, minimal fix, verify, commit.

**Tech Stack:** Python 3.12 / FastAPI / SQLite / Pydantic Settings (backend); React 18 / TypeScript / Vite / Tailwind CSS / Zustand / Vitest (frontend)

---

## File Structure

### Backend Changes
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/config.py` | Anchor `.env` resolution to repo root |
| Modify | `start.sh` | Export env vars before seed script |
| Modify | `backend/main.py` | Add LLM health to `/health` |
| Modify | `backend/routers/survey.py` | Emit per-question error SSE events on LLM failure |
| Modify | `backend/routers/followup.py` | Wrap stream in try/except, emit error event |
| Modify | `backend/llm.py` | Add `check_llm_health()` |
| Create | `backend/tests/test_config_paths.py` | Test .env resolution from any CWD |
| Create | `backend/tests/test_seed_history.py` | Test seed script finds DB at configured path |
| Create | `backend/tests/test_ready_endpoint.py` | Test /ready and /health responses |
| Create | `backend/tests/test_survey_sse.py` | Test SSE error event emission |
| Create | `backend/tests/test_followup_sse.py` | Test followup error handling |

### Frontend Changes
| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/store.ts` | Add `dbReady`, `llmStatus` state |
| Modify | `frontend/src/api.ts` | Add `checkReady()` polling, `checkHealth()` |
| Modify | `frontend/src/App.tsx` | Gate on readiness, show loading/error states |
| Modify | `frontend/src/components/Sidebar.tsx` | Disable "新規調査" during loading |
| Modify | `frontend/src/components/SurveyConfig.tsx` | Fix question generation error handling |
| Modify | `frontend/src/components/SurveyRunner.tsx` | Add progress bar, error display, memoize list items |
| Modify | `frontend/src/hooks/useSurvey.ts` | Batch SSE chunk updates for performance |
| Modify | `frontend/src/index.css` | New theme animations/transitions |
| Modify | `frontend/tailwind.config.js` | New professional color palette |
| Modify | `frontend/vite.config.ts` | Add manualChunks for code splitting |
| Create | `frontend/src/components/__tests__/survey-config.test.tsx` | Test question generation UX |
| Create | `frontend/src/components/__tests__/loading-states.test.tsx` | Test readiness gating |

---

## Task 1: Fix Config Path Resolution (Issue 2 Root Cause)

**Problem:** `config.py` uses `model_config = {"env_file": ".env"}` (relative to CWD). When the backend or seed script runs from `backend/`, it can't find `$REPO_ROOT/.env`, so defaults like `db_path="./data/personas.db"` resolve to `backend/data/personas.db` — which doesn't exist.

**Files:**
- Create: `backend/tests/test_config_paths.py`
- Modify: `backend/config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_config_paths.py
import os
from pathlib import Path
from unittest.mock import patch

import pytest


def test_settings_resolves_db_path_under_repo_data_dir():
    """db_path must resolve under the repo's data/ dir, not under backend/."""
    repo_root = Path(__file__).resolve().parents[2]
    expected_data_dir = repo_root / "data"

    # Clear env vars so defaults kick in
    env_clear = {k: "" for k in ("DB_PATH", "DATA_DIR", "HISTORY_DB_PATH")}
    with patch.dict(os.environ, env_clear, clear=False):
        import importlib
        import config as cfg
        importlib.reload(cfg)
        resolved = Path(cfg.settings.db_path).resolve()

    assert str(resolved).startswith(str(expected_data_dir)), (
        f"db_path {resolved} is not under {expected_data_dir}"
    )


def test_env_file_found_from_backend_cwd():
    """Settings must find .env even when CWD is backend/."""
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env"
    assert env_file.exists(), f".env not found at {env_file}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_config_paths.py -v`
Expected: FAIL — db_path resolves under backend/data/ or default relative path

- [ ] **Step 3: Fix config.py to anchor paths to repo root**

Current `config.py` structure uses a plain dict for `model_config` and has no path resolution. Replace with:

```python
"""Application configuration loaded from environment variables."""

import json
from pathlib import Path
from typing import List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    # LLM
    vllm_url: str = "http://localhost:8000/v1"
    vllm_model: str = "nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese"
    mock_llm: bool = False
    llm_temperature: float = 0.7
    llm_max_tokens: int = 512
    report_max_tokens: int = 4096
    llm_concurrency: int = 4

    # Data paths
    data_dir: str = "./data"
    persona_parquet_path: str = ""
    persona_hf_dataset: str = "nvidia/Nemotron-Personas-Japan"
    db_path: str = "./data/personas.db"
    history_db_path: str = "./data/history.db"

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8080
    cors_origins: str = '["*"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.cors_origins)

    model_config = {"env_file": str(_ENV_FILE), "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def _resolve_paths(self) -> "Settings":
        """Resolve relative paths against repo root, not CWD."""
        for field in ("data_dir", "db_path", "history_db_path", "persona_parquet_path"):
            val = getattr(self, field)
            if val:
                p = Path(val)
                if not p.is_absolute():
                    object.__setattr__(self, field, str(_REPO_ROOT / p))
        return self


settings = Settings()
```

Key changes:
- `_REPO_ROOT` is computed from `__file__`, so it's stable regardless of CWD
- `env_file` points to the repo root `.env` via absolute path
- `_resolve_paths` model_validator converts any relative `data_dir`/`db_path`/`history_db_path` to absolute paths anchored at repo root
- Uses `object.__setattr__` because Pydantic models may be frozen

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_config_paths.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/tests/test_config_paths.py
git commit -m "fix: anchor config paths to repo root, not CWD"
```

---

## Task 2: Fix start.sh Seed Script Environment (Issue 2 Direct Cause)

**Problem:** `start.sh` runs `seed_demo_history.py` in a separate Python process without the env vars that uvicorn gets via `--env-file`. After Task 1, config.py finds `.env` by itself, but we should also export env vars for robustness.

**Files:**
- Create: `backend/tests/test_seed_history.py`
- Modify: `start.sh`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_seed_history.py
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from config import settings
from db import PERSONA_DDL, _create_history_db


@pytest.fixture()
def history_db(tmp_path):
    """Create a minimal history DB for seed tests."""
    db_path = str(tmp_path / "history.db")
    with patch.object(settings, "history_db_path", db_path):
        _create_history_db()
    return db_path


@pytest.fixture()
def persona_db(tmp_path):
    """Create a minimal persona DB with one row."""
    db_path = str(tmp_path / "personas.db")
    conn = sqlite3.connect(db_path)
    conn.executescript(PERSONA_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("test-uuid", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()
    return db_path


def test_seed_history_opens_configured_db(persona_db, history_db):
    """seed_history must use settings.db_path, not a relative default."""
    with patch.object(settings, "db_path", persona_db), \
         patch.object(settings, "history_db_path", history_db):
        from scripts.seed_demo_history import seed_history
        import importlib
        import scripts.seed_demo_history as mod
        importlib.reload(mod)
        mod.seed_history()

    conn = sqlite3.connect(history_db)
    count = conn.execute("SELECT COUNT(*) FROM survey_runs").fetchone()[0]
    conn.close()
    assert count > 0, "Seeding should have created at least one survey run"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_seed_history.py -v`
Expected: FAIL with OperationalError or assertion error

- [ ] **Step 3: Fix start.sh to export env vars before seed**

In `start.sh`, replace the seed section (lines 53-61):

```bash
# Seed demo history
echo "[3/4] Seeding demo history..."
cd "$REPO_DIR/backend"
# Export .env so seed script inherits the same config as uvicorn
set -a
. "$REPO_DIR/.env"
set +a
python -c "
import os, sys
sys.path.insert(0, '.')
from scripts.seed_demo_history import seed_history
seed_history()
" || echo "  (Seeding skipped — may already exist)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_seed_history.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add start.sh backend/tests/test_seed_history.py
git commit -m "fix: export .env before seed script so it finds the DB"
```

---

## Task 3: Fix Startup Readiness & LLM Health Check (Issues 4, 10)

**Problem:** (a) No LLM health check — if vLLM isn't running, the demo silently fails on every LLM call. (b) Frontend has no way to know LLM status. The `/health` endpoint returns `mock_llm` but not whether the LLM is actually reachable.

**Files:**
- Create: `backend/tests/test_ready_endpoint.py`
- Modify: `backend/main.py`
- Modify: `backend/llm.py`

- [ ] **Step 1: Write failing tests for /health**

```python
# backend/tests/test_ready_endpoint.py
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


@pytest.fixture()
def app_client():
    """Client against the real app without lifespan (DB not initialized)."""
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


def test_health_returns_llm_reachable_field(app_client):
    resp = app_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "mock_llm" in data
    assert "llm_reachable" in data


def test_ready_returns_503_when_db_not_loaded(app_client):
    main._db_ready.clear()
    resp = app_client.get("/ready")
    assert resp.status_code == 503
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_ready_endpoint.py -v`
Expected: FAIL — `llm_reachable` not in /health response

- [ ] **Step 3: Add check_llm_health to llm.py**

Add at the end of `backend/llm.py`:

```python
async def check_llm_health() -> bool:
    """Return True if vLLM endpoint is reachable, False otherwise."""
    if settings.mock_llm:
        return True
    try:
        client = get_client()
        await client.models.list()
        return True
    except Exception:
        return False
```

- [ ] **Step 4: Update /health endpoint in main.py**

Replace the existing `/health` endpoint:

```python
@app.get("/health")
async def health():
    from llm import check_llm_health
    reachable = await check_llm_health()
    return {
        "status": "ok",
        "mock_llm": settings.mock_llm,
        "llm_reachable": reachable,
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_ready_endpoint.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/llm.py backend/tests/test_ready_endpoint.py
git commit -m "feat: add LLM health check to /health endpoint"
```

---

## Task 4: Fix Survey SSE Per-Question Error Propagation (Issues 6, 9)

**Problem:** In `_run_persona_survey()` (survey.py:71), the inner try/except (lines 103-119) catches per-question LLM errors and silently replaces the answer with a fallback message. No SSE event is emitted for the error. The **outer** except (lines 153-158) already emits `persona_error` for full persona failures, but individual question failures are invisible to the frontend.

**Files:**
- Create: `backend/tests/test_survey_sse.py`
- Modify: `backend/routers/survey.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_survey_sse.py
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from routers import survey


def _setup_dbs(tmp_path):
    """Create minimal persona + history DBs."""
    persona_db = str(tmp_path / "personas.db")
    history_db = str(tmp_path / "history.db")

    from db import PERSONA_DDL, _create_history_db
    conn = sqlite3.connect(persona_db)
    conn.executescript(PERSONA_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()

    with patch.object(settings, "history_db_path", history_db):
        _create_history_db()

    return persona_db, history_db


@pytest.fixture()
def survey_client(tmp_path):
    persona_db, history_db = _setup_dbs(tmp_path)
    original_db = settings.db_path
    original_hist = settings.history_db_path
    settings.db_path = persona_db
    settings.history_db_path = history_db

    app = FastAPI()
    app.include_router(survey.router)
    with TestClient(app) as c:
        yield c

    settings.db_path = original_db
    settings.history_db_path = original_hist


def test_survey_emits_error_event_on_per_question_llm_failure(survey_client):
    """When LLM fails on a question, SSE must include an error indicator."""

    async def mock_stream(*args, **kwargs):
        raise ConnectionError("vLLM unreachable")
        yield  # make it a generator

    with patch("routers.survey.stream_survey_answer", side_effect=mock_stream):
        resp = survey_client.post(
            "/api/survey/run",
            json={
                "persona_ids": ["p1"],
                "survey_theme": "テスト",
                "questions": ["テスト質問"],
            },
            headers={"Accept": "text/event-stream"},
        )

    # Parse SSE events
    events = []
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            events.append(line[7:].strip())

    # Must have either persona_error or a persona_answer with error indicator
    has_error_signal = "persona_error" in events
    assert has_error_signal, (
        f"Expected persona_error event when LLM fails per-question, got: {events}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_survey_sse.py -v`
Expected: FAIL — the inner except catches and swallows the error, the persona still completes "successfully" with a fallback answer, no `persona_error` emitted

- [ ] **Step 3: Fix survey.py inner except to emit error event**

In `backend/routers/survey.py`, in the `_run_persona_survey()` function, modify the inner except block (around line 117-119). Change:

```python
            except Exception as e:
                logger.error("LLM error for persona %s q%d: %s", persona_id, q_idx, e)
                full_answer = "（回答を取得できませんでした）"
```

To:

```python
            except Exception as e:
                logger.error("LLM error for persona %s q%d: %s", persona_id, q_idx, e)
                full_answer = "（回答を取得できませんでした）"
                await event_queue.put({
                    "event": "persona_error",
                    "data": {
                        "persona_uuid": persona_id,
                        "question_index": q_idx,
                        "error": str(e),
                    },
                })
```

Note: uses `persona_uuid` (not `persona_id`) in the data key to match the existing SSE event convention used throughout the file.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_survey_sse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/survey.py backend/tests/test_survey_sse.py
git commit -m "fix: emit persona_error SSE events on per-question LLM failures"
```

---

## Task 5: Fix Followup SSE Error Handling (Issue 6)

**Problem:** `followup.py` has no try/except around the `stream_followup_answer()` call. If the LLM stream fails, the SSE generator stops without emitting a `done` or `error` event, causing the frontend to hang indefinitely.

**Files:**
- Create: `backend/tests/test_followup_sse.py`
- Modify: `backend/routers/followup.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_followup_sse.py
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import PERSONA_DDL, _create_history_db
from routers import followup


@pytest.fixture()
def followup_client(tmp_path):
    history_db = str(tmp_path / "history.db")
    persona_db = str(tmp_path / "personas.db")

    conn = sqlite3.connect(persona_db)
    conn.executescript(PERSONA_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()

    orig_db = settings.db_path
    orig_hist = settings.history_db_path
    settings.db_path = persona_db
    settings.history_db_path = history_db

    _create_history_db()

    # Seed a survey run so followup has context
    hist_conn = sqlite3.connect(history_db)
    hist_conn.execute(
        "INSERT INTO survey_runs (id, created_at, survey_theme, questions_json,"
        " filter_config_json, persona_count, status)"
        " VALUES (?, datetime('now'), ?, ?, '{}', 1, 'completed')",
        ("run1", "テスト", json.dumps(["質問1"])),
    )
    hist_conn.execute(
        "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary,"
        " persona_full_json, question_index, question_text, answer, score, created_at)"
        " VALUES (?, ?, ?, '{}', 0, ?, ?, 4, datetime('now'))",
        ("run1", "p1", "テスト太郎 30歳", "質問1", "回答テスト"),
    )
    hist_conn.commit()
    hist_conn.close()

    app = FastAPI()
    app.include_router(followup.router)
    with TestClient(app) as c:
        yield c

    settings.db_path = orig_db
    settings.history_db_path = orig_hist


def test_followup_emits_error_event_on_llm_failure(followup_client):
    """When LLM stream fails, must emit an error event, not hang."""
    async def mock_stream(*args, **kwargs):
        raise ConnectionError("vLLM unreachable")
        yield  # make it a generator

    with patch("routers.followup.stream_followup_answer", side_effect=mock_stream):
        resp = followup_client.post(
            "/api/followup/ask",
            json={
                "run_id": "run1",
                "persona_uuid": "p1",
                "question": "テスト質問",
            },
            headers={"Accept": "text/event-stream"},
        )

    events = []
    for line in resp.text.split("\n"):
        if line.startswith("event: "):
            events.append(line[7:].strip())

    assert "error" in events or "done" in events, (
        f"Expected error or done event, got: {events}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_followup_sse.py -v`
Expected: FAIL — stream breaks without error/done event

- [ ] **Step 3: Wrap followup stream in try/except**

In `backend/routers/followup.py`, wrap the streaming loop. Find the `async for kind, chunk in stream_followup_answer(...)` loop and wrap it:

```python
        try:
            async for kind, chunk in stream_followup_answer(system_prompt, messages):
                if kind == 'think':
                    data = json.dumps({"thinking": chunk}, ensure_ascii=False)
                    yield f"event: thinking\ndata: {data}\n\n"
                else:
                    full_answer += chunk
                    data = json.dumps({"text": chunk}, ensure_ascii=False)
                    yield f"event: token\ndata: {data}\n\n"
        except Exception as e:
            logger.error("Followup LLM error for %s: %s", request.persona_uuid, e)
            err_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err_data}\n\n"
            full_answer = "（回答を取得できませんでした）"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_followup_sse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/followup.py backend/tests/test_followup_sse.py
git commit -m "fix: emit error event in followup SSE when LLM fails"
```

---

## Task 6: Fix Frontend Loading & Readiness Gating (Issues 4, 5)

**Problem:** (a) "データベース読み込み中" never ends — the frontend doesn't properly poll `/ready` or handle 503 responses. (b) "新規調査" button doesn't respond during DB loading because there's no readiness gate.

**Files:**
- Create: `frontend/src/components/__tests__/loading-states.test.tsx`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/src/components/__tests__/loading-states.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom';

vi.mock('../../api', () => ({
  api: {
    getFilters: vi.fn(),
    getSample: vi.fn(),
    getCount: vi.fn(),
    getHistory: vi.fn(),
    getHistoryRun: vi.fn(),
    deleteHistoryRun: vi.fn(),
    generateReport: vi.fn(),
    checkReady: vi.fn(),
    checkHealth: vi.fn(),
  },
  startSurveySSE: vi.fn(),
  startFollowupSSE: vi.fn(),
}));

import { api } from '../../api';

describe('Loading state API', () => {
  it('api.checkReady should be a function', () => {
    expect(typeof api.checkReady).toBe('function');
  });

  it('api.checkHealth should be a function', () => {
    expect(typeof api.checkHealth).toBe('function');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run src/components/__tests__/loading-states.test.tsx`
Expected: FAIL — `api.checkReady` is undefined

- [ ] **Step 3: Add checkReady and checkHealth to api.ts**

Add to the `api` object in `frontend/src/api.ts`:

```typescript
async checkReady(): Promise<boolean> {
  try {
    const res = await fetch('/ready');
    return res.ok;
  } catch {
    return false;
  }
},

async checkHealth(): Promise<{ status: string; mock_llm: boolean; llm_reachable: boolean }> {
  const res = await fetch('/health');
  return res.json();
},
```

- [ ] **Step 4: Add dbReady and llmStatus state to store.ts**

Add to the `AppState` interface in `frontend/src/store.ts`:

```typescript
// In interface AppState:
dbReady: boolean
setDbReady: (ready: boolean) => void
llmStatus: { mock_llm: boolean; llm_reachable: boolean } | null
setLlmStatus: (status: { mock_llm: boolean; llm_reachable: boolean }) => void
```

Add to the store creation:

```typescript
// In create<AppState>:
dbReady: false,
setDbReady: (dbReady) => set({ dbReady }),
llmStatus: null,
setLlmStatus: (llmStatus) => set({ llmStatus }),
```

Also add `dbReady: false` and `llmStatus: null` to `resetSurvey()` if desired (though readiness shouldn't reset on survey reset).

- [ ] **Step 5: Update App.tsx to poll readiness**

Add a `useEffect` at the top of the App component that polls `/ready` every 2s:

```tsx
const dbReady = useStore(s => s.dbReady);
const setDbReady = useStore(s => s.setDbReady);
const setLlmStatus = useStore(s => s.setLlmStatus);

useEffect(() => {
  if (dbReady) return;
  let cancelled = false;
  const poll = async () => {
    while (!cancelled) {
      const ready = await api.checkReady();
      if (ready && !cancelled) {
        setDbReady(true);
        const health = await api.checkHealth();
        setLlmStatus(health);
        return;
      }
      await new Promise(r => setTimeout(r, 2000));
    }
  };
  poll();
  return () => { cancelled = true; };
}, [dbReady, setDbReady, setLlmStatus]);
```

Show a clear loading overlay when `!dbReady`:
```tsx
if (!dbReady) {
  return (
    <div className="min-h-screen bg-[#0a0a0f] flex items-center justify-center">
      <div className="text-center">
        <div className="animate-spin w-8 h-8 border-2 border-[#76B900] border-t-transparent rounded-full mx-auto mb-4" />
        <p className="text-gray-300">データベースを準備中...</p>
        <p className="text-gray-500 text-sm mt-2">初回は数分かかる場合があります</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Update Sidebar.tsx to disable "新規調査" when not ready**

In `frontend/src/components/Sidebar.tsx`, read `dbReady` from the store and disable the button:

```tsx
const dbReady = useStore(s => s.dbReady);
// In the "新規調査" button:
<button
  disabled={!dbReady}
  className={`... ${!dbReady ? 'opacity-50 cursor-not-allowed' : ''}`}
  onClick={handleNewSurvey}
>
  新規調査
</button>
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run src/components/__tests__/loading-states.test.tsx`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add frontend/src/api.ts frontend/src/store.ts frontend/src/App.tsx frontend/src/components/Sidebar.tsx frontend/src/components/__tests__/loading-states.test.tsx
git commit -m "fix: add readiness polling and disable UI during DB load"
```

---

## Task 7: Fix Question Generation Button (Issue 7)

**Problem:** "AIに質問を生成させる" button in SurveyConfig.tsx doesn't work when the LLM is unavailable. The `catch` block at line 66 says `// ignore` — errors are completely swallowed with no user feedback. The existing `generatingQuestions` state (line 15) is already used for the loading indicator but no error state exists.

**Files:**
- Create: `frontend/src/components/__tests__/survey-config.test.tsx`
- Modify: `frontend/src/components/SurveyConfig.tsx`

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/__tests__/survey-config.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';

vi.mock('../../api', () => ({
  api: {
    getFilters: vi.fn(),
    getSample: vi.fn(),
    getCount: vi.fn(),
    getHistory: vi.fn(),
    getHistoryRun: vi.fn(),
    deleteHistoryRun: vi.fn(),
    generateReport: vi.fn(),
    checkReady: vi.fn().mockResolvedValue(true),
    checkHealth: vi.fn().mockResolvedValue({ mock_llm: true, llm_reachable: true }),
  },
  startSurveySSE: vi.fn(),
  startFollowupSSE: vi.fn(),
}));

describe('SurveyConfig', () => {
  it('should show LLM warning when llmStatus indicates unreachable', async () => {
    // Import dynamically after mocks are set up
    const { useStore } = await import('../../store');

    // Set store state to simulate LLM unreachable
    useStore.setState({
      surveyTheme: 'テスト',
      questions: ['質問1'],
      selectedPersonas: [{ uuid: 'p1', name: 'テスト', age: 30, sex: '男',
        prefecture: '東京都', region: '関東', occupation: '会社員',
        education_level: '大学卒', marital_status: '未婚', persona: 'テスト',
        professional_persona: '', cultural_background: '', skills_and_expertise: '',
        hobbies_and_interests: '', career_goals_and_ambitions: '' }],
      surveyLabel: '',
      llmStatus: { mock_llm: false, llm_reachable: false },
    });

    const SurveyConfig = (await import('../SurveyConfig')).default;
    render(<SurveyConfig />);

    // Should show a warning about LLM being unreachable
    expect(screen.getByText(/LLM.*接続できません/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run src/components/__tests__/survey-config.test.tsx`
Expected: FAIL — no LLM warning element exists

- [ ] **Step 3: Fix SurveyConfig.tsx error handling**

In `frontend/src/components/SurveyConfig.tsx`:

1. Add error state:
```tsx
const [genError, setGenError] = useState<string | null>(null)
```

2. Read `llmStatus` from store:
```tsx
const llmStatus = useStore(s => s.llmStatus)
```

3. Replace the empty `catch` block (line 66-67) with:
```tsx
} catch (err) {
  setGenError('質問の生成に失敗しました。LLMサーバーの接続を確認してください。')
}
```

4. Clear error when generation starts (inside `generateQuestions`, before the try):
```tsx
setGenError(null)
```

5. Add warning and error display in the JSX, after the "質問項目" section header:

```tsx
{llmStatus && !llmStatus.llm_reachable && !llmStatus.mock_llm && (
  <p className="text-yellow-400 text-xs mb-2">
    LLMサーバーに接続できません。モックモードでの実行を検討してください。
  </p>
)}
{genError && (
  <p className="text-red-400 text-xs mt-2">{genError}</p>
)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run src/components/__tests__/survey-config.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SurveyConfig.tsx frontend/src/components/__tests__/survey-config.test.tsx
git commit -m "fix: show error feedback when question generation fails"
```

---

## Task 8: Fix LLM Generation Visibility & Error Display (Issue 9)

**Problem:** Users can't tell when the LLM is generating. The SurveyRunner shows "回答中..." but has no global progress bar and doesn't display per-question errors. The `persona_error` event is already handled in `useSurvey.ts` (lines 106-109) — it sets `status: 'error'`. But SurveyRunner only shows a red "✗" icon for errors (line 41) with no detail.

**Key types:** `PersonaStatus = 'waiting' | 'active' | 'complete' | 'error'` and `PersonaRunState` has fields: `persona`, `status`, `answers`, `activeQuestion?`, `activeAnswer?`, `activeThinking?`.

**Files:**
- Modify: `frontend/src/components/SurveyRunner.tsx`

- [ ] **Step 1: Add progress bar to SurveyRunner**

In `frontend/src/components/SurveyRunner.tsx`, add a progress bar after the header (after line 142):

```tsx
{/* Progress bar */}
{!surveyComplete && (
  <div className="mb-2">
    <div className="w-full bg-gray-800 rounded-full h-1.5">
      <div
        className="bg-[#76B900] h-1.5 rounded-full transition-all duration-300"
        style={{ width: `${total > 0 ? (surveyCompleted / total) * 100 : 0}%` }}
      />
    </div>
    <p className="text-xs text-gray-500 mt-1">
      {surveyCompleted}/{total} ペルソナ完了
      {surveyFailed > 0 && <span className="text-red-400 ml-2">({surveyFailed}件エラー)</span>}
    </p>
  </div>
)}
```

Note: `surveyCompleted`, `surveyFailed`, `total` are already available from the existing destructuring on line 68-69.

- [ ] **Step 2: Add error detail display for errored personas**

In the `PersonaListItem` component, enhance the error display. The existing code (line 41-42) shows "✗" and red color for errors. Add a tooltip or inline message. In the Q&A feed area, when `displayState?.status === 'error'`, show a clear error message:

After the `{displayState.status === 'active' && ...}` block (around line 218-236), add:

```tsx
{displayState.status === 'error' && displayState.answers.length === 0 && (
  <div className="text-sm text-red-400 bg-red-900/20 rounded-lg p-3">
    LLM応答エラーが発生しました。サーバー接続を確認してください。
  </div>
)}
```

- [ ] **Step 3: Wrap PersonaListItem in React.memo**

The `PersonaListItem` component (lines 24-63) is already a separate function but not memoized. Wrap it:

```tsx
const PersonaListItem = React.memo(function PersonaListItem({
  name, age, sex, status, score, isActive, onClick,
}: {
  // ... existing props
}) {
  // ... existing body
});
```

Add `React` import: change `import { useEffect, useRef } from 'react'` to `import React, { useEffect, useRef } from 'react'`.

- [ ] **Step 4: Run all frontend tests**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/SurveyRunner.tsx
git commit -m "feat: add progress bar, error display, and memoize persona list"
```

---

## Task 9: Vite Code Splitting (Issue 3)

**Problem:** Build warning: "Some chunks are larger than 500 kB after minification." No `manualChunks` configuration in `frontend/vite.config.ts`.

**Files:**
- Modify: `frontend/vite.config.ts`

- [ ] **Step 1: Analyze current bundle**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vite build 2>&1 | tail -20`
Note which chunks exceed 500kB (likely `recharts` is the largest dependency).

- [ ] **Step 2: Add manualChunks to vite.config.ts**

Add a `build` section to the Vite config:

```typescript
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom'],
        charts: ['recharts'],
      },
    },
  },
},
```

- [ ] **Step 3: Rebuild and verify warning is gone**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vite build 2>&1 | grep -i "chunk"`
Expected: No "larger than 500 kB" warning

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "perf: add Vite manualChunks to eliminate large bundle warning"
```

---

## Task 10: Frontend Theme Redesign (Issue 1)

**Problem:** The current NVIDIA dark theme uses harsh lime green (`#76B900`) on near-black backgrounds. It looks like a gaming/tech booth, not a professional finance demo.

**Approach:** Use @superpowers:frontend-design skill during execution for creative direction. Plan defines the structural changes; the skill will guide the actual palette and visual design.

**Important:** The codebase uses **hardcoded hex values** in className strings (e.g., `bg-[#0a0a0f]`, `text-[#76B900]`, `border-[rgba(118,185,0,0.2)]`), NOT Tailwind utility names like `bg-nvidia-green`. The `tailwind.config.js` defines `nvidia.green` etc. but components reference hex values directly.

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`
- Modify: All components with hardcoded color hex values

- [ ] **Step 1: Define new color palette in tailwind.config.js**

Replace NVIDIA colors with a professional finance palette. Use the `frontend-design` skill to determine exact values. Update the `extend.colors` section. Example structure:

```javascript
colors: {
  fin: {
    primary: '#....',      // Primary accent (refined blue or teal)
    secondary: '#....',    // Secondary accent
    dark: '#....',         // Darkest background
    darker: '#....',       // Card/panel background
    surface: '#....',      // Elevated surface
    border: 'rgba(...)',   // Subtle borders
    success: '#....',      // Positive scores (green)
    warning: '#....',      // Medium scores (amber)
    danger: '#....',       // Low scores (red)
  },
},
```

- [ ] **Step 2: Update index.css base styles**

Update body background, text color, scrollbar colors, and animations to use new palette.

- [ ] **Step 3: Update components — replace hardcoded hex values**

Search-and-replace across all components. The targets are hardcoded hex/rgba values in `className` strings:

| Current value | Replacement |
|---------------|-------------|
| `bg-[#0a0a0f]` | `bg-fin-dark` |
| `bg-[#141420]` | `bg-fin-darker` |
| `bg-[#1c1c2e]` | `bg-fin-surface` |
| `text-[#76B900]` / `bg-[#76B900]` | `text-fin-primary` / `bg-fin-primary` |
| `text-[#00A3E0]` / `bg-[#00A3E0]` | `text-fin-secondary` / `bg-fin-secondary` |
| `border-[rgba(118,185,0,...)]` | `border-fin-border` |
| `hover:bg-[#8fd100]` | `hover:bg-fin-primary/80` |
| `hover:text-[#40c0f0]` | `hover:text-fin-secondary/80` |
| `focus:border-[#76B900]` | `focus:border-fin-primary` |

Files to update: `App.tsx`, `Sidebar.tsx`, `SurveyConfig.tsx`, `SurveyRunner.tsx`, `FilterPanel.tsx`, `PersonaCards.tsx`, `ReportDashboard.tsx`, `FollowUpChat.tsx`, `StepIndicator.tsx`, `TopPickCard.tsx`, `PersonaAvatar.tsx`, `PersonaDetailModal.tsx`, `Layout.tsx`

- [ ] **Step 4: Build and verify**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npm run build`
Expected: No build errors

- [ ] **Step 5: Run all frontend tests**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/index.css frontend/src/components/ frontend/src/App.tsx
git commit -m "feat: redesign theme with professional finance palette"
```

---

## Task 11: UI Performance — Batch SSE Chunk Updates (Issue 8)

**Problem:** The web UI is laggy. The `useSurvey` hook calls `store.updatePersonaState()` on every `persona_answer_chunk` SSE event (line 73 of `useSurvey.ts`), causing a Zustand state update + React re-render per chunk. With multiple personas and fast token streaming, this can be hundreds of updates per second.

**Architecture note:** The SSE event handler is a callback passed to `startSurveySSE()` (line 45). It's not a useEffect — it's a closure created inside `useCallback`. The buffering must happen inside this callback, using a ref for the timer and accumulated text.

**Key fields:** `PersonaRunState.activeAnswer` (string) accumulates streaming text. `store.updatePersonaState(uuid, partial)` does a shallow merge.

**Files:**
- Modify: `frontend/src/hooks/useSurvey.ts`

- [ ] **Step 1: Add chunk buffering refs in useSurvey**

Add refs for chunk accumulation and a flush interval:

```typescript
const chunkBuffer = useRef<Record<string, string>>({})
const flushRef = useRef<ReturnType<typeof setInterval> | null>(null)
```

- [ ] **Step 2: Start/stop flush interval with survey lifecycle**

At the start of `startSurvey`, before calling `startSurveySSE`:

```typescript
// Start batched flush for chunks
if (flushRef.current) clearInterval(flushRef.current)
flushRef.current = setInterval(() => {
  const buf = chunkBuffer.current
  const keys = Object.keys(buf)
  if (keys.length === 0) return
  const s = useStore.getState()
  for (const pid of keys) {
    const ps = s.personaStates[pid]
    if (ps) {
      const current = ps.activeAnswer || ''
      s.updatePersonaState(pid, { activeAnswer: current + buf[pid] })
    }
  }
  chunkBuffer.current = {}
}, 100)
```

In the `survey_complete` handler, flush remaining and clear:

```typescript
case 'survey_complete': {
  // Flush any remaining chunks
  if (flushRef.current) {
    clearInterval(flushRef.current)
    flushRef.current = null
  }
  const buf = chunkBuffer.current
  for (const [pid, text] of Object.entries(buf)) {
    const ps2 = s.personaStates[pid]
    if (ps2) s.updatePersonaState(pid, { activeAnswer: (ps2.activeAnswer || '') + text })
  }
  chunkBuffer.current = {}
  // ... existing survey_complete logic
}
```

- [ ] **Step 3: Replace inline chunk update with buffer write**

Change the `persona_answer_chunk` handler (lines 68-78):

```typescript
case 'persona_answer_chunk': {
  const d = data as SSEPersonaAnswerChunk
  // Buffer chunks instead of immediate store update
  chunkBuffer.current[d.persona_uuid] = (chunkBuffer.current[d.persona_uuid] || '') + d.chunk
  // Still update activeQuestion immediately (it's cheap)
  const ps = s.personaStates[d.persona_uuid]
  if (ps && ps.activeQuestion !== d.question_index) {
    s.updatePersonaState(d.persona_uuid, { activeQuestion: d.question_index })
  }
  break
}
```

- [ ] **Step 4: Flush buffer before persona_answer finalizes**

In the `persona_answer` handler, flush the buffer for that persona first:

```typescript
case 'persona_answer': {
  const d = data as SSEPersonaAnswer
  // Flush any buffered chunks for this persona
  delete chunkBuffer.current[d.persona_uuid]
  // ... existing persona_answer logic
}
```

- [ ] **Step 5: Clean up on cancelSurvey**

In `cancelSurvey`:
```typescript
const cancelSurvey = useCallback(() => {
  cancelRef.current?.()
  cancelRef.current = null
  if (flushRef.current) {
    clearInterval(flushRef.current)
    flushRef.current = null
  }
  chunkBuffer.current = {}
}, [])
```

- [ ] **Step 6: Run frontend tests**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useSurvey.ts
git commit -m "perf: batch SSE chunk updates at 100ms intervals to reduce re-renders"
```

---

## Task 12: End-to-End Smoke Test in Mock Mode (Issue 10)

**Problem:** "The demo just doesn't work at current setting." Need to verify the full flow works end-to-end with `MOCK_LLM=true`.

**Files:**
- Create: `backend/tests/test_e2e_mock.py`

- [ ] **Step 1: Write E2E test for mock mode**

```python
# backend/tests/test_e2e_mock.py
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings
from db import PERSONA_DDL, _create_history_db


@pytest.fixture()
def e2e_client(tmp_path):
    """Full app client with mock LLM and temp DBs."""
    persona_db = str(tmp_path / "personas.db")
    history_db = str(tmp_path / "history.db")

    conn = sqlite3.connect(persona_db)
    conn.executescript(PERSONA_DDL)
    conn.execute(
        "INSERT INTO personas (uuid, name, persona, country, sex, age, marital_status,"
        " education_level, occupation, region, area, prefecture)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("p1", "テスト太郎", "テストペルソナ", "日本", "男", 30,
         "未婚", "大学卒", "会社員", "関東", "都心", "東京都"),
    )
    conn.commit()
    conn.close()

    orig_db = settings.db_path
    orig_hist = settings.history_db_path
    orig_mock = settings.mock_llm
    settings.db_path = persona_db
    settings.history_db_path = history_db
    settings.mock_llm = True

    _create_history_db()

    import main
    main._db_ready.set()

    with TestClient(main.app) as c:
        yield c

    settings.db_path = orig_db
    settings.history_db_path = orig_hist
    settings.mock_llm = orig_mock


def test_full_survey_flow_mock_mode(e2e_client):
    """The complete happy path: filters -> sample -> survey -> report."""
    # 1. Get filters
    resp = e2e_client.get("/api/personas/filters")
    assert resp.status_code == 200

    # 2. Sample personas
    resp = e2e_client.get("/api/personas/sample", params={"count": 1})
    assert resp.status_code == 200
    personas = resp.json()["sampled"]
    assert len(personas) >= 1
    pid = personas[0]["uuid"]

    # 3. Run survey (SSE)
    resp = e2e_client.post(
        "/api/survey/run",
        json={
            "persona_ids": [pid],
            "survey_theme": "テスト調査",
            "questions": ["この商品をどう思いますか？"],
        },
    )
    assert resp.status_code == 200
    text = resp.text
    assert "survey_complete" in text

    # Extract run_id from events
    run_id = None
    for line in text.split("\n"):
        if line.startswith("data: ") and "run_id" in line:
            data = json.loads(line[6:])
            if "run_id" in data:
                run_id = data["run_id"]
                break
    assert run_id is not None

    # 4. Generate report
    resp = e2e_client.post("/api/report/generate", json={"run_id": run_id})
    assert resp.status_code == 200
    report = resp.json()
    assert "overall_score" in report

    # 5. Check history
    resp = e2e_client.get("/api/history")
    assert resp.status_code == 200
    assert len(resp.json()["runs"]) >= 1
```

- [ ] **Step 2: Run E2E test**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_e2e_mock.py -v`
Expected: PASS (after all prior fixes)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_e2e_mock.py
git commit -m "test: add E2E smoke test for mock mode survey flow"
```

---

## Execution Dependencies

```
Task 1 (config paths) <- Task 2 (start.sh seed)
Task 3 (health check) <- Task 6 (frontend readiness) <- Task 7 (question gen button)
Task 4 (survey SSE errors) <- Task 8 (generation indicators)
Task 5 (followup SSE errors) — independent
Task 9 (code splitting) — independent
Task 10 (theme redesign) — independent, use @frontend-design skill
Task 11 (performance) — independent
Task 12 (E2E test) — depends on Tasks 1-8
```

**Recommended parallel execution groups:**
1. **Backend group:** Tasks 1 → 2 → 3 → 4 → 5 (sequential, each builds on prior)
2. **Frontend group A:** Tasks 6 → 7 → 8 (sequential, depends on Task 3)
3. **Frontend group B:** Tasks 9, 10, 11 (independent, can run in parallel)
4. **Validation:** Task 12 (after groups 1-3 complete)
