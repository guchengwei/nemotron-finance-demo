# Remaining Work — Nemotron Finance Demo

_Written 2026-03-19 for handoff. Context compacted after 8-bug fix session._

---

## Current State

- Branch `fix/8-bugs` is open as **PR #1** on GitHub (not yet merged to `main`)
- All 8 bugs implemented, committed, and e2e verified with real LLM
- Backend running on port 8080 (`fix/8-bugs` code), vLLM on port 8000
- Frontend dev server was started at port 5173 during e2e (may or may not still be running)

---

## Checklist: Jobs Remaining

### 1. Merge PR #1

- [ ] Review PR #1: https://github.com/guchengwei/nemotron-finance-demo/pull/1
- [ ] Merge `fix/8-bugs` → `main`
- [ ] Restart backend from `main` after merge

### 2. E2E Browser Test (Blocked by Playwright root sandboxing)

Playwright MCP couldn't launch Chrome (running as root without `--no-sandbox`).
All API-level e2e tests passed. Browser e2e still needs manual or CI verification.

**Manual steps to verify:**
- Step 1: Open app → confirm no 金融リテラシー dropdown in FilterPanel
- Step 1: Sample personas → confirm financial literacy badge visible on cards
- Step 3: Run survey → click persona list items to switch display (Bug 4)
- Step 3: Verify question number shows correctly during thinking (not always Q1)
- After completion: click Step 3 in nav — should stay navigable (Bug 5)
- Step 4: Report loads with spinner animation (not plain text)
- Step 4: Kill backend mid-report → retry button appears (Bug 6)
- Step 4: Click "この人に質問する" on a top pick → follow-up chat loads (Bug 7)

### 3. Additional Tests to Write (from Plan)

The plan specified these tests but they weren't written:

- [ ] **Bug 3 unit test**: `useSurvey.ts` — assert `persona_answer` event sets `activeAnswer: undefined`
- [ ] **Bug 5 unit test**: `StepIndicator` — Step 3 navigable when `personaStates` non-empty
- [ ] **Bug 7 unit test**: `handleChatWithPersona` — both `selectedPersonas` and `currentHistoryRun` paths
- [ ] **Backend e2e test** `backend/tests/test_report_e2e.py`:
  - Seed DB with nested `financial_extension` personas
  - Call `/api/report/generate`
  - Assert `by_financial_literacy` non-empty
  - Assert `top_picks` has 3 valid UUIDs
  - Assert report is cached (second call same data)
  - Test small (3 personas) and large (50+) surveys

### 4. Report Deduplication (Race Condition — from Bug 6 plan)

The plan described a race between 3 callers all triggering report generation:
- `SurveyRunner.tsx` (auto-triggers 1.5s after completion)
- `ReportDashboard.tsx` (triggers on mount)
- `Sidebar.tsx` (triggers on history restore)

**Implemented:** Each caller independently calls `api.generateReport()`. Backend handles this via DB caching (`report_json` column) — second call returns cached. No client-side deduplication was added.

**If duplicate in-flight calls cause UI issues:** implement the `generateReportIfNeeded` store action described in the plan (promise deduplication in `store.ts`).

### 5. vLLM Prefix Caching Verification

- [ ] Add `--enable-prefix-caching` to vLLM launch args if not already set (check vLLM logs)
- [ ] Check `cached_tokens` in backend logs after report generation — should be non-zero for calls 2+3
- Current vLLM launch: `vllm serve nvidia/NVIDIA-Nemotron-Nano-9B-v2-Japanese --host 0.0.0.0 --port ...`
- The backend now logs `cached_tokens` via `logger.info("group_tendency cached_tokens=...")` etc.

### 6. Remaining Unused Functions in report.py

After Bug 8, these old functions are now unused (not called from the endpoint):
- `_build_answers_summary()` — replaced by `_build_question_aggregation()`
- `_build_candidate_personas_block()` — replaced by `_build_top_pick_candidates()`
- `large_survey` variable in the endpoint

These are dead code but harmless. Remove if desired.

---

## What Was Fixed (Bug Summary)

| Bug | File(s) | Fix |
|-----|---------|-----|
| 1 | FilterPanel.tsx, persona_store.py, personas.py, models.py, followup.py, report.py | Removed 金融リテラシー filter; fixed nested `financial_extension` lookup |
| 2 | PersonaCards.tsx, SurveyRunner.tsx | Added financial literacy badge to persona list |
| 3 | hooks/useSurvey.ts | `activeAnswer: ''` → `activeAnswer: undefined` |
| 4 | SurveyRunner.tsx | Added `manualDisplayUuid` state, wired persona list onClick |
| 5 | StepIndicator.tsx | Step 3 returns `personaStates.length > 0` instead of `false` |
| 6 | ReportDashboard.tsx | Spinner animation, error state + retry button, empty top_picks warning |
| 7 | ReportDashboard.tsx | Fixed `||` vs `?:` operator precedence crash in `handleChatWithPersona` |
| 8 | llm.py, prompts.py, report.py | Split 1 LLM call → 3 focused calls; redesigned data prep; structured_outputs for top_picks |

---

## Key Architecture Notes

### financial_extension Schema (Important!)

Persona data flows through two paths:
1. **PersonaStore DataFrame** (from parquet) — top-level columns. Does NOT have `financial_literacy`.
2. **`persona_full_json` in survey_answers** — serialized JSON. `survey.py` overlays financial data as `{"financial_extension": {...}}` (nested).

All consumers of `persona_full_json` must check nested `financial_extension`:
```python
fe = persona.get("financial_extension") or {}
lit = persona.get("financial_literacy") or fe.get("financial_literacy")
```
This is now fixed in `report.py` (`_aggregate_scores`) and `followup.py`.

### Report Generation (3-Call Split)

`/api/report/generate` now makes 3 sequential LLM calls:
1. `generate_report_group_tendency(shared_system)` → plain text
2. `generate_report_conclusion(shared_system, group_tendency)` → plain text
3. `generate_report_top_picks(shared_system, top_pick_candidates)` → list[dict] via structured_outputs

All 3 share the same `REPORT_SHARED_SYSTEM` prefix for KV cache reuse.
Fallbacks: `build_fallback_group_tendency()`, `build_fallback_conclusion()`, `build_fallback_top_picks()`.

### nemotron_nano_v2_reasoning_parser.py

Untracked file in root (seen in git status). Not part of these fixes. Likely the custom vLLM reasoning parser for splitting `<think>` from answers.

---

## Running the App

```bash
# Backend (from repo root)
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8080 --env-file ../.env

# Frontend (dev)
cd frontend && npm run dev -- --host 0.0.0.0 --port 5173

# vLLM (already running as PID 184024 as of 2026-03-19)
# Do NOT restart unless changing model or vLLM params
```

## Test Commands

```bash
# Backend
cd backend && python -m pytest --tb=short -q
# Expected: 47/48 pass (1 pre-existing .env worktree path test)

# Frontend
cd frontend && npm test
# Expected: 14/14 pass
```
