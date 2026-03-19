# Report JSON Robustness Fix

  ## Summary
  The current real-LLM report flow in this repo completes without crashing, but the qualitative report content can still be sparse because the model sometimes ignores the
  required JSON schema and returns free-form prose. The right fix is to reduce how much structure the LLM must produce, move more determinism into the backend, and make
  parsing/fallback field-level instead of all-or-nothing.

  This plan is written for a fresh session and assumes the implementer will continue from the current `main` branch state after commit `510c15b` (`Fix survey flows and add
  real-LLM e2e coverage`).

  ## Current State And Context
  - The report endpoint is implemented in `backend/routers/report.py`.
  - The report LLM call lives in `backend/llm.py`, function `generate_report(...)`.
  - The current prompt is `REPORT_SYSTEM_PROMPT` in `backend/prompts.py`.
  - Python already computes the numeric parts reliably:
    - `overall_score`
    - `score_distribution`
    - `demographic_breakdown`
  - The LLM is currently asked to emit those numeric fields anyway, plus qualitative fields. This is unnecessary and increases schema failure risk.
  - During real-LLM Playwright validation, the report flow logged failures like:
    - `Report JSON parse failed: Okay, let's tackle this user request...`
  - A minimal fallback was already added so missing `json_repair` no longer crashes the backend, but current behavior still returns `{}` on parse failure, which leaves
  `group_tendency`, `conclusion`, and `top_picks` sparse.
  - The real-LLM Playwright suite already exists and should be reused:
    - `frontend/playwright.real-llm.config.ts`
    - `frontend/e2e/real-llm/03-survey-happy-path-real-llm.spec.ts`

  ## Goal
  Make report generation robust enough that:
  - the API always returns a structurally complete report
  - the report page always has meaningful qualitative sections
  - real-model prose or malformed JSON no longer causes empty `group_tendency`, empty `conclusion`, or missing `top_picks`
  - `top_picks` always reference real surveyed personas from the run

  ## Implementation Changes

  ### 1. Narrow the LLM contract
  Change the report prompt so the model only produces qualitative fields.

  In `backend/prompts.py`:
  - Replace the current report schema request with a smaller schema:
    - `group_tendency`
    - `conclusion`
    - `top_picks`
  - Remove `overall_score`, `score_distribution`, and `demographic_breakdown` from the requested JSON output.
  - Add an explicit “JSON object only, no explanation, no markdown, no code block” instruction.
  - Add a clear selection constraint for `top_picks`:
    - choose exactly 3 items
    - select only from the provided candidate personas
    - copy `persona_uuid` exactly from the candidate list
  - Include a compact candidate block in the prompt for each eligible persona:
    - `persona_uuid`
    - persona summary
    - score
    - 1-2 short answer excerpts
  - Keep Japanese output requirements.

  Default prompt design:
  - First part: concise task and strict JSON-only output rule.
  - Second part: qualitative goals only.
  - Third part: candidate personas with explicit UUIDs.
  - Fourth part: exact JSON object example with only the qualitative fields.

  ### 2. Split report generation into raw-call, parse, and normalize stages
  Refactor `backend/llm.py` so `generate_report()` is no longer a single fragile parse step.

  Implement three internal helpers:
  - `generate_report_raw(...) -> str`
    - does the OpenAI/vLLM call
    - returns sanitized raw text
  - `parse_report_qualitative(raw_text: str) -> dict`
    - strips `<think>` tags
    - strips code fences
    - extracts the first plausible JSON object from surrounding prose
    - tries `json_repair` if available
    - otherwise falls back to stdlib `json.loads`
    - returns partial parsed data instead of `{}` whenever possible
  - `normalize_report_qualitative(parsed: dict) -> dict`
    - guarantees only the allowed keys survive
    - validates `group_tendency` and `conclusion` are strings
    - validates `top_picks` is a list of dicts
    - drops malformed entries instead of failing the whole report

  Do not return `{}` just because one field is malformed. Parsing must be field-tolerant.

  ### 3. Add deterministic backend fallback generation
  In `backend/routers/report.py`, add backend-generated qualitative fallbacks.

  Implement helpers for:
  - `build_fallback_group_tendency(...)`
  - `build_fallback_conclusion(...)`
  - `build_fallback_top_picks(...)`

  Expected behavior:
  - `group_tendency`
    - derive from average score, score distribution, and broad demographic signals already computed in Python
    - should always produce 1 concise Japanese paragraph
  - `conclusion`
    - derive from overall score plus common positive/negative motifs seen in answers
    - should always produce 1 concise Japanese paragraph with an action-oriented recommendation
  - `top_picks`
    - always produce 3 items when at least 3 personas exist
    - if fewer than 3 personas exist, return as many valid picks as possible without fabricating personas

  Top-pick fallback policy:
  - positive pick:
    - highest scored persona with strongest positive phrasing in the first answer
  - negative pick:
    - lowest scored persona with strongest concern phrasing
  - unique pick:
    - remaining persona with the most distinctive or longest response
  - If lexical heuristics are weak, fall back to score ordering plus answer length.

  Implementation constraint:
  - every fallback `persona_uuid` must come from `answers`
  - every fallback `persona_name` and `persona_summary` must come from stored run data
  - every fallback `highlight_quote` must be a clipped excerpt from a real stored answer, max about 50 chars

  ### 4. Merge qualitative fields field-by-field
  In `backend/routers/report.py`:
  - Keep Python numeric aggregates authoritative.
  - Replace the current one-shot merge with field-level merge:
    - `group_tendency` = valid parsed LLM value or backend fallback
    - `conclusion` = valid parsed LLM value or backend fallback
    - `top_picks` = valid parsed LLM picks after validation, otherwise backend fallback
  - Validate LLM `top_picks` against real run personas:
    - unknown UUIDs are dropped
    - missing required fields are repaired from persona/run data where possible
    - if fewer than 3 valid picks remain, fill the remainder using fallback picks not already selected

  Cache the final merged report in `report_json`, not the raw LLM output.

  ### 5. Improve report input preparation
  The current `_build_answers_summary(...)` is good enough structurally, but the prompt context should make persona selection easier.

  In `backend/routers/report.py`:
  - Add a dedicated helper to build the candidate persona block for `top_picks`.
  - Keep answer excerpts short and high-signal.
  - Prefer first-question score plus one or two strongest answer excerpts over dumping too much text.
  - Avoid asking the model to infer identifiers from long unstructured summaries.

  ### 6. Logging and observability
  Add explicit report-generation logging so future debugging is simpler.

  Recommended warnings:
  - `report raw response was non-json`
  - `report parse partially succeeded`
  - `report fallback used for group_tendency`
  - `report fallback used for conclusion`
  - `report fallback used for top_picks`

  Do not log full answer summaries. Log short response prefixes only.

  ## Public Interfaces
  No frontend API change is required.

  Keep `backend/models.py` `ReportResponse` unchanged:
  - `overall_score`
  - `score_distribution`
  - `group_tendency`
  - `conclusion`
  - `top_picks`
  - `demographic_breakdown`

  The only change is reliability and completeness of existing fields.

  ## Tests

  ### Backend unit tests
  Add parser-focused tests in backend test coverage:
  - clean JSON object parses successfully
  - JSON wrapped in prose parses successfully
  - fenced JSON parses successfully
  - malformed JSON with recoverable structure yields partial fields
  - pure prose yields no parsed qualitative fields but does not throw
  - normalization drops malformed top-pick entries without killing valid ones

  ### Backend report integration tests
  Add tests for the report endpoint:
  - LLM returns prose only:
    - endpoint still returns non-empty `group_tendency`
    - endpoint still returns non-empty `conclusion`
    - endpoint still returns valid `top_picks`
  - LLM returns partial JSON:
    - valid fields are preserved
    - missing fields are filled by backend fallback
  - LLM returns fabricated UUIDs:
    - fabricated picks are rejected/repaired
    - returned `top_picks` use only real run personas
  - Final cached `report_json` equals the merged response body

  Best implementation approach:
  - patch `llm.generate_report_raw` or equivalent raw-call helper rather than patching the entire endpoint stack

  ### Frontend / E2E regression
  Strengthen `frontend/e2e/real-llm/03-survey-happy-path-real-llm.spec.ts`:
  - after report loads, assert:
    - `group_tendency` section is visible and non-empty, or
    - `conclusion` section is visible and non-empty
  - assert at least one top-pick card exists when the run has enough personas
  - do not assert exact text because the real LLM is variable

  Add one deterministic backend-side regression test for the “non-JSON report prose” case so CI does not depend on real model misbehavior.

  ## Acceptance Criteria
  The fix is complete when:
  - report generation no longer produces sparse qualitative sections due only to non-JSON LLM output
  - the backend returns a complete report object even when the model returns prose
  - `top_picks` always reference real personas from the run
  - the report page remains meaningfully populated in real-LLM flows
  - parser/fallback behavior is covered by automated tests

  ## Assumptions
  - We are not trying to make the model perfectly obedient to JSON. We are making the backend robust to imperfect model behavior.
  - Python remains the source of truth for numeric report fields.
  - Qualitative fallback text can be template-driven as long as it is coherent, Japanese, and materially useful.
  - It is acceptable for fallback qualitative content to be less rich than ideal model output; completeness and correctness are the priority.