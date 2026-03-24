# Fix Report Prompt Echo Leakage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the LLM from echoing back user prompt text in Tab 4 (report) tendency/conclusion output, and detect+fallback when it happens anyway.

**Architecture:** Two defense layers: (1) prevention via sampling parameters (`repetition_penalty`, `frequency_penalty`, lower temperature), (2) detection via post-generation echo-check that triggers existing fallback logic. All changes are backend-only (`backend/llm.py`, `backend/prompts.py`, `backend/config.py`).

**Tech Stack:** Python 3.11+, FastAPI, OpenAI AsyncClient (vLLM), pytest

**Bug Evidence (run_id `270c4830`):**
- `conclusion` field contained the literal prompt: `"上記を踏まえ、総合結論・金融機関が取るべき推奨アクションを詳しく述べてください。テキストのみ。JSONや説明文は不要です。"`
- `recommended_actions` parsed prompt fragments as actions: `["テキストのみ。", "JSONや説明文は不要です。"]`
- `group_tendency` parroted a single persona's answer instead of synthesizing

**Root Causes:**
1. No `repetition_penalty`/`frequency_penalty` to discourage token regurgitation
2. Temperature too high for non-thinking mode (0.3 vs recommended near-greedy)
3. No post-generation check detects prompt echo-back

**Known Limitations (Parser — tracked separately):**
- vLLM creates a **new parser instance per request** (not per-startup). However, `NemotronNanoV2ReasoningParser.__init__` reads `chat_template_kwargs` from `**kwargs`, but vLLM constructs it as `self.reasoning_parser(tokenizer)` — **no per-request kwargs are passed**. The `enable_thinking` branch at lines 92-97 effectively **always defaults to `True`**.
- The correct fix: rewrite the parser to NOT branch in `__init__`. For non-streaming, read `request` (passed to `extract_reasoning`). For streaming, infer from text shape (always handle `<think>...</think>` gracefully).
- App-layer `_strip_thinking()` already handles leaked `<think>` tags, so the current parser behavior is tolerable but fragile.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/llm.py` | Modify | Add echo detection, adjust sampling params for report calls |
| `backend/prompts.py` | Modify | Extract static instruction constant for safe echo detection |
| `backend/config.py` | Modify | Add `report_temperature`, `report_repetition_penalty`, `report_frequency_penalty` |
| `backend/tests/test_echo_detection.py` | Create | Tests for echo detection utility |
| `backend/tests/test_report_prompt_echo.py` | Create | Integration tests for prompt-echo fallback |

---

### Task 1: Add echo detection utility to `llm.py`

A function that detects when an LLM response contains significant substrings of the prompt text. Returns `True` if the response is echoing the prompt, allowing callers to trigger fallback.

**Files:**
- Create: `backend/tests/test_echo_detection.py`
- Modify: `backend/llm.py:166-171` (after `sanitize_answer_text`)

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_echo_detection.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import detect_prompt_echo


SAMPLE_PROMPT = "集計結果を踏まえ、グループ全体の傾向を簡潔に述べてください。テキストのみ。JSONや説明文は不要です。"

CONCLUSION_PROMPT = "上記を踏まえ、総合結論・金融機関が取るべき推奨アクションを詳しく述べてください。テキストのみ。JSONや説明文は不要です。"


def test_detects_exact_echo():
    """Response that IS the prompt verbatim."""
    assert detect_prompt_echo(SAMPLE_PROMPT, SAMPLE_PROMPT) is True


def test_detects_echo_embedded_in_response():
    """Response contains the prompt text within other content."""
    response = f"NISA制度は好評です。ただし、…\n\n{CONCLUSION_PROMPT}"
    assert detect_prompt_echo(CONCLUSION_PROMPT, response) is True


def test_allows_legitimate_response():
    """Normal analytical response should NOT be flagged."""
    response = "全体として、NISA制度に対する関心は高く、特に非課税期間の無期限化が支持されています。一方、制度の複雑さに対する不安も見られます。"
    assert detect_prompt_echo(SAMPLE_PROMPT, response) is False


def test_allows_short_overlap():
    """Small keyword overlap (e.g. 'テキスト') is not an echo."""
    response = "テキストマイニングの結果、前向きな意見が多数を占めています。"
    assert detect_prompt_echo(SAMPLE_PROMPT, response) is False


def test_handles_empty_strings():
    assert detect_prompt_echo("", "") is False
    assert detect_prompt_echo(SAMPLE_PROMPT, "") is False
    assert detect_prompt_echo("", "some response") is False


def test_detects_partial_prompt_echo():
    """Response contains a large contiguous chunk of the prompt."""
    # Take 80% of the prompt as a chunk
    chunk = CONCLUSION_PROMPT[:int(len(CONCLUSION_PROMPT) * 0.8)]
    response = f"NISA制度は…{chunk}"
    assert detect_prompt_echo(CONCLUSION_PROMPT, response) is True


def test_conclusion_reusing_tendency_is_not_echo():
    """A conclusion that legitimately references the group tendency should NOT be flagged.
    Echo detection for conclusion uses REPORT_CONCLUSION_INSTRUCTION (static only),
    not the full user_content which includes the dynamic group_tendency."""
    from prompts import REPORT_CONCLUSION_INSTRUCTION

    # Conclusion legitimately reuses words from the tendency
    response = "全体的にNISA制度への関心は高く、非課税期間の無期限化が支持されています。金融機関は制度周知の強化が求められます。"
    assert detect_prompt_echo(REPORT_CONCLUSION_INSTRUCTION, response) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_echo_detection.py -v`
Expected: FAIL with `ImportError: cannot import name 'detect_prompt_echo' from 'llm'`

- [ ] **Step 3: Implement `detect_prompt_echo` in `llm.py`**

Add after `sanitize_answer_text` (around line 172):

```python
def detect_prompt_echo(prompt: str, response: str, min_chunk: int = 20) -> bool:
    """Detect if a response contains significant substring overlap with the prompt.

    Uses longest-common-substring check: if any contiguous chunk of the prompt
    (>= min_chunk characters) appears in the response, it's an echo.
    """
    if not prompt or not response or len(prompt) < min_chunk:
        return False
    # Check for any contiguous chunk of the prompt appearing in the response
    # Slide a window of `min_chunk` chars across the prompt
    for i in range(len(prompt) - min_chunk + 1):
        chunk = prompt[i : i + min_chunk]
        if chunk in response:
            return True
    return False
```

- [ ] **Step 4: Extract `REPORT_CONCLUSION_INSTRUCTION` constant in `prompts.py`**

Task 1 test imports `REPORT_CONCLUSION_INSTRUCTION`, so add it now. In `backend/prompts.py`, change lines 155-157:

From:
```python
REPORT_CONCLUSION_USER = """グループ傾向: {group_tendency}

上記を踏まえ、総合結論・金融機関が取るべき推奨アクションを詳しく述べてください。テキストのみ。JSONや説明文は不要です。"""
```

To:
```python
# Static instruction portion — used by echo detection (must NOT include dynamic {group_tendency})
REPORT_CONCLUSION_INSTRUCTION = "上記を踏まえ、総合結論・金融機関が取るべき推奨アクションを詳しく述べてください。テキストのみ。JSONや説明文は不要です。"

REPORT_CONCLUSION_USER = """グループ傾向: {group_tendency}

""" + REPORT_CONCLUSION_INSTRUCTION
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_echo_detection.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/llm.py backend/prompts.py backend/tests/test_echo_detection.py
git commit -m "feat: add detect_prompt_echo utility and REPORT_CONCLUSION_INSTRUCTION constant"
```

---

### Task 2: Wire echo detection into report LLM calls

When the LLM response echoes the user prompt, return empty string to trigger the existing fallback logic in `generate_report_endpoint`.

**Files:**
- Modify: `backend/llm.py:683-762` (report generation functions)
- Create: `backend/tests/test_report_prompt_echo.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_report_prompt_echo.py
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_mock_response(content: str):
    """Build a mock OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.reasoning_content = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


def test_group_tendency_returns_empty_on_echo():
    from prompts import REPORT_GROUP_TENDENCY_USER

    echoed = f"NISAの概要です。{REPORT_GROUP_TENDENCY_USER}"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(echoed)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_group_tendency("shared system prompt")
            )

    assert result == "", f"Expected empty string for echoed response, got: {result!r}"


def test_conclusion_returns_empty_on_echo():
    from prompts import REPORT_CONCLUSION_INSTRUCTION

    tendency = "全体的に前向きです。"
    # Echo contains the static instruction text (not just the tendency)
    echoed = f"結論としては…{REPORT_CONCLUSION_INSTRUCTION}"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(echoed)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_conclusion("shared system prompt", tendency)
            )

    assert result == "", f"Expected empty string for echoed response, got: {result!r}"


def test_group_tendency_passes_through_normal_response():
    """A legitimate analytical response should be returned as-is, not rejected."""
    normal = "全体として、NISA制度に対する関心は高く、特に非課税期間の無期限化が支持されています。一方、制度の複雑さに対する不安も見られます。"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(normal)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_group_tendency("shared system prompt")
            )

    assert result == normal, f"Expected normal response to pass through, got: {result!r}"


def test_conclusion_passes_through_normal_response():
    """A legitimate conclusion should be returned as-is."""
    tendency = "全体的に前向きです。"
    normal = "総合すると、NISA制度の改正は概ね好意的に受け止められており、金融機関は制度周知の強化と個別相談の充実が求められます。"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(normal)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_conclusion("shared system prompt", tendency)
            )

    assert result == normal, f"Expected normal response to pass through, got: {result!r}"


def test_group_tendency_returns_empty_on_null_content():
    """When reasoning parser misroutes content to reasoning_content,
    message.content is None. Should return empty string for fallback."""
    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"

        # Simulate vLLM bug: content is None, answer trapped in reasoning_content
        msg = MagicMock()
        msg.content = None
        msg.reasoning_content = "実際の分析結果がここに入る"
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=resp)

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_group_tendency("shared system prompt")
            )

    assert result == "", f"Expected empty string when content is None, got: {result!r}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_report_prompt_echo.py -v`
Expected: FAIL — the current code returns the echoed text, not empty string

- [ ] **Step 3: Add echo detection to `generate_report_group_tendency`**

In `backend/llm.py`, inside `generate_report_group_tendency` (around line 713), replace the existing return block:

From:
```python
        result = _strip_thinking(raw).strip()
        if not result:
            logger.warning("group_tendency: empty after stripping thinking tags")
            return ""
        return result
```

To:
```python
        result = _strip_thinking(raw).strip()
        if not result:
            logger.warning("group_tendency: empty after stripping thinking tags")
            return ""
        # Detect prompt echo-back
        from prompts import REPORT_GROUP_TENDENCY_USER
        if detect_prompt_echo(REPORT_GROUP_TENDENCY_USER, result):
            logger.warning("group_tendency: detected prompt echo, triggering fallback")
            return ""
        return result
```

- [ ] **Step 4: Add echo detection to `generate_report_conclusion`**

In `backend/llm.py`, inside `generate_report_conclusion` (around line 755), replace the existing return block:

From:
```python
        result = _strip_thinking(raw).strip()
        if not result:
            logger.warning("conclusion: empty after stripping thinking tags")
            return ""
        return result
```

To:
```python
        result = _strip_thinking(raw).strip()
        if not result:
            logger.warning("conclusion: empty after stripping thinking tags")
            return ""
        # Detect prompt echo-back using ONLY the static instruction portion,
        # NOT the dynamic group_tendency (which the model legitimately reuses)
        from prompts import REPORT_CONCLUSION_INSTRUCTION
        if detect_prompt_echo(REPORT_CONCLUSION_INSTRUCTION, result):
            logger.warning("conclusion: detected prompt echo, triggering fallback")
            return ""
        return result
```

**Important:** This uses `REPORT_CONCLUSION_INSTRUCTION` (the static instruction text only), NOT `user_content` (which includes the dynamic `group_tendency`). Comparing against `user_content` would false-positive when the model legitimately references the tendency text in its conclusion.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_report_prompt_echo.py tests/test_echo_detection.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run existing report tests to check for regressions**

Run: `cd backend && python -m pytest tests/test_report_llm.py tests/test_report_endpoint.py tests/test_report_parsing_module.py -v`
Expected: All existing tests still PASS

- [ ] **Step 7: Commit**

```bash
git add backend/llm.py backend/tests/test_report_prompt_echo.py
git commit -m "feat: wire echo detection into report LLM calls, fallback on echo"
```

---

### Task 3: Add sampling parameters to prevent echo

Add `repetition_penalty`, `frequency_penalty`, and lower temperature for report calls where thinking is disabled. Note: `repetition_penalty` is NOT applied to `top_picks` because it can hurt exact UUID copying and JSON schema fidelity in structured output.

**Files:**
- Modify: `backend/config.py:14-23`
- Modify: `backend/llm.py:694-704` (group_tendency), `backend/llm.py:735-745` (conclusion), `backend/llm.py:790-803` (top_picks)

- [ ] **Step 1: Add config settings**

In `backend/config.py`, add after line 22 (`report_max_tokens`):

```python
    report_temperature: float = 0.1
    report_repetition_penalty: float = 1.15
    report_frequency_penalty: float = 0.3
```

- [ ] **Step 2: Update `generate_report_group_tendency` sampling params**

In `backend/llm.py`, modify the `generate_report_group_tendency` function. Change:

```python
    extra_body: dict = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": shared_system},
                {"role": "user", "content": REPORT_GROUP_TENDENCY_USER},
            ],
            temperature=0.3,
            max_tokens=2048,
            extra_body=extra_body,
        )
```

To:

```python
    extra_body: dict = {
        "chat_template_kwargs": {"enable_thinking": False},
        "repetition_penalty": settings.report_repetition_penalty,
    }
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": shared_system},
                {"role": "user", "content": REPORT_GROUP_TENDENCY_USER},
            ],
            temperature=settings.report_temperature,
            frequency_penalty=settings.report_frequency_penalty,
            max_tokens=2048,
            extra_body=extra_body,
        )
```

- [ ] **Step 3: Update `generate_report_conclusion` sampling params**

Same change pattern as step 2 for the conclusion function. Change:

```python
    extra_body: dict = {"chat_template_kwargs": {"enable_thinking": False}}
    ...
            temperature=0.3,
```

To:

```python
    extra_body: dict = {
        "chat_template_kwargs": {"enable_thinking": False},
        "repetition_penalty": settings.report_repetition_penalty,
    }
    ...
            temperature=settings.report_temperature,
            frequency_penalty=settings.report_frequency_penalty,
```

- [ ] **Step 4: Update `generate_report_top_picks` — temperature only**

In `backend/llm.py`, modify `generate_report_top_picks` (around line 790). Change only temperature:

```python
            temperature=0.3,
```

To:

```python
            temperature=settings.report_temperature,
```

Do NOT add `repetition_penalty` or `frequency_penalty` to `top_picks` — it can degrade exact UUID/name copying and JSON schema fidelity in structured output.

- [ ] **Step 5: Run all report tests**

Run: `cd backend && python -m pytest tests/test_report_llm.py tests/test_report_endpoint.py tests/test_report_parsing_module.py tests/test_echo_detection.py tests/test_report_prompt_echo.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/config.py backend/llm.py
git commit -m "feat: add repetition_penalty, frequency_penalty, and lower temperature for report calls"
```

---

### Task 4: Clear cached report for the affected run

The buggy report is cached in `survey_runs.report_json`. Clear it so regeneration uses the new code.

**Files:**
- No code changes — database operation only

- [ ] **Step 1: Clear the cached report**

```bash
cd /gen-ai/finance/nemotron-finance-demo
python3 -c "
import sqlite3
db = sqlite3.connect('data/history.db')
db.execute('UPDATE survey_runs SET report_json = NULL WHERE id = ?', ['270c4830-a2f1-4ea8-9b9b-15470ec609fb'])
db.commit()
print('Cleared cached report for run 270c4830')
db.close()
"
```

- [ ] **Step 2: Verify the cache was cleared**

```bash
python3 -c "
import sqlite3
db = sqlite3.connect('data/history.db')
row = db.execute('SELECT report_json FROM survey_runs WHERE id = ?', ['270c4830-a2f1-4ea8-9b9b-15470ec609fb']).fetchone()
print('report_json is None:', row[0] is None)
db.close()
"
```

Expected: `report_json is None: True`

---

### Task 5: Final verification

- [ ] **Step 1: Run the full test suite**

```bash
cd /gen-ai/finance/nemotron-finance-demo/backend
python -m pytest tests/ -v
```

Expected: All tests PASS, no regressions

- [ ] **Step 2: Manual smoke test (if vLLM server is running)**

Navigate to the app, go to Tab 4 for run `270c4830`, verify:
- Report regenerates (not from cache)
- `group_tendency` contains synthesized analysis, not parroted answers
- `conclusion` does not contain prompt text
- `recommended_actions` are actual action items, not prompt fragments

---

## Summary of Changes

| Layer | What | Why |
|-------|------|-----|
| **Detection** | `detect_prompt_echo()` in `llm.py` | Catches echo when prevention fails |
| **Fallback** | Return `""` on echo → existing fallback kicks in | Graceful degradation |
| **Prevention** | `repetition_penalty=1.15`, `frequency_penalty=0.3`, `temperature=0.1` | Reduces degenerate sampling |
| **Constant** | `REPORT_CONCLUSION_INSTRUCTION` in `prompts.py` | Safe echo detection scope (excludes dynamic `group_tendency`) |

## Out of Scope (Tracked Separately)

| Issue | Description | Recommended Fix |
|-------|-------------|-----------------|
| **Parser `enable_thinking` ignored** | vLLM constructs parser as `self.reasoning_parser(tokenizer)` without per-request kwargs. The `enable_thinking` branch in `__init__` always defaults to `True`. | Rewrite parser to infer mode from `request` in `extract_reasoning()` or from text shape (always handle `<think>` gracefully). Do NOT branch in `__init__`. |
