# Completed-Run Navigation and Persona Profile Consistency Bug Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan. Before claiming completion, use superpowers:verification-before-completion. Final acceptance requires a real-LLM E2E test run.

**Goal:** Fix the finished-survey flow so Tabs `(1)` to `(5)` stay consistent and usable after report completion, with read-only review behavior for completed runs and shared persona detail access across tabs.

**Architecture:** This is primarily a frontend state-management and rendering fix, plus a small backend history-contract extension. The UI currently restores only part of the persisted state for completed history entries, several tab views still depend on transient local state, and the history payload does not include the final `enable_thinking` value needed for a correct Step 2 review screen. The fix should centralize completed-run review state in the store, restore all needed persona/report context from history loads, persist and expose the final thinking-mode setting, and move persona-detail modal ownership to shared app state.

**Tech Stack:** React 18, Zustand, Vite, Vitest, Playwright, FastAPI backend with SSE survey/follow-up endpoints.

---

## Summary

This repo is a financial survey demo with a 5-step UI:

1. `ペルソナ選択`
2. `調査設定`
3. `調査実行`
4. `レポート`
5. `深掘り`

The reported problem is that after a survey completes, the app behaves like a partially-reset draft instead of a stable finished run:

- Step 3 can become inaccessible again.
- Opening Step 3 can auto-jump back to Step 4.
- Step 1 becomes blank after navigating away from it.
- Persona financial status is only reliably visible in Step 1 before the survey progresses.
- Persona detail/profile access is inconsistent across tabs.
- Tab 2 must never create a new survey run except via the explicit start action.

A concrete completed run was inspected in local history DB:

- `run_id`: `2763e141-add3-48fa-be44-58d6bd2e83d5`
- status: `completed`
- persona_count: `8`
- saved answers: `24`
- questions: `3`
- cached report: present, with 3 top picks

That means the frontend already has enough persisted persona/report data to support most of a read-only completed-run review flow, but not the final thinking-mode setting shown in Step 2. The plan therefore includes a minimal backend schema/API change for `enable_thinking`.

## Required Execution Conditions

- Use Codex superpowers to execute this plan.
- Preferred execution mode: `subagent-driven-development`.
- Acceptable fallback: `executing-plans` if the work stays in one session.
- Before completion, use `verification-before-completion`.
- Final exam is mandatory: run a real-LLM E2E test after implementation.
- Do not treat unit tests or mocked E2E coverage as sufficient completion evidence.

## Current Findings

### Verified root cause 1: completed history loads do not restore full run session state

In `frontend/src/components/Sidebar.tsx`, `loadRun()` only reconstructs `selectedPersonas`, `personaStates`, and survey counts for `running` / `failed` runs.

For `completed` runs:

- `currentReport` is restored
- `currentRunId`, `surveyTheme`, `questions`, and `currentHistoryRun` are restored
- but `selectedPersonas` and `personaStates` are not reconstructed

This causes:

- Step 3 nav gating to fail later because it depends on `personaStates`
- Step 1 to lose sampled persona content because it depends on component-local state and/or missing store state
- cross-tab persona context to disappear after history restore

### Verified root cause 2: Step 3 auto-report logic is tied to mount/reopen behavior

In `frontend/src/components/SurveyRunner.tsx`, a `useEffect` auto-generates the report and calls `setStep(4)` after survey completion.

That is correct for the first completion of a live run, but wrong when Step 3 is reopened later for a finished run. Reopening Step 3 should show the completed transcript, not immediately navigate away again.

### Verified root cause 3: Step 1 sampled persona UI is local, not durable

In `frontend/src/components/FilterPanel.tsx`, sampled personas are stored in local component state (`personas`), while the wider app depends on store state for navigation and history.

This causes the sampled-persona panel to disappear when Step 1 remounts, even if `selectedPersonas` still exists.

### Verified root cause 4: persona detail UI is implemented only for Step 1

`frontend/src/components/PersonaCards.tsx` owns its own selected persona and opens `frontend/src/components/PersonaDetailModal.tsx` locally.

Other tabs reuse persona snippets, but do not share the same detail-modal capability. As a result:

- finance profile visibility is inconsistent
- the user cannot inspect the same persona profile from Steps 3, 4, and 5

### Verified root cause 5: Step 1 review mode spans `App.tsx`, not just `FilterPanel.tsx`

In `frontend/src/App.tsx`, Step 1 always renders `WelcomeScreen` above `FilterPanel`.

That means completed-run read-only behavior cannot be implemented correctly by changing only `frontend/src/components/FilterPanel.tsx`. If review mode leaves the normal Step 1 shell intact, the user will still see and be able to trigger:

- quick demo start
- custom survey start

For completed-run review, those entry points must be hidden or replaced with a read-only completed-run header/state. The only explicit way out of review mode should remain `＋ 新規調査`.

### Verified root cause 6: Step 4 profile affordance lives in `TopPickCard.tsx`

The Step 4 top-pick header/card UI is rendered by `frontend/src/components/TopPickCard.tsx`, not directly by `frontend/src/components/ReportDashboard.tsx`.

That means a plan that requires a Step 4 profile affordance but only lists `ReportDashboard.tsx` as the Step 4 render surface is incomplete. The implementation must either:

- add a dedicated profile-open affordance in `TopPickCard.tsx`
- or move top-pick rendering responsibility, explicitly, before implementation begins

### Verified root cause 7: history detail does not expose the final thinking-mode setting

In `backend/db.py`, `survey_runs` has no `enable_thinking` column. In `backend/routers/survey.py`, run creation does not persist that value. In `backend/models.py` and `backend/routers/history.py`, `SurveyRunDetail` does not return it.

That means Step 2 cannot truthfully render the completed run's final thinking-mode state from history. Any frontend-only implementation would have to guess. The plan must therefore add backend persistence and history API support for `enable_thinking`, or explicitly drop the Step 2 requirement. This plan keeps the requirement and adds the backend support.

### Verified root cause 8: Step 5 navigation is currently enabled by report presence, not interviewee state

In `frontend/src/components/StepIndicator.tsx`, Step 5 becomes navigable whenever `currentReport !== null`. In `frontend/src/components/FollowUpChat.tsx`, the screen only works when `followupPersona` is set.

Completed history loads currently restore `currentReport` but do not restore a deterministic active interviewee. As written, the top nav can therefore route a completed run into the broken `ペルソナが選択されていません` screen. The plan must either restore interviewee state from durable data or gate Step 5 until the user explicitly selects a persona from Step 4. It must not guess.

### Current evidence on issue 5

From code inspection, new history runs are only created by `/api/survey/run`, which is called by `startSurvey()`. Tab 2 field edits do not directly call that endpoint in the current code. Implementation should still harden this behavior and verify it with tests, since the user reports extra unfinished jobs in the left sidebar and wants a guarantee that only explicit start actions can create runs.

## Required Product Behavior

### Completed-run behavior

After a survey report is complete:

- Tabs `(1)`, `(2)`, and `(3)` must remain accessible.
- These tabs should be read-only review screens for the completed run.
- Reopening any of them must not mutate the run or create a new run.
- Step 4 remains the primary completed destination, but it must no longer trap the user.
- Step 1 completed review must not expose draft-start actions such as quick demo or custom survey start. The user must explicitly leave review mode via `＋ 新規調査` before any new run can begin.

### Step 1 behavior

For a completed run, Step 1 should:

- look visually finished
- show the sampled personas from the completed run
- keep financial badges/status visible
- allow opening the persona detail modal
- not behave like an editable filter/sampling draft
- not render active quick-demo or custom-survey entry points inside the Step 1 content area

Do not require historical filters to be restorable exactly; live runs currently do not persist `filter_config_json` in the normal survey path.

### Step 2 behavior

For a completed run, Step 2 should:

- show final theme, label, questions, and thinking setting
- be read-only
- never start new work from edits, because there should be no edits

### Step 3 behavior

For a completed run, Step 3 should:

- show the completed survey transcript
- remain accessible via top navigation
- not auto-switch back to Step 4
- keep row click for transcript selection
- open persona details from the visible persona header/avatar/name

### Step 5 behavior

For a completed run, Step 5 should:

- never be reachable from the top nav unless an interviewee persona is active
- reuse saved follow-up chat history when that interviewee has existing messages
- never open to the empty `ペルソナが選択されていません` state via completed-run top-nav navigation
- remain disabled for completed history loads until the user selects an interviewee from Step 4, unless a deterministic restored interviewee exists from durable state

Do not guess at an interviewee based only on report order or other weak heuristics.

### Persona detail behavior

Persona detail access should behave consistently across tabs:

- Step 1 persona cards: open detail modal
- Step 3 current visible persona header: open detail modal
- Step 4 top-pick persona card/header area: open detail modal
- Step 5 interviewee header: open detail modal

The same shared modal should show the same finance profile fields everywhere:

- `financial_literacy`
- `annual_income_bracket`
- `asset_bracket`
- `primary_bank_type`
- `investment_experience`
- `financial_concerns`

### Run-creation rule

Only these UI actions may create a new run-history entry:

- Quick demo start
- Explicit `調査を開始する` button

Everything else must not create a run:

- changing theme
- changing label
- changing preset
- editing questions
- toggling thinking mode
- visiting or revisiting completed review tabs

## Implementation Changes

### Task 1: Add persisted review metadata and shared completed-run state

**Files:**

- Modify: `backend/db.py`
- Modify: `backend/models.py`
- Modify: `backend/routers/survey.py`
- Modify: `backend/routers/history.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/store.ts`
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/components/StepIndicator.tsx` if navigation gating or completed-state rendering still depends on draft-only flags

Implement persisted review metadata plus store-level state/helpers for:

- whether the app is showing a completed run in review mode
- final `enableThinking` value restored from history, not inferred
- shared persona-detail modal state:
  - active persona
  - open action
  - close action

Do not infer review mode from `currentStep` alone. It should be derived from persisted run context, such as:

- `currentHistoryRun?.status === 'completed'`
- or a completed current session with stable report and restored persona state

When loading history:

- persist `enable_thinking` in `survey_runs`, backfill older rows to a safe default, and return it from `/api/history/{run_id}`
- restore `enableThinking` from the history payload instead of guessing from current UI state
- always restore `selectedPersonas` and reconstructed `personaStates` for completed runs
- always restore survey counts for completed runs
- explicitly restore completed-session flags needed by shared navigation and Step 3 rendering, rather than leaving completed history runs in a draft-like state
- keep `currentHistoryRun`, `currentRunId`, `surveyTheme`, `questions`, and `currentReport` aligned
- make Step 5 top-nav eligibility depend on an active follow-up persona or other deterministic restored interviewee state, not just `currentReport`
- if no deterministic interviewee can be restored for a completed run, keep Step 5 disabled until the user selects one from Step 4

This reconstruction should reuse the existing logic currently used for interrupted runs rather than duplicating it.

### Task 2: Make Step 1 render from durable store state

**Files:**

- Modify: `frontend/src/App.tsx`
- Add: `frontend/src/components/CompletedFilterReview.tsx` (preferred), or explicitly add a no-side-effects review mode to `frontend/src/components/FilterPanel.tsx`
- Modify: `frontend/src/components/FilterPanel.tsx` only if shared presentation pieces must be extracted or a guarded review mode is introduced

Refactor Step 1 so the completed-review surface is driven by durable store state, not local `personas` or hidden draft state.

Do not mount the current draft `FilterPanel` unchanged in completed review mode. Today it auto-randomizes filters on first render and triggers live `api.getCount()` fetches for non-default state. Completed review must bypass those side effects entirely.

For completed review mode:

- show a completed-step header/state
- replace or suppress the normal `WelcomeScreen` draft-entry actions for this mode
- render sampled personas from restored `selectedPersonas`
- hide or disable filter mutation controls and sampling actions
- avoid mount-time randomization, live count fetches, and any mutation of local draft filter state
- show the sampled persona grid from restored `selectedPersonas`
- preserve finance badge rendering
- open the shared persona-detail modal instead of a local modal

For non-review mode:

- preserve current persona selection workflow

Do not silently change the semantics of `new survey`; `resetSurvey()` should still clear review state and return the user to a fresh editable Step 1.

### Task 3: Make Step 2 a read-only summary for completed runs

**Files:**

- Modify: `frontend/src/components/SurveyConfig.tsx`

Add completed review rendering:

- theme shown but not editable
- label shown but not editable
- questions shown but not editable
- thinking mode shown from persisted history data as the final setting, not togglable
- no question generation button
- no survey start button

For active draft mode:

- preserve current editing behavior
- ensure field edits remain pure state updates and never start a run

### Task 4: Prevent Step 3 from auto-redirecting after completion

**Files:**

- Modify: `frontend/src/components/SurveyRunner.tsx`

Refactor report-generation logic so the auto-transition to Step 4 happens only for the first completion of a live survey run.

The effect must not fire when:

- revisiting Step 3 after report generation already happened
- opening a completed history run
- opening Step 3 for a completed run that already has `currentReport`

Keep explicit report navigation via button.

Completed history runs reopened in Step 3 must also render with completed-state copy/controls, not live-run copy derived from missing flags. If `SurveyRunner` still keys its header or CTA state off `surveyComplete`, Task 1 must restore that state for completed history loads or Task 4 must switch the rendering logic to review-aware derived state.

Also add profile opening on the visible persona header/avatar/name while preserving list-row click for transcript selection.

### Task 5: Lift persona detail modal to app/layout scope and fix Step 5 entry rules

**Files:**

- Modify: `frontend/src/components/PersonaCards.tsx`
- Modify: `frontend/src/components/PersonaDetailModal.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/components/ReportDashboard.tsx`
- Modify: `frontend/src/components/TopPickCard.tsx`
- Modify: `frontend/src/components/FollowUpChat.tsx`
- Modify: `frontend/src/components/SurveyRunner.tsx`

Render the shared modal once near layout/app root.

Refactor `PersonaCards` so it no longer owns local modal state. It should call the shared open-profile action.

Wire shared profile opening from:

- Step 1 card click
- Step 3 visible persona header
- Step 4 top-pick profile affordance
- Step 5 interviewee header

Keep Step 4’s `この人に質問する` action as follow-up-chat navigation, not profile opening.

Also make completed-run Step 5 behavior explicit:

- `FollowUpChat` must work for completed history runs when `followupPersona` is present
- top-nav Step 5 must stay disabled until an interviewee is active, unless Task 1 restored one deterministically
- selecting a top pick from Step 4 must set `followupPersona` and then navigate to Step 5
- completed-run navigation must never land on the empty no-persona screen

### Task 6: Harden and verify run creation boundaries

**Files:**

- Modify backend tests around:
  - `backend/routers/history.py`
  - `backend/routers/survey.py`
- Modify tests around:
  - `frontend/src/components/Sidebar.tsx`
  - `frontend/src/components/SurveyConfig.tsx`
  - `frontend/src/App.tsx`
  - `frontend/src/components/StepIndicator.tsx`
  - `frontend/src/hooks/useSurvey.ts`

Enforce by test that `/api/survey/run` is only reachable through:

- quick demo start
- explicit survey start

Do not add implicit auto-start behavior anywhere else.

Also enforce by test that these actions do not invoke the survey-start path and do not create extra history entries:

- loading a completed history run from the sidebar
- navigating across completed review tabs `(1)` to `(5)`
- reopening Step 3 from a completed run

## Test Cases and Scenarios

### Unit / component tests

Add or update tests for these scenarios:

1. Completed history restore
- Load a completed history run
- Assert `enable_thinking` is present in the restored history payload and store state
- Assert `selectedPersonas` restored
- Assert `personaStates` restored
- Assert completed-session flags/state needed by Step 3 and top-nav rendering are restored
- Assert Step 3 nav is enabled
- Assert Step 1 shows restored sampled personas instead of blank content

2. Step 3 revisit regression
- Start from completed run state with report present
- Open Step 3
- Assert app stays on Step 3
- Assert Step 3 shows completed/review copy instead of live-run copy
- Assert no extra `generateReport()` call happens on revisit

3. Step 1 review mode
- With completed review state, assert filter controls are hidden/disabled
- Assert sampled personas and finance badges are visible
- Assert quick demo and custom survey entry points are absent or disabled
- Assert clicking a persona opens shared detail modal
- Assert Step 1 review mount does not auto-randomize filters or call `api.getCount()`

4. Step 2 review mode
- With completed review state, assert theme/label/questions are rendered read-only
- Assert thinking mode matches the persisted `enable_thinking` value
- Assert generate/start actions are absent or disabled

5. Step 3 profile access
- Assert row click changes displayed transcript
- Assert header/avatar/name opens shared detail modal

6. Step 4 profile access
- Assert top-pick profile affordance opens detail modal
- Assert follow-up action still routes to Step 5

7. Step 5 profile access
- Assert completed history load does not enable/open Step 5 until an interviewee is active, unless one was restored deterministically
- Assert selecting a top pick enables Step 5 and loads the correct interviewee
- Assert interviewee header/avatar/name opens detail modal with finance fields visible
- Assert saved follow-up chat history appears when reopening a completed run with the same interviewee

8. Run creation boundary
- Assert theme/label/preset/question edits never invoke survey start
- Assert only quick demo and explicit start invoke the survey-start path
- Assert loading history and navigating completed review tabs never invoke survey start
- Assert completed-run review navigation does not create an extra sidebar history entry

9. History API contract
- Assert `/api/history/{run_id}` returns `enable_thinking`
- Assert newly created runs persist the requested `enable_thinking` value
- Assert older rows without the column value still deserialize safely under the chosen backfill/default strategy

### Final verification before completion

Run frontend tests first, then run the required real-LLM E2E final exam.

Minimum verification commands:

```bash
cd frontend && npm test
cd frontend && npm run test:e2e:real-llm
```

If the real-LLM suite is too broad or flaky for a focused change, add or run a targeted real-LLM spec that explicitly covers:

- load completed run from history
- visit Steps 1, 2, 3, and 4
- confirm Step 3 does not auto-jump to Step 4
- confirm Step 1 is not blank
- confirm Step 1 review mode does not expose quick demo or custom survey actions
- confirm Step 1 review mode does not trigger draft randomization or live count refresh behavior
- confirm persona detail modal opens from Steps 3, 4, and 5
- confirm Step 4 top-pick profile affordance opens the shared modal without hijacking `この人に質問する`
- confirm Step 5 stays gated until an interviewee is selected, or is restored only from deterministic saved state
- confirm Step 5 opens correctly after selecting an interviewee from Step 4
- confirm no unintended extra run appears in the left sidebar during review-tab navigation

Do not mark the task complete without reporting the exact real-LLM E2E outcome.

## Assumptions and Defaults

- After report completion, Tabs `(1)` to `(3)` are read-only review screens.
- Step 5 is a follow-up screen, not a generic completed-run tab; it requires an active interviewee persona and should remain gated otherwise.
- Step 1 completed view shows sampled personas and run-summary state, not editable historical filters or active draft-start CTAs.
- In Step 3, list-row click remains transcript selection only; profile opens from the visible persona header.
- The Step 4 profile affordance is implemented in the top-pick card surface, while `この人に質問する` remains follow-up-chat navigation.
- Existing backend history data is not sufficient for Step 2 review mode; the plan includes a minimal history schema/API change for `enable_thinking`.
- Real-LLM E2E is the final acceptance gate and is mandatory for completion.
