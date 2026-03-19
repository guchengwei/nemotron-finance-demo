# Fix Four Critical Bugs — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 bugs: (1) database loading freeze, (2) undeletable survey history, (3) deep-dive LLM cutoff + thinking display, (4) persona profile truncation in deep-dive view.

**Architecture:** Replace SQLite persona queries with in-memory pandas DataFrame for instant filter/sample operations. Keep SQLite only for history.db (small, write-heavy). Add separate followup token budget. Fix missing UI elements (delete button, expandable profile).

**Tech Stack:** Python/FastAPI, pandas (already installed), aiosqlite (history only), React/TypeScript, Zustand

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/persona_store.py` | **Create** | In-memory persona DataFrame: load from parquet, filter/sample/lookup operations |
| `backend/db.py` | **Modify** | Remove persona SQLite logic. Keep history DB init. Add WAL mode for history. |
| `backend/main.py` | **Modify** | Use persona_store init. Report error state on `/ready` if init fails. |
| `backend/config.py` | **Modify** | Add `followup_max_tokens`. Remove `db_path`. |
| `backend/routers/personas.py` | **Modify** | Replace SQLite queries with persona_store calls. |
| `backend/routers/survey.py` | **Modify** | Replace `_get_persona()` SQLite lookup with persona_store lookup. |
| `backend/llm.py` | **Modify** | Fix `_stream_split_thinking` to handle unclosed `<think>`. Use `followup_max_tokens`. |
| `frontend/src/components/Sidebar.tsx` | **Modify** | Add delete button with confirmation. |
| `frontend/src/components/FollowUpChat.tsx` | **Modify** | Make persona profile expandable (remove line-clamp). |
| `frontend/src/App.tsx` | **Modify** | Handle error state from `/ready` endpoint. |
| `backend/tests/conftest.py` | **Modify** | Update fixtures to use persona_store instead of SQLite. |
| `backend/tests/test_persona_store.py` | **Create** | Unit tests for in-memory persona store. |
| `backend/tests/test_personas_api.py` | **Modify** | Update to work with DataFrame-backed endpoints. |
| `backend/tests/test_stream_thinking.py` | **Create** | Tests for `_stream_split_thinking` edge cases. |
| `frontend/src/components/__tests__/sidebar.test.tsx` | **Modify** | Add test for delete button. |

---

## Task 1: Create in-memory persona store

**Files:**
- Create: `backend/persona_store.py`
- Create: `backend/tests/test_persona_store.py`

This module replaces all SQLite persona queries. It loads the parquet into a pandas DataFrame at startup and provides filter/sample/lookup functions. All operations are sub-millisecond on 1M rows in-memory.

- [ ] **Step 1: Write failing tests for persona store**

Create `backend/tests/test_persona_store.py`:

```python
import pandas as pd
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persona_store import PersonaStore


@pytest.fixture()
def store():
    """Build a PersonaStore from a small test DataFrame."""
    df = pd.DataFrame([
        {"uuid": "p1", "name": "田中太郎", "sex": "男", "age": 35, "region": "関東",
         "prefecture": "東京都", "occupation": "会社員", "education_level": "大学卒",
         "marital_status": "既婚", "persona": "ペルソナ1", "professional_persona": "会社員",
         "cultural_background": "日本", "skills_and_expertise": "営業",
         "hobbies_and_interests": "読書", "career_goals_and_ambitions": "昇進",
         "area": "都心", "country": "日本"},
        {"uuid": "p2", "name": "佐藤花子", "sex": "女", "age": 29, "region": "関東",
         "prefecture": "東京都", "occupation": "公務員", "education_level": "大学卒",
         "marital_status": "未婚", "persona": "ペルソナ2", "professional_persona": "公務員",
         "cultural_background": "日本", "skills_and_expertise": "事務",
         "hobbies_and_interests": "旅行", "career_goals_and_ambitions": "安定",
         "area": "都心", "country": "日本"},
        {"uuid": "p3", "name": "鈴木一郎", "sex": "男", "age": 52, "region": "関西",
         "prefecture": "大阪府", "occupation": "自営業", "education_level": "高校卒",
         "marital_status": "既婚", "persona": "ペルソナ3", "professional_persona": "自営業",
         "cultural_background": "日本", "skills_and_expertise": "経営",
         "hobbies_and_interests": "ゴルフ", "career_goals_and_ambitions": "事業拡大",
         "area": "都市部", "country": "日本"},
        {"uuid": "p4", "name": "高橋陽子", "sex": "女", "age": 45, "region": "関東",
         "prefecture": "神奈川県", "occupation": "会社員", "education_level": "大学卒",
         "marital_status": "既婚", "persona": "ペルソナ4", "professional_persona": "会社員",
         "cultural_background": "日本", "skills_and_expertise": "企画",
         "hobbies_and_interests": "料理", "career_goals_and_ambitions": "転職",
         "area": "郊外", "country": "日本"},
    ])
    return PersonaStore(df)


def test_total_count(store):
    assert store.total_count() == 4


def test_filters(store):
    f = store.get_filters()
    assert set(f["sex"]) == {"男", "女"}
    assert "関東" in f["regions"]
    assert "関西" in f["regions"]
    assert f["total_count"] == 4
    assert "大学卒" in f["education_levels"]
    assert "高校卒" in f["education_levels"]


def test_count_with_sex_filter(store):
    assert store.count(sex="男") == 2


def test_count_with_region_and_age(store):
    assert store.count(region="関東", age_min=30, age_max=50) == 2


def test_count_no_match(store):
    assert store.count(region="九州") == 0


def test_sample_returns_requested_count(store):
    total, sampled = store.sample(count=2)
    assert total == 4
    assert len(sampled) == 2


def test_sample_with_filter(store):
    total, sampled = store.sample(sex="男", count=10)
    assert total == 2
    assert len(sampled) == 2
    assert all(p["sex"] == "男" for p in sampled)


def test_sample_includes_all_persona_fields(store):
    _, sampled = store.sample(count=1)
    p = sampled[0]
    assert "uuid" in p
    assert "name" in p
    assert "persona" in p
    assert "occupation" in p


def test_get_persona_by_uuid(store):
    p = store.get_persona("p1")
    assert p is not None
    assert p["name"] == "田中太郎"
    assert p["uuid"] == "p1"


def test_get_persona_missing_returns_none(store):
    assert store.get_persona("nonexistent") is None


def test_occupation_filter_uses_partial_match(store):
    assert store.count(occupation="会社") == 2


def test_education_filter_uses_partial_match(store):
    assert store.count(education="大学") == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_persona_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'persona_store'`

- [ ] **Step 3: Implement PersonaStore**

Create `backend/persona_store.py`:

```python
"""In-memory persona store backed by pandas DataFrame.

Replaces SQLite for persona queries. Loaded once at startup from parquet.
All filter/sample/lookup operations are sub-millisecond on 1M rows.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

# Singleton instance — set by init_persona_store()
_store: Optional["PersonaStore"] = None


class PersonaStore:
    """In-memory persona data with filter, sample, and lookup operations."""

    def __init__(self, df: pd.DataFrame):
        # Fill NaN with None for JSON serialization
        self._df = df.where(df.notna(), None)
        logger.info("PersonaStore initialized with %d rows", len(df))

    def total_count(self) -> int:
        return len(self._df)

    def get_filters(self) -> dict:
        df = self._df
        sex_vals = sorted(df["sex"].dropna().unique().tolist())
        regions = sorted(df["region"].dropna().unique().tolist())
        prefectures = sorted(df["prefecture"].dropna().unique().tolist())
        education_levels = sorted(df["education_level"].dropna().unique().tolist())
        occ_counts = (
            df["occupation"].dropna()
            .value_counts()
            .head(50)
            .index.tolist()
        )
        return {
            "sex": sex_vals,
            "age_ranges": ["20-29", "30-39", "40-49", "50-59", "60-69", "70+"],
            "regions": regions,
            "prefectures": prefectures,
            "occupations_top50": occ_counts,
            "education_levels": education_levels,
            "financial_literacy": ["初心者", "中級者", "上級者", "専門家"],
            "total_count": len(df),
        }

    def _apply_filters(
        self,
        sex: Optional[str] = None,
        age_min: Optional[int] = None,
        age_max: Optional[int] = None,
        region: Optional[str] = None,
        prefecture: Optional[str] = None,
        occupation: Optional[str] = None,
        education: Optional[str] = None,
        financial_literacy: Optional[str] = None,
    ) -> pd.DataFrame:
        df = self._df
        if sex:
            df = df[df["sex"] == sex]
        if age_min is not None:
            df = df[df["age"] >= age_min]
        if age_max is not None:
            df = df[df["age"] <= age_max]
        if region:
            df = df[df["region"] == region]
        if prefecture:
            df = df[df["prefecture"] == prefecture]
        if occupation:
            df = df[df["occupation"].str.contains(occupation, na=False)]
        if education:
            df = df[df["education_level"].str.contains(education, na=False)]
        if financial_literacy:
            df = df[df.get("financial_literacy", pd.Series(dtype=str)) == financial_literacy]
        return df

    def count(self, **filters) -> int:
        return len(self._apply_filters(**filters))

    def sample(self, count: int = 8, **filters) -> tuple[int, list[dict]]:
        filtered = self._apply_filters(**filters)
        total = len(filtered)
        if total == 0:
            return 0, []
        n = min(count, total)
        sampled = filtered.sample(n=n)
        rows = sampled.to_dict(orient="records")
        return total, rows

    def get_persona(self, uuid: str) -> Optional[dict]:
        matches = self._df[self._df["uuid"] == uuid]
        if matches.empty:
            return None
        return matches.iloc[0].to_dict()


def init_persona_store() -> PersonaStore:
    """Load parquet into memory. Downloads from HuggingFace if needed."""
    from db import extract_name, _download_dataset

    raw_parquet = (settings.persona_parquet_path or "").strip()
    if raw_parquet:
        parquet_path = Path(raw_parquet).expanduser()
    else:
        parquet_path = Path(settings.data_dir) / "personas.parquet"

    if not parquet_path.exists():
        logger.info("Parquet not found — downloading from HuggingFace...")
        _download_dataset(parquet_path)

    logger.info("Loading parquet into memory: %s", parquet_path)
    df = pd.read_parquet(str(parquet_path))

    # Extract names if not present
    if "name" not in df.columns:
        df["name"] = df["persona"].apply(extract_name)

    logger.info("Loaded %d personas into memory", len(df))

    global _store
    _store = PersonaStore(df)
    return _store


def get_store() -> PersonaStore:
    """Get the singleton PersonaStore. Raises if not initialized."""
    if _store is None:
        raise RuntimeError("PersonaStore not initialized — call init_persona_store() first")
    return _store
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_persona_store.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/persona_store.py backend/tests/test_persona_store.py
git commit -m "feat: add in-memory PersonaStore backed by pandas DataFrame

Replaces SQLite for read-only persona queries. Parquet loaded into memory
at startup for sub-millisecond filter/sample/lookup operations on 1M rows.
Eliminates the 171-second DISTINCT query caused by missing idx_education index."
```

---

## Task 2: Wire PersonaStore into backend and fix /ready error handling

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/db.py`
- Modify: `backend/config.py`
- Modify: `backend/routers/personas.py`
- Modify: `backend/routers/survey.py:37-50` (replace `_get_persona` SQLite lookup)

This task replaces all persona SQLite usage with the in-memory PersonaStore and fixes the critical bug where `_db_ready` is never set on init failure.

- [ ] **Step 1: Update config.py — add followup_max_tokens, keep db_path for backward compat**

In `backend/config.py`, add `followup_max_tokens` after line 20:

```python
    followup_max_tokens: int = 2048
```

The `db_path` setting can remain since it's referenced in tests and may still be used for the financial_context table. No removal needed.

- [ ] **Step 2: Update main.py — fix error handling in _init_db_background, use persona_store**

Replace `_init_db_background` in `backend/main.py` to set `_db_ready` even on failure, and store the error:

```python
_db_ready = threading.Event()
_db_init_error: str | None = None


def _init_db_background():
    global _db_init_error
    try:
        from persona_store import init_persona_store
        from db import _create_history_db
        init_persona_store()
        _create_history_db()
        _db_ready.set()
        logger.info("Databases ready.")
    except Exception as e:
        logger.exception("Database initialization failed.")
        _db_init_error = str(e)
        _db_ready.set()  # Unblock frontend polling — error state will be reported
```

Update the `/ready` endpoint to report errors:

```python
@app.get("/ready")
async def ready():
    if _db_ready.is_set():
        if _db_init_error:
            return JSONResponse(
                {"status": "error", "detail": _db_init_error},
                status_code=500,
            )
        return {"status": "ready"}
    return JSONResponse({"status": "loading"}, status_code=503)
```

- [ ] **Step 3: Rewrite personas.py — replace SQLite with persona_store**

Replace the full content of the three endpoints in `backend/routers/personas.py`:

```python
"""Persona filter, count, and sample endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from models import CountResponse, FiltersResponse, PersonaSample, Persona, FinancialExtension
from persona_store import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/personas', tags=['personas'])


@router.get('/filters', response_model=FiltersResponse)
async def get_filters():
    """Return distinct filter values from the persona store."""
    store = get_store()
    f = store.get_filters()
    return FiltersResponse(**f)


@router.get('/count', response_model=CountResponse)
async def get_count(
    sex: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    prefecture: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    occupation: Optional[str] = Query(None),
    education: Optional[str] = Query(None),
    financial_literacy: Optional[str] = Query(None),
):
    store = get_store()
    total = store.count(
        sex=sex, age_min=age_min, age_max=age_max,
        region=region, prefecture=prefecture,
        occupation=occupation, education=education,
        financial_literacy=financial_literacy,
    )
    return CountResponse(total_matching=total)


@router.get('/sample', response_model=PersonaSample)
async def get_sample(
    sex: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    prefecture: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    occupation: Optional[str] = Query(None),
    education: Optional[str] = Query(None),
    financial_literacy: Optional[str] = Query(None),
    count: int = Query(8, ge=1, le=200),
):
    store = get_store()
    total, rows = store.sample(
        count=count,
        sex=sex, age_min=age_min, age_max=age_max,
        region=region, prefecture=prefecture,
        occupation=occupation, education=education,
        financial_literacy=financial_literacy,
    )
    personas = []
    for record in rows:
        fin_ext = None
        if record.get('financial_literacy'):
            fin_ext = FinancialExtension(
                financial_literacy=record.get('financial_literacy'),
                investment_experience=record.get('investment_experience'),
                financial_concerns=record.get('financial_concerns'),
                annual_income_bracket=record.get('annual_income_bracket'),
                asset_bracket=record.get('asset_bracket'),
                primary_bank_type=record.get('primary_bank_type'),
            )
        personas.append(Persona(
            uuid=record['uuid'],
            name=record.get('name') or '不明',
            age=record.get('age') or 0,
            sex=record.get('sex') or '',
            prefecture=record.get('prefecture') or '',
            region=record.get('region') or '',
            area=record.get('area'),
            occupation=record.get('occupation') or '',
            education_level=record.get('education_level') or '',
            marital_status=record.get('marital_status') or '',
            persona=record.get('persona') or '',
            professional_persona=record.get('professional_persona') or '',
            sports_persona=record.get('sports_persona'),
            arts_persona=record.get('arts_persona'),
            travel_persona=record.get('travel_persona'),
            culinary_persona=record.get('culinary_persona'),
            cultural_background=record.get('cultural_background') or '',
            skills_and_expertise=record.get('skills_and_expertise') or '',
            skills_and_expertise_list=record.get('skills_and_expertise_list'),
            hobbies_and_interests=record.get('hobbies_and_interests') or '',
            hobbies_and_interests_list=record.get('hobbies_and_interests_list'),
            career_goals_and_ambitions=record.get('career_goals_and_ambitions') or '',
            country=record.get('country'),
            financial_extension=fin_ext,
        ))
    return PersonaSample(total_matching=total, sampled=personas)
```

- [ ] **Step 4: Update survey.py — replace _get_persona SQLite lookup**

In `backend/routers/survey.py`, replace `_get_persona` function (lines 37-50) with:

```python
async def _get_persona(persona_id: str) -> dict | None:
    from persona_store import get_store
    return get_store().get_persona(persona_id)
```

Update `_run_persona_survey` signature (line 71-80): remove `persona_db` parameter, update call at line 84:

```python
persona = await _get_persona(persona_id)
```

Update `run_with_sem` (lines 201-207): remove the `aiosqlite.connect(settings.db_path)` block:

```python
async def run_with_sem(pid, idx):
    async with semaphore:
        await _run_persona_survey(
            pid, idx, total, questions, run_id,
            request.survey_theme, event_queue, history_db
        )
```

Remove the `aiosqlite` import if no longer used, and `from config import settings` import of `db_path`.

- [ ] **Step 5: Update db.py — remove persona SQLite loading, keep history + download**

Keep `_create_history_db()`, `_download_dataset()`, `extract_name()`, `get_history_db()`, and the history DDL.

Remove: `_load_personas_to_sqlite()`, `_get_persona_conn()`, `get_persona_db()`, `PERSONA_DDL`, `FINANCIAL_EXT_DDL`, `_ensure_financial_ext_table()`, and `init_db()`.

Add WAL mode to `_create_history_db`:

```python
def _create_history_db():
    os.makedirs(os.path.dirname(settings.history_db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(settings.history_db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(HISTORY_DDL)
    conn.commit()
    conn.close()
    logger.info("History DB ready: %s", settings.history_db_path)
```

- [ ] **Step 6: Update test fixtures in conftest.py**

Replace the `seeded_db` / `client` fixtures in `backend/tests/conftest.py` to use PersonaStore:

```python
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from persona_store import PersonaStore
from routers import personas


TEST_PERSONA_DATA = [
    {"uuid": "p1", "name": "田中太郎", "sex": "男", "age": 35, "region": "関東",
     "prefecture": "東京都", "occupation": "会社員", "education_level": "大学卒",
     "marital_status": "既婚", "persona": "ペルソナ1", "professional_persona": "会社員",
     "cultural_background": "日本", "skills_and_expertise": "営業",
     "skills_and_expertise_list": "['営業']", "hobbies_and_interests": "読書",
     "hobbies_and_interests_list": "['読書']", "career_goals_and_ambitions": "昇進",
     "area": "都心", "country": "日本",
     "financial_literacy": "中級者", "investment_experience": "あり",
     "financial_concerns": "老後資金", "annual_income_bracket": "600-800万円",
     "asset_bracket": "1000-3000万円", "primary_bank_type": "メガバンク"},
    {"uuid": "p2", "name": "佐藤花子", "sex": "女", "age": 29, "region": "関東",
     "prefecture": "東京都", "occupation": "公務員", "education_level": "大学卒",
     "marital_status": "未婚", "persona": "ペルソナ2", "professional_persona": "公務員",
     "cultural_background": "日本", "skills_and_expertise": "事務",
     "skills_and_expertise_list": "['事務']", "hobbies_and_interests": "旅行",
     "hobbies_and_interests_list": "['旅行']", "career_goals_and_ambitions": "安定",
     "area": "都心", "country": "日本",
     "financial_literacy": "初心者", "investment_experience": "なし",
     "financial_concerns": "生活費", "annual_income_bracket": "400-600万円",
     "asset_bracket": "500-1000万円", "primary_bank_type": "ネット銀行"},
    {"uuid": "p3", "name": "鈴木一郎", "sex": "男", "age": 52, "region": "関西",
     "prefecture": "大阪府", "occupation": "自営業", "education_level": "高校卒",
     "marital_status": "既婚", "persona": "ペルソナ3", "professional_persona": "自営業",
     "cultural_background": "日本", "skills_and_expertise": "経営",
     "skills_and_expertise_list": "['経営']", "hobbies_and_interests": "ゴルフ",
     "hobbies_and_interests_list": "['ゴルフ']", "career_goals_and_ambitions": "事業拡大",
     "area": "都市部", "country": "日本",
     "financial_literacy": "専門家", "investment_experience": "あり",
     "financial_concerns": "事業承継", "annual_income_bracket": "800万円以上",
     "asset_bracket": "3000万円以上", "primary_bank_type": "地方銀行"},
    {"uuid": "p4", "name": "高橋陽子", "sex": "女", "age": 45, "region": "関東",
     "prefecture": "神奈川県", "occupation": "会社員", "education_level": "大学卒",
     "marital_status": "既婚", "persona": "ペルソナ4", "professional_persona": "会社員",
     "cultural_background": "日本", "skills_and_expertise": "企画",
     "skills_and_expertise_list": "['企画']", "hobbies_and_interests": "料理",
     "hobbies_and_interests_list": "['料理']", "career_goals_and_ambitions": "転職",
     "area": "郊外", "country": "日本",
     "financial_literacy": "上級者", "investment_experience": "あり",
     "financial_concerns": "教育費", "annual_income_bracket": "600-800万円",
     "asset_bracket": "1000-3000万円", "primary_bank_type": "メガバンク"},
]


@pytest.fixture()
def test_store():
    """Create a PersonaStore from test data."""
    df = pd.DataFrame(TEST_PERSONA_DATA)
    return PersonaStore(df)


@pytest.fixture()
def client(test_store):
    """API client with PersonaStore patched in."""
    app = FastAPI()
    app.include_router(personas.router)

    with patch("routers.personas.get_store", return_value=test_store):
        with TestClient(app) as test_client:
            yield test_client
```

- [ ] **Step 7: Run all backend tests**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/ -v`
Expected: All pass. Some test files (test_survey_sse.py, test_followup_sse.py, test_e2e_mock.py) may need minor patches if they import removed symbols — fix as needed.

- [ ] **Step 8: Commit**

```bash
git add backend/main.py backend/db.py backend/config.py backend/routers/personas.py backend/routers/survey.py backend/tests/conftest.py
git commit -m "fix: replace SQLite persona queries with in-memory pandas DataFrame

Root cause: missing idx_education index caused 171-second DISTINCT query
on 4.1GB SQLite DB, freezing the filter panel indefinitely.

Solution: load parquet directly into pandas DataFrame at startup.
All filter/sample/lookup operations are now sub-millisecond.
SQLite retained only for history.db (small, write-heavy).

Also fixes: /ready endpoint now reports init errors instead of
hanging forever when initialization fails."
```

---

## Task 3: Fix frontend error handling for /ready

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: Update api.checkReady to return error state**

In `frontend/src/api.ts`, change `checkReady`:

```typescript
async checkReady(): Promise<{ ready: boolean; error?: string }> {
    try {
      const res = await fetch('/ready');
      if (res.ok) return { ready: true };
      if (res.status === 500) {
        const data = await res.json();
        return { ready: false, error: data.detail || 'Database initialization failed' };
      }
      return { ready: false };
    } catch {
      return { ready: false };
    }
  },
```

- [ ] **Step 2: Update App.tsx to handle error state**

In `frontend/src/App.tsx`, update the polling loop (lines 84-101):

```typescript
const [dbError, setDbError] = useState<string | null>(null);

useEffect(() => {
    if (dbReady) return;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        const result = await api.checkReady();
        if (cancelled) return;
        if (result.error) {
          setDbError(result.error);
          return;
        }
        if (result.ready) {
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

Update the loading screen (lines 103-113) to show error:

```tsx
if (!dbReady) {
    return (
      <div className="min-h-screen bg-[#0F172A] flex items-center justify-center">
        <div className="text-center">
          {dbError ? (
            <>
              <div className="w-8 h-8 mx-auto mb-4 text-red-500 text-2xl">!</div>
              <p className="text-red-400">データベースの初期化に失敗しました</p>
              <p className="text-gray-500 text-sm mt-2 max-w-md">{dbError}</p>
            </>
          ) : (
            <>
              <div className="animate-spin w-8 h-8 border-2 border-[#2563EB] border-t-transparent rounded-full mx-auto mb-4" />
              <p className="text-gray-300">データベースを準備中...</p>
              <p className="text-gray-500 text-sm mt-2">初回は数分かかる場合があります</p>
            </>
          )}
        </div>
      </div>
    );
  }
```

- [ ] **Step 3: Run frontend tests**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/api.ts
git commit -m "fix: show error message when database init fails instead of infinite spinner"
```

---

## Task 4: Add delete button to survey history sidebar

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/__tests__/sidebar.test.tsx`

- [ ] **Step 1: Add delete test to sidebar.test.tsx**

Add to `frontend/src/components/__tests__/sidebar.test.tsx`:

```typescript
describe('Sidebar delete', () => {
  beforeEach(() => {
    useStore.setState({ dbReady: true })
    mockedApi.getFilters.mockResolvedValue(filtersResponse)
    mockedApi.getCount.mockResolvedValue({ total_matching: 100 })
  })

  it('delete button removes history entry', async () => {
    const user = userEvent.setup()
    const mockRun = {
      id: 'run-1',
      created_at: '2026-03-18T00:00:00',
      survey_theme: 'テストテーマ',
      persona_count: 8,
      status: 'completed',
      overall_score: 3.5,
    }
    mockedApi.getHistory.mockResolvedValue({ runs: [mockRun] })
    mockedApi.deleteHistoryRun.mockResolvedValue(undefined)

    render(<App />)

    expect(await screen.findByText('テストテーマ')).toBeInTheDocument()

    const deleteBtn = screen.getByTestId('delete-run-run-1')
    await user.click(deleteBtn)

    await waitFor(() => {
      expect(screen.queryByText('テストテーマ')).not.toBeInTheDocument()
    })
    expect(mockedApi.deleteHistoryRun).toHaveBeenCalledWith('run-1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run src/components/__tests__/sidebar.test.tsx`
Expected: FAIL — delete button not found

- [ ] **Step 3: Add delete button to Sidebar.tsx**

In `frontend/src/components/Sidebar.tsx`, update the history item rendering. Add `api` import and a `deleteRun` handler:

```typescript
import { useEffect, useState } from 'react'
import { useStore } from '../store'
import { api } from '../api'
```

Add inside the `Sidebar` function:

```typescript
const [deleting, setDeleting] = useState<string | null>(null)

const deleteRun = async (e: React.MouseEvent, run_id: string) => {
    e.stopPropagation()
    setDeleting(run_id)
    try {
      await api.deleteHistoryRun(run_id)
      setHistory(history.filter(r => r.id !== run_id))
    } catch (err) {
      console.error('Failed to delete run:', err)
    } finally {
      setDeleting(null)
    }
  }
```

In the history map, add a delete button after the date div (inside the `<button>` element, after line 86):

```tsx
<div
  data-testid={`delete-run-${run.id}`}
  role="button"
  onClick={(e) => deleteRun(e, run.id)}
  className="absolute top-1 right-1 w-5 h-5 flex items-center justify-center
    rounded text-gray-600 hover:text-red-400 hover:bg-red-400/10
    opacity-0 group-hover:opacity-100 transition-all text-xs"
  title="削除"
>
  {deleting === run.id ? '...' : '×'}
</div>
```

Add `relative` to the parent button's className for absolute positioning of the delete button.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run src/components/__tests__/sidebar.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Sidebar.tsx frontend/src/components/__tests__/sidebar.test.tsx
git commit -m "fix: add delete button to survey history sidebar entries

Root cause: DELETE /api/history/{run_id} endpoint and api.deleteHistoryRun()
existed but no UI element triggered them. Old/failed runs accumulated
with no way to remove them."
```

---

## Task 5: Fix deep-dive LLM cutoff — increase token budget and handle unclosed think tags

**Files:**
- Modify: `backend/llm.py`
- Create: `backend/tests/test_stream_thinking.py`

- [ ] **Step 1: Write tests for _stream_split_thinking edge cases**

Create `backend/tests/test_stream_thinking.py`:

```python
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import _stream_split_thinking


async def collect(source):
    results = []
    async for item in _stream_split_thinking(source):
        results.append(item)
    return results


async def async_iter(chunks):
    for c in chunks:
        yield c


@pytest.mark.asyncio
async def test_plain_answer_no_thinking():
    chunks = ["Hello", " world"]
    result = await collect(async_iter(chunks))
    assert all(kind == "answer" for kind, _ in result)
    full = "".join(text for _, text in result)
    assert full == "Hello world"


@pytest.mark.asyncio
async def test_complete_think_block():
    chunks = ["<think>", "reasoning", "</think>", "answer text"]
    result = await collect(async_iter(chunks))
    kinds = [k for k, _ in result]
    assert "think" in kinds
    assert "answer" in kinds
    think_text = "".join(t for k, t in result if k == "think")
    assert think_text == "reasoning"
    answer_text = "".join(t for k, t in result if k == "answer")
    assert answer_text == "answer text"


@pytest.mark.asyncio
async def test_unclosed_think_tag_yields_thinking_not_lost():
    """Critical bug fix: if stream ends mid-<think> (token budget exhausted),
    the thinking buffer must still be yielded, not silently discarded."""
    chunks = ["<think>", "English reasoning that runs out of tok"]
    result = await collect(async_iter(chunks))
    # Must yield the thinking content even though </think> never appeared
    assert len(result) >= 1
    think_items = [(k, t) for k, t in result if k == "think"]
    assert len(think_items) == 1
    assert "English reasoning" in think_items[0][1]


@pytest.mark.asyncio
async def test_think_split_across_chunks():
    chunks = ["<thi", "nk>", "deep thought", "</thi", "nk>", "final answer"]
    result = await collect(async_iter(chunks))
    think_text = "".join(t for k, t in result if k == "think")
    answer_text = "".join(t for k, t in result if k == "answer")
    assert think_text == "deep thought"
    assert answer_text == "final answer"
```

- [ ] **Step 2: Run tests to verify unclosed-think test fails**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_stream_thinking.py -v`
Expected: `test_unclosed_think_tag_yields_thinking_not_lost` FAILS (current code discards buffer)

- [ ] **Step 3: Fix _stream_split_thinking in llm.py**

In `backend/llm.py`, change line 181 from:

```python
    if buf and not in_think:
        yield ('answer', buf)
```

to:

```python
    # Handle remaining buffer
    if in_think:
        # Stream ended inside unclosed <think> — yield what we have
        yield ('think', think_buf + buf)
    elif buf:
        yield ('answer', buf)
```

- [ ] **Step 4: Update stream_followup_answer to use followup_max_tokens**

In `backend/llm.py`, change line 263 from:

```python
            max_tokens=settings.llm_max_tokens,
```

to:

```python
            max_tokens=settings.followup_max_tokens,
```

- [ ] **Step 5: Run tests to verify all pass**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/test_stream_thinking.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/llm.py backend/config.py backend/tests/test_stream_thinking.py
git commit -m "fix: deep-dive LLM cutoff — increase followup tokens and handle unclosed think tags

Two root causes:
1. followup_max_tokens was shared with survey at 512 — now separate at 2048
2. _stream_split_thinking silently discarded thinking buffer when stream
   ended inside unclosed <think> tag (token budget exhausted mid-think)"
```

---

## Task 6: Fix persona profile truncation in deep-dive view

**Files:**
- Modify: `frontend/src/components/FollowUpChat.tsx`

- [ ] **Step 1: Make persona profile expandable**

In `frontend/src/components/FollowUpChat.tsx`, replace the persona card section (lines 124-141) to make the truncated persona text expandable:

Add state at the top of the component:

```typescript
const [profileExpanded, setProfileExpanded] = useState(false)
```

Replace line 140 (`<div className="text-xs text-gray-400 mt-2 line-clamp-3">...`) with:

```tsx
<button
  onClick={() => setProfileExpanded(!profileExpanded)}
  className="text-left w-full"
>
  <div className={`text-xs text-gray-400 mt-2 ${profileExpanded ? '' : 'line-clamp-3'}`}>
    {followupPersona.persona}
  </div>
  <div className="text-[10px] text-gray-600 mt-1 hover:text-gray-400 transition-colors">
    {profileExpanded ? '▲ 折りたたむ' : '▼ すべて表示'}
  </div>
</button>
```

Remove the hardcoded `?.slice(0, 120)` and the trailing `...` — the `line-clamp-3` CSS handles truncation visually, and expanding shows the full text.

- [ ] **Step 2: Run frontend tests**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/FollowUpChat.tsx
git commit -m "fix: make persona profile expandable in deep-dive view

Was truncated with line-clamp-3 and .slice(0,120) with no way to see
the full profile. Now toggles between collapsed and expanded."
```

---

## Task 7: Update remaining test files and run full suite

**Files:**
- Modify: `backend/tests/test_survey_sse.py` (if broken by survey.py changes)
- Modify: `backend/tests/test_followup_sse.py` (if broken)
- Modify: `backend/tests/test_e2e_mock.py` (if broken)
- Modify: `backend/tests/test_ready_endpoint.py` (update for new error state)

- [ ] **Step 1: Update test_ready_endpoint.py for error state**

Add a test for the error case:

```python
def test_ready_returns_500_on_init_error(app_client):
    main._db_ready.set()
    main._db_init_error = "Test error"
    try:
        resp = app_client.get("/ready")
        assert resp.status_code == 500
        assert "error" in resp.json()["status"]
    finally:
        main._db_init_error = None
        main._db_ready.clear()
```

- [ ] **Step 2: Fix any remaining broken test imports**

Test files that import `PERSONA_DDL` or `settings.db_path` for persona SQLite need to be updated to use `PersonaStore` + `patch("routers.personas.get_store")` or `patch("routers.survey._get_persona")` patterns instead.

Key files to check:
- `test_survey_sse.py` — replace persona SQLite setup with `patch` of `_get_persona`
- `test_followup_sse.py` — may still use history.db SQLite (fine to keep)
- `test_e2e_mock.py` — replace persona SQLite setup

- [ ] **Step 3: Run full backend test suite**

Run: `cd /gen-ai/finance/nemotron-finance-demo/backend && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Run full frontend test suite**

Run: `cd /gen-ai/finance/nemotron-finance-demo/frontend && npx vitest run`
Expected: All PASS

- [ ] **Step 5: Commit any test fixes**

```bash
git add backend/tests/
git commit -m "test: update test fixtures for persona DataFrame migration"
```

---

## Task 8: Update startup scripts and README for DataFrame migration

**Files:**
- Modify: `setup-env.sh`
- Modify: `start.sh`
- Modify: `README.md`

The persona data is no longer loaded into SQLite — it's held in-memory from the parquet file. References to `personas.db` and `DB_PATH` must be updated.

- [ ] **Step 1: Update setup-env.sh**

Remove the `DB_PATH` variable entirely. It's no longer used.

1. Line 136: Change `"Data directory (SQLite DBs)"` → `"Data directory (parquet + history DB)"`
2. Line 142: Remove `DB_PATH="$DATA_DIR/personas.db"`
3. Lines 145-146: Remove `info "DB_PATH       = $DB_PATH"`, keep the HISTORY_DB line
4. Line 125-126: Add a new prompt for `FOLLOWUP_MAX_TOKENS` after the `LLM_MAX_TOKENS` prompt:

```bash
ask "Max tokens for follow-up chat" "2048"
read -r FOLLOWUP_MAX_TOKENS; FOLLOWUP_MAX_TOKENS="${FOLLOWUP_MAX_TOKENS:-2048}"
```

5. In the `.env` output block (line 164-187):
   - Remove `DB_PATH=$DB_PATH` line
   - Add `FOLLOWUP_MAX_TOKENS=$FOLLOWUP_MAX_TOKENS` after `REPORT_MAX_TOKENS`

- [ ] **Step 2: Update start.sh**

Line 40: The `/ready` endpoint now returns HTTP 500 on init error (not just 503 during loading). Update the readiness check to handle this:

```bash
READY_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ready 2>/dev/null)
if [ "$READY_STATUS" = "200" ]; then
    echo " ready."
    break
elif [ "$READY_STATUS" = "500" ]; then
    echo
    echo "ERROR: Database initialization failed."
    curl -s http://127.0.0.1:8080/ready | python3 -c "import sys,json; print(json.load(sys.stdin).get('detail',''))" 2>/dev/null
    exit 1
fi
```

Replace the existing `curl -fsS http://127.0.0.1:8080/ready` check (lines 40-41) with this block.

- [ ] **Step 3: Update README.md**

Key changes:

1. **Architecture diagram** (line 27-28): Replace `│  SQLite (personas)   │` with `│  Pandas (in-memory)   │` and `│  SQLite (history)    │` stays as-is.

2. **Preset table** (line 96): Change `repo-local SQLite in ./data` → `repo-local data in ./data`

3. **Config reference table** (lines 113-128):
   - Remove the `DB_PATH` row entirely
   - Update `DATA_DIR` description: `"Default directory for parquet and history database"` instead of `"Default directory for SQLite databases"`
   - Add row: `FOLLOWUP_MAX_TOKENS` | `2048` | `Max tokens per follow-up chat answer`

4. **First Run section** (lines 222-236): Replace with:

```markdown
## First Run — Persona Data

On first startup the backend checks for the persona parquet file. If it doesn't exist:

1. **Auto-download** (no `PERSONA_PARQUET_PATH` set): downloads the dataset from HuggingFace Hub (`nvidia/Nemotron-Personas-Japan`, ~1.6 GB parquet).
2. **From local parquet** (`PERSONA_PARQUET_PATH` set): loads directly from the specified file.

The parquet is loaded into an in-memory pandas DataFrame (~2-3 GB RAM). This is much faster than the previous SQLite approach — startup completes in seconds after the initial download.

To pre-download before the event:
```bash
cd backend
source venv/bin/activate
python -c "from persona_store import init_persona_store; init_persona_store()"
```
```

5. **Project structure** (line 307): Change `│   ├── db.py                 # SQLite init, persona loading` → `│   ├── db.py                 # History DB init (SQLite)` and add `│   ├── persona_store.py      # In-memory persona store (pandas DataFrame)`

6. **Dataset section** (line 352): Remove the line about `persona_financial_context` SQLite table — financial extension data is now a column in the DataFrame.

- [ ] **Step 4: Commit**

```bash
git add setup-env.sh start.sh README.md
git commit -m "docs: update startup scripts and README for pandas DataFrame migration

Remove DB_PATH references, add FOLLOWUP_MAX_TOKENS config, update
architecture diagram and first-run instructions to reflect in-memory
persona store instead of SQLite."
```

---

## Summary of changes by bug

| Bug | Root Cause | Fix | Key Files |
|-----|-----------|-----|-----------|
| 1. Loading freeze | Missing `idx_education` → 171s query; no error state on init fail | Replace SQLite with in-memory pandas; report errors on `/ready` | `persona_store.py`, `main.py`, `personas.py`, `App.tsx` |
| 2. Undeletable history | No delete UI despite backend + API existing | Add delete button with `stopPropagation` | `Sidebar.tsx` |
| 3. LLM cutoff | `max_tokens=512` shared; unclosed `<think>` buffer silently discarded | Separate `followup_max_tokens=2048`; yield unclosed think buffer | `llm.py`, `config.py` |
| 4. Profile truncation | `line-clamp-3` + `.slice(0,120)` with no expand | Collapsible toggle showing full persona text | `FollowUpChat.tsx` |
