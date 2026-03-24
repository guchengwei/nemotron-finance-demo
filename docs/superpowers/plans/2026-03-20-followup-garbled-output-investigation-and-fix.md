# Follow-Up Garbled Output Investigation And Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore correct Tab 5 follow-up output under the parser-enabled Nemotron/vLLM runtime by identifying and fixing the actual backend failure mode instead of relying on symptom-level prefix filtering.

**Architecture:** Keep the custom Nemotron reasoning parser in place. Assume parser-backed serving is required in this deployment and that server default behavior may be thinking-on unless a request overrides it. The fix should focus on proving whether Tab 5 follow-up breaks because request-time `enable_thinking` handling, parser interaction, or stream decoding diverges from survey/report behavior, then apply the minimal backend change that restores correct follow-up output without changing the overall serving model.

**Tech Stack:** FastAPI, aiosqlite, vLLM OpenAI-compatible streaming API, Python async generators, pytest

---

## Summary

Keep the custom Nemotron reasoning parser in place. Assume parser-backed serving is required in this deployment and that server default behavior may be thinking-on unless a request overrides it. The fix should focus on proving whether Tab 5 follow-up breaks because request-time `enable_thinking` handling, parser interaction, or stream decoding diverges from survey/report behavior, then apply the minimal backend change that restores correct follow-up output without changing the overall serving model.

## File Structure

- Modify: `backend/routers/followup.py`
  - Own the follow-up SSE path, persisted history behavior, and any retry/removal of heuristic output filtering.
- Modify: `backend/llm.py`
  - Own follow-up stream handling and any parser-backed stream interpretation fixes.
- Modify: `backend/tests/test_followup_sse.py`
  - Own unit-level follow-up endpoint regression coverage.
- Modify: `backend/tests/test_stream_reasoning.py`
  - Own low-level parser-backed stream decoding coverage.
- Modify: `backend/tests/test_real_llm_e2e.py`
  - Own real-LLM regression coverage for parser-enabled follow-up behavior.

## Tasks

### Task 1: Reproduce the bug with a failing automated test

**Files:**
- Modify: `backend/tests/test_followup_sse.py`
- Modify: `backend/tests/test_real_llm_e2e.py`

- [ ] **Step 1: Add a focused unit regression test for follow-up output quality**

Write a new test in `backend/tests/test_followup_sse.py` that mocks the follow-up generator with a malformed output shape representative of the observed failure and asserts the endpoint behavior that must hold after the fix:
- no duplicated assistant turn
- no empty final assistant message
- one persisted user row and one persisted assistant row
- no reliance on the current English-prefix heuristic unless explicitly retained by a later failing test

Prefer a behavior-level assertion over internal retry-count assertions.

- [ ] **Step 2: Add a real-LLM regression test for parser-enabled follow-up**

Extend `backend/tests/test_real_llm_e2e.py` with one follow-up regression that runs only in the real-LLM environment and checks:
- follow-up request reaches `event: done`
- visible answer is non-empty user-facing text
- no raw `<think>` tags leak in the final answer
- thinking-off run does not emit `thinking` SSE events

Seed the run with `enable_thinking=0` to match the highest-risk configuration already identified.

- [ ] **Step 3: Run the new tests to verify they fail for the expected reason**

Run:

```bash
pytest -q backend/tests/test_followup_sse.py -k followup
pytest -q backend/tests/test_real_llm_e2e.py -k bug3
```

Expected:
- the new unit regression fails because the current follow-up logic still depends on symptom-level heuristics
- the real-LLM regression fails or reproduces the currently observed broken behavior in the parser-enabled environment

- [ ] **Step 4: Do not commit the red state**

Keep the failing tests local as the TDD red phase. Do not create a checkpoint commit until the minimal fix for this task is green.

### Task 2: Lock down parser-backed stream decoding behavior

**Files:**
- Modify: `backend/tests/test_stream_reasoning.py`
- Modify: `backend/llm.py`

- [ ] **Step 1: Add failing low-level stream decoding tests**

Extend `backend/tests/test_stream_reasoning.py` with cases for:
- parser-backed reasoning followed by content
- transition chunk containing both `reasoning` and `content`
- no reasoning when `enable_thinking=False`
- partial transition boundaries that must not lose the first visible answer tokens
- parser-backed chunks that produce mixed or malformed transitions without leaking reasoning into visible answer content

- [ ] **Step 2: Run the targeted stream tests to verify red**

Run:

```bash
pytest -q backend/tests/test_stream_reasoning.py
```

Expected:
- at least one new parser-backed edge-case test fails against the current implementation

- [ ] **Step 3: Implement the minimal stream decoding fix in `backend/llm.py`**

Limit changes to follow-up-relevant stream interpretation first:
- prefer fixing how parser-backed chunks are interpreted
- preserve the current `('think', text)` / `('answer', chunk)` contract
- do not broaden into unrelated prompt or frontend changes

If survey/report code can reuse the same safe splitter without widening scope, that reuse is acceptable only after the follow-up-specific red test goes green.

- [ ] **Step 4: Run the stream tests again to verify green**

Run:

```bash
pytest -q backend/tests/test_stream_reasoning.py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/llm.py backend/tests/test_stream_reasoning.py
git commit -m "fix: harden parser-backed stream decoding for followup"
```

### Task 3: Remove or constrain the symptom-level follow-up heuristic

**Files:**
- Modify: `backend/routers/followup.py`
- Modify: `backend/tests/test_followup_sse.py`

- [ ] **Step 1: Write or refine the failing endpoint-level test first**

Before changing `backend/routers/followup.py`, ensure `backend/tests/test_followup_sse.py` has a failing test that proves the desired endpoint contract:
- follow-up uses the persisted run `enable_thinking` value
- no silent mode switch unless a test-backed retry policy is explicitly required
- one assistant response is persisted and returned for one user input
- fallback handling remains intact on error/cancel

- [ ] **Step 2: Implement the minimal router fix**

In `backend/routers/followup.py`:
- remove or relax the current English-prefix diagnosis/retry path unless the updated failing tests prove it is still needed
- preserve current persistence behavior for user turns and assistant fallback rows
- preserve current SSE `error` and `done` event contract
- pass the persisted run `enable_thinking` value once and avoid hidden mode changes during normal operation

- [ ] **Step 3: Run follow-up endpoint tests to verify green**

Run:

```bash
pytest -q backend/tests/test_followup_sse.py
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/routers/followup.py backend/tests/test_followup_sse.py
git commit -m "fix: remove followup symptom-level retry heuristics"
```

### Task 4: Verify the parser-enabled real-LLM path end to end

**Files:**
- Modify: `backend/tests/test_real_llm_e2e.py`

- [ ] **Step 1: Run the real-LLM regression test after backend fixes**

Run:

```bash
pytest -q backend/tests/test_real_llm_e2e.py -k bug3
```

Expected:
- parser-enabled follow-up completes successfully
- thinking-off run emits no `thinking` SSE events
- final answer contains no raw `<think>` tags
- no junk or empty output is observed in the captured final answer

- [ ] **Step 2: If the real-LLM test still fails, debug the runtime/path mismatch before adding new heuristics**

Investigate in this order:
1. request-level `enable_thinking` payload
2. parser-backed stream field shape from vLLM
3. follow-up-only prompt or message construction differences

Do not add new visible-text prefix filters unless a new failing test proves they are required.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_real_llm_e2e.py
git commit -m "test: cover parser-enabled followup regression"
```

### Task 5: Final verification and handoff

**Files:**
- No additional production files required

- [ ] **Step 1: Run the full focused backend verification suite**

Run:

```bash
pytest -q backend/tests/test_stream_reasoning.py backend/tests/test_followup_sse.py
pytest -q backend/tests/test_real_llm_e2e.py -k bug3
```

Expected: PASS in environments where real LLM is available; unit tests must pass everywhere.

- [ ] **Step 2: Manual smoke test in the parser-enabled runtime**

Use the existing parser-enabled vLLM startup shape and verify:
- create a run with thinking off
- open Tab 5
- ask multiple follow-up questions for one persona
- confirm no junk output, no raw `<think>` leakage, no hang, and correct chat history persistence

- [ ] **Step 3: Final commit**

```bash
git add backend/llm.py backend/routers/followup.py backend/tests/test_stream_reasoning.py backend/tests/test_followup_sse.py backend/tests/test_real_llm_e2e.py
git commit -m "fix: restore stable followup output with parser-enabled vllm"
```

## Test Cases And Scenarios

- Follow-up with `enable_thinking=False` under parser-enabled vLLM
- Follow-up with `enable_thinking=True` under parser-enabled vLLM
- Transition chunk where reasoning and answer content arrive together
- Parser-backed stream with no visible reasoning section
- Error and cancellation fallback persistence
- Final answer must never persist raw `<think>` tags

## Assumptions And Defaults

- The custom reasoning parser remains required in production.
- Request-level `enable_thinking` is intended to remain supported and must not be silently overridden by router heuristics.
- The first implementation pass is intentionally limited to Tab 5 follow-up and its supporting backend stream-decoding code.
- `README.md` and `setup-env.sh` are out of scope for this pass unless the tested fix proves a startup-flag change is required.
- The plan is intentionally backend-first; no frontend API or SSE schema changes are expected.
