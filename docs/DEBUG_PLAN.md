# Debug Plan: 5 Issues in Nemotron Finance Demo

## Application Overview

This is a **Japanese-language financial market research app** that uses AI-generated personas to simulate survey responses. The stack is:

- **Frontend**: React 18 + TypeScript + Vite + Tailwind CSS + Zustand (state management) + Recharts (charts)
- **Backend**: FastAPI + Python + aiosqlite (SQLite) + OpenAI-compatible client
- **LLM**: NVIDIA Nemotron-Nano-9B-v2-Japanese served via **vLLM** with a custom reasoning parser

### How the App Works (5 Tabs)

1. **Tab 1 (ペルソナ選択)**: Welcome screen + persona filter panel. Users select AI personas from a database.
2. **Tab 2 (調査設定)**: Configure survey theme, questions, and thinking mode toggle. Can auto-generate questions via LLM.
3. **Tab 3 (調査実行)**: Execute the survey — each persona answers each question via SSE streaming. Scores are extracted from answers.
4. **Tab 4 (レポート)**: Auto-generated report with overall score, group tendency, conclusion, demographic charts, and top-pick personas.
5. **Tab 5 (深掘り)**: Follow-up chat with individual personas for deeper insights.

### Key Architecture Details

- **vLLM Reasoning Parser** (`nemotron_nano_v2_reasoning_parser.py`): At server startup, reads `chat_template_kwargs.enable_thinking` to choose between `StringThinkReasoningParser` (thinking ON) or `IdentityReasoningParser` (thinking OFF). This is a **server-level** setting, NOT per-request.
- **Per-request `enable_thinking`**: Sent via `extra_body["chat_template_kwargs"]["enable_thinking"]` — only affects the **Jinja2 chat template** (asks model not to think). The vLLM parser instance is unchanged.
- **Reasoning tokens count against `max_tokens`**: vLLM enforces one completion budget. The parser only post-processes output; it doesn't grant a separate budget for reasoning. If the model thinks despite being told not to, those tokens eat into the content budget.
- **Score extraction**: The system prompt tells the model to use `【評価: X】` format. `extract_score()` in `survey.py` runs on ALL questions, and scores are stored in DB for all questions.
- **State management**: Zustand store (`frontend/src/store.ts`) holds `enableThinking` (defaults to `false`), `selectedPersonas`, `currentRunId`, `personaStates`, `currentHistoryRun`, etc.
- **History DB**: SQLite via aiosqlite. Tables: `survey_runs` (stores `enable_thinking`), `survey_answers` (stores `score`, `question_index`, `persona_uuid`), `followup_chats`.

---

## Bug 1: Tendency/Conclusion Garbage in Tab 4

### Symptom
Report's `group_tendency` and `conclusion` fields show garbled/truncated text. Observed for run_id `a3f2b46e-8f9d-428c-baa6-d365bac1de93`.

### Root Cause
The report generation functions in `backend/llm.py` set `enable_thinking: False` via `extra_body`, but the Nemotron model may still emit `<think>` tokens. Since **reasoning tokens count against `max_tokens`**:

- `generate_report_group_tendency` (line 662): `max_tokens=500` — if model thinks for 400 tokens, only 100 left for content
- `generate_report_conclusion` (line 697): `max_tokens=3000` — less vulnerable but still possible
- `generate_report_top_picks` (line 747): `max_tokens=800` — structured JSON output, easily truncated

If truncation happens mid-`</think>` tag, the parser's `extract_reasoning()` returns `(all_text, None)` — content becomes `None` → empty string.

The existing `_strip_thinking()` function (line 139 of `llm.py`) is still needed as defense-in-depth for edge cases where the parser fails.

### Fix

**File: `backend/llm.py`**

1. **Increase max_tokens** to absorb potential reasoning overhead:
   - Line 662: `max_tokens=500` → `max_tokens=2048`
   - Line 697: `max_tokens=3000` → `max_tokens=4096`
   - Line 747: `max_tokens=800` → `max_tokens=2048`

2. **Add output validation** after sanitize in each function: for text functions (`group_tendency`, `conclusion`), return empty string if result is empty/whitespace-only after `_strip_thinking()` (triggers fallback). For `top_picks`, return `[]` on parse failure (already handled). Do NOT use aggressive length thresholds.

3. **Keep `_strip_thinking()`** — do NOT remove it. It's defense-in-depth.

4. **Add diagnostic logging**: After each report LLM call, log the length of `getattr(resp.choices[0].message, 'reasoning_content', None)` to track whether thinking is happening despite the flag. Log length only, not raw text.

---

## Bug 2: Score Only From Q1

### Assumptions / Decisions
- **Metric change**: Moving from Q1-only to per-persona averaged scores is an intentional product decision that changes the meaning of "overall score" and distribution buckets. Equal-weight per-persona averaging is the intended metric.
- **`_first_answer_excerpt()` Q1 preference**: This function prefers Q1 answers for top-pick highlight quotes. This is a minor Q1 bias but acceptable since it only affects quote selection, not scoring. Full Q1 de-biasing of quotes is out of scope for this fix.

### Symptom
The report's overall score, distribution chart, and demographic breakdown only use scores from question 1 (index 0), ignoring scores from other questions.

### Root Cause
Three places in `backend/routers/report.py` filter to `question_index == 0`:

1. **`_build_persona_records()`** (line 73): `if answer["question_index"] == 0 and answer.get("score") is not None:` — only sets persona score from Q1
2. **`_build_question_aggregation()`** (line 186): `if q_idx == 0:` — only shows score stats for Q1
3. **`_aggregate_scores()`** (line 249): `a["question_index"] == 0` — only collects Q1 scores for distribution/demographics

Scores ARE extracted and stored in DB for all questions (verified in `survey.py` line 128).

### Fix

**File: `backend/routers/report.py`**

**a) `_build_persona_records()` (~line 57)**:
- Remove the `question_index == 0` filter on lines 73-74
- After building all records, compute **average score** across ALL questions with valid scores per persona
- Replace lines 73-74 with: collect all scores per persona, then after the loop, set `record["score"] = round(mean(scores), 1)` if any scores exist

```python
# In the per-answer loop, collect scores:
if answer.get("score") is not None:
    record.setdefault("_scores", []).append(answer["score"])

# After the loop, compute averages:
for record in records.values():
    scores = record.pop("_scores", [])
    if scores:
        record["score"] = round(sum(scores) / len(scores), 1)
```

**b) `_build_question_aggregation()` (~line 174)**:
- Remove the `if q_idx == 0:` guard on line 186
- Show score stats for ALL questions that have scores

```python
# Replace:
if q_idx == 0:
    scores = [a["score"] for a in q_list if a.get("score") is not None]
# With:
scores = [a["score"] for a in q_list if a.get("score") is not None]
```

**c) `_aggregate_scores()` (~line 247)**:
- Remove `a["question_index"] == 0` filter on lines 249 and 265
- Compute **per-persona average scores** (each persona contributes one average to distribution/demographics)
- Change approach: first collect all scores per persona across all questions, then average per persona

```python
# Step 1: Collect all scores per persona
persona_scores: dict[str, list[int]] = defaultdict(list)
persona_data_cache: dict[str, dict] = {}
for a in answers:
    if a.get("score") is not None:
        uuid = a["persona_uuid"]
        persona_scores[uuid].append(a["score"])
        if uuid not in persona_data_cache:
            try:
                persona_data_cache[uuid] = json.loads(a.get("persona_full_json") or "{}")
            except Exception:
                persona_data_cache[uuid] = {}

# Step 2: Compute per-persona averages
persona_avgs: dict[str, float] = {}
for uuid, scores_list in persona_scores.items():
    persona_avgs[uuid] = round(sum(scores_list) / len(scores_list), 1)

# Step 3: Build distribution from per-persona averages (round to nearest int)
all_avg_scores = list(persona_avgs.values())
distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
for s in all_avg_scores:
    key = str(round(s))
    if key in distribution:
        distribution[key] += 1

overall = round(sum(all_avg_scores) / len(all_avg_scores), 1) if all_avg_scores else None

# Step 4: Demographics using per-persona averages
for uuid, avg_score in persona_avgs.items():
    p = persona_data_cache.get(uuid, {})
    # ... same demographic bucketing but using avg_score instead of a["score"]
```

---

## Bug 3: Thinking Mode Always On in Tab 3/5

### Symptom
Even with thinking mode toggled OFF in Tab 2, ThinkingBlock components appear in Tab 3 (survey) and Tab 5 (followup). (Tab 4 ReportDashboard does not use ThinkingBlock.)

### Root Cause
Two separate issues:

1. **Backend (Tab 5)**: `backend/routers/followup.py` line 90 calls `stream_followup_answer(system_prompt, messages)` WITHOUT passing `enable_thinking`. The function signature (`llm.py` line 397) defaults to `True`. The run's `enable_thinking` value IS available in the `run` dict (loaded from DB at line 29).

2. **Frontend (Tab 3/5)**: The Nemotron model may still emit `<think>` tokens even when `enable_thinking=False` is sent. The backend's `_stream_split_reasoning()` separates them, and the frontend renders them via `ThinkingBlock` regardless of the user's toggle setting.

### Fix

**File: `backend/routers/followup.py`** (~line 90):
```python
# Change:
async for kind, chunk in stream_followup_answer(system_prompt, messages):
# To:
enable_thinking = bool(run.get("enable_thinking", True))
async for kind, chunk in stream_followup_answer(system_prompt, messages, enable_thinking=enable_thinking):
```

**File: `frontend/src/components/SurveyRunner.tsx`** (~line 14, ThinkingBlock usage):
- Read `enableThinking` from the store
- Conditionally render `ThinkingBlock` only when `enableThinking` is `true`
- Where `ThinkingBlock` is rendered in the answer display, wrap with: `{enableThinking && thinking && <ThinkingBlock thinking={thinking} />}`

**File: `frontend/src/components/FollowUpChat.tsx`** (~line 196):
- Same pattern: read `enableThinking` from store
- Line 196-198: wrap `ThinkingBlock` rendering with `enableThinking` check
- For history runs, the `enableThinking` value is already restored from DB via `Sidebar.tsx` line 116

---

## Bug 4: Tab 1 Resets to Welcome Screen

### Symptom
After selecting personas and entering Tab 2, navigating back to Tab 1 shows the Welcome screen + FilterPanel instead of a read-only review of selected personas.

### Root Cause
`frontend/src/App.tsx` line 136: `CompletedFilterReview` only shows when `currentHistoryRun?.status === 'completed'`. During an active (new) run, `currentHistoryRun` is `null`, so it falls through to WelcomeScreen.

### Fix

**File: `frontend/src/App.tsx`** (~line 135):
Derive `hasActiveWorkflow` and broaden the condition:

```typescript
// In renderStep(), case 1:
case 1: {
  const hasActiveWorkflow = selectedPersonas.length > 0
  if (currentHistoryRun?.status === 'completed' || hasActiveWorkflow) {
    return <CompletedFilterReview badge={
      currentHistoryRun?.status === 'completed'
        ? '完了済み（閲覧のみ）'
        : '設定済み（閲覧のみ）'
    } />
  }
  return (
    <div>
      <WelcomeScreen />
      <div className="mt-8">
        <FilterPanel key={resetVersion} />
      </div>
    </div>
  )
}
```

**File: `frontend/src/components/CompletedFilterReview.tsx`**:
- Accept optional `badge` prop: `export default function CompletedFilterReview({ badge }: { badge?: string })`
- Replace hardcoded `完了済み（閲覧のみ）` on line 15 with `{badge || '完了済み（閲覧のみ）'}`

**File: `frontend/src/components/SurveyConfig.tsx`** (~line 24):
- Also lock config as read-only during active runs (not just completed history):
```typescript
const { currentRunId, personaStates } = useStore()
const isCompletedReview = currentHistoryRun?.status === 'completed'
const isActiveRun = !!(currentRunId || Object.keys(personaStates).length > 0)
const isReadOnly = isCompletedReview || isActiveRun
```
- Use `isReadOnly` instead of `isCompletedReview` for the read-only rendering guard

---

## Bug 5a: Chat Box Layout

### Symptom
The Tab 5 chat box extends beyond one screen height.

### Root Cause

**File: `frontend/src/components/FollowUpChat.tsx`**:
- Line 178: `min-h-[32rem]` on chat container without viewport constraint → extends beyond viewport

### Fix

**Height fix** (`FollowUpChat.tsx` line 178):
```
// Replace:
min-h-[32rem]
// With:
min-h-0
```
Also add `min-h-0` to the root flex container to coordinate with `Layout.tsx`'s existing `overflow-auto` on `<main>`. This avoids double-scroll behavior since `Layout.tsx:21` already has `<main className="flex-1 overflow-auto">`.

---

## Bug 5b: Dynamic Suggested Questions (Enhancement)

> **Note**: This is a new feature, not a bugfix. It requires additional design work before implementation:
> - Cache storage mechanism and invalidation strategy
> - API response shape and error handling
> - Failure fallback behavior (fall back to static questions?)
> - Test coverage (backend unit + frontend component)

### Current State
- Lines 6-10: `SUGGESTED_QUESTIONS` is a hardcoded array of 3 static strings
- Line 219: `messages.length === 0` guard means suggestions disappear after any message

### Proposed Design (requires refinement)

**Backend** (`backend/routers/followup.py`):
- New endpoint `POST /suggestions` with `SuggestionRequest(run_id, persona_uuid)`
- Cache results per `(run_id, persona_uuid)` to avoid repeated LLM calls
- Define error response shape and fallback to static suggestions on failure

**Backend** (`backend/llm.py`):
- New function `generate_followup_suggestions(survey_theme, persona_summary, answer_excerpts) -> list[str]`
- `max_tokens=512`, `temperature=0.7`

**Frontend** (`frontend/src/components/FollowUpChat.tsx`):
- Fetch suggestions on mount / persona change
- Keep suggestions visible after messages (remove `messages.length === 0` guard)
- Filter out already-asked questions

---

## File Summary

| File | Bugs |
|------|------|
| `backend/llm.py` | Bug 1 (max_tokens + validation + logging) |
| `backend/routers/report.py` | Bug 2 (remove Q1 filter, use per-persona averages) |
| `backend/routers/followup.py` | Bug 3 (pass `enable_thinking`) |
| `frontend/src/App.tsx` | Bug 4 (broaden Tab 1 condition) |
| `frontend/src/components/CompletedFilterReview.tsx` | Bug 4 (accept `badge` prop) |
| `frontend/src/components/SurveyConfig.tsx` | Bug 4 (lock for active runs) |
| `frontend/src/components/SurveyRunner.tsx` | Bug 3 (conditional ThinkingBlock) |
| `frontend/src/components/FollowUpChat.tsx` | Bug 3 (conditional ThinkingBlock), Bug 5a (layout fix) |

## Execution Order

1. **Bug 3** — Smallest, clearest code bug. Backend: 1 line in followup.py. Frontend: conditional rendering in 2 files.
2. **Bug 1** — Increase max_tokens + add validation + logging in llm.py.
3. **Bug 2** — Remove Q1 filter in report.py, use per-persona average scores.
4. **Bug 4** — Frontend tab lock in App.tsx + CompletedFilterReview + SurveyConfig.
5. **Bug 5a** — Layout fix in FollowUpChat.tsx.
6. **Bug 5b** — (Enhancement, deferred) Dynamic question generation — requires design review.

## Verification

### Manual Checks
1. **Bug 1**: Generate report → tendency/conclusion are coherent Japanese text (not garbled/truncated). Check backend logs for `reasoning_content` length.
2. **Bug 2**: Report shows average scores from all questions; distribution chart and demographics use all scores. Verify with a run where Q2+ have different scores than Q1.
3. **Bug 3**: Toggle thinking OFF in Tab 2 → Run survey → No ThinkingBlock in Tab 3. Navigate to Tab 5 → No ThinkingBlock. Check backend logs that `enable_thinking=False` is passed in followup.
4. **Bug 4**: Select personas → Go to Tab 2 → Click Tab 1 → See read-only persona review with "設定済み（閲覧のみ）" badge. Also works for completed history runs with "完了済み（閲覧のみ）" badge.
5. **Bug 5a**: Tab 5 chat fits within viewport without double-scroll.

### Automated Test Coverage
Existing test files that should be updated/extended:

| Bug | Test File | What to Test |
|-----|-----------|-------------|
| Bug 1 | `backend/tests/test_report_endpoint.py` | Verify fallback triggers when LLM returns empty after thinking strip |
| Bug 2 | `backend/tests/test_report_endpoint.py:141-173` | Verify per-persona averaging with multi-question scores |
| Bug 3 | `backend/tests/test_followup_sse.py:52-77` | Verify `enable_thinking` is passed from run config |
| Bug 4 | (frontend component test) | Verify Tab 1 shows review when `selectedPersonas.length > 0` |
| Bug 5a | (frontend component test) | Verify chat container has no `min-h-[32rem]` |
