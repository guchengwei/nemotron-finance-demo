# Durable, resumable Survey Runs

- **Status:** Baseline implemented; follow-ups open
- **Baseline date:** 2026-07-12
- **Related:** [Issue #18](https://github.com/guchengwei/nemotron-finance-demo/issues/18), [PR #26](https://github.com/guchengwei/nemotron-finance-demo/pull/26)

Refined through `/grill-with-docs` on 2026-07-10, this specification is the
authoritative target contract for durable, resumable Survey Runs. The merged
baseline does not yet satisfy every requirement below.
Read the [domain language](../../CONTEXT.md) and
[ADR 0001](../adr/0001-durable-survey-run-lifecycle.md) first.

The contract includes answer sanitization, sentinel-driven fan-in,
question/persona error semantics, immutable `run_personas` snapshots, and the
history-connection hardening needed for transactional events. Incremental
thinking presentation remains a separate improvement.

## Baseline residual checklist

These open issues identify the known requirements still needing implementation
or explicit verification after the merged baseline:

- [#19 — Answer boundary sanitization](https://github.com/guchengwei/nemotron-finance-demo/issues/19)
- [#20 — Durable observer gap recovery](https://github.com/guchengwei/nemotron-finance-demo/issues/20)
- [#21 — Idempotency key ordering](https://github.com/guchengwei/nemotron-finance-demo/issues/21)
- [#22 — Exclude failed Answer Outcomes from follow-up](https://github.com/guchengwei/nemotron-finance-demo/issues/22)
- [#23 — Surface `not_completed_reason` in UI and history](https://github.com/guchengwei/nemotron-finance-demo/issues/23)
- [#24 — Confirm cancel-then-delete behavior](https://github.com/guchengwei/nemotron-finance-demo/issues/24)
- [#25 — Verify and document shutdown and database ownership](https://github.com/guchengwei/nemotron-finance-demo/issues/25)

## 1. Required invariants

1. A Survey Run exists as soon as a valid start request is accepted. Question
   generation is background work owned by that run.
2. A Run Observer may disconnect, reload, or coexist with other observers
   without changing execution.
3. Persisted Run Events are gaplessly sequenced per run, retained for the
   lifetime of the run, and delivered in order with at-least-once semantics.
4. Live Deltas are unsequenced, unpersisted, and best-effort. Losing them cannot
   change an Answer Outcome.
5. Related canonical state and the Run Event announcing it commit atomically.
   Nothing is broadcast before commit.
6. Exactly one terminal Run Event exists and has the highest sequence number:
   `survey_complete`, `survey_error`, or `survey_cancelled`.
7. Survey Run outcomes are `running`, `completed`, `failed`, and `cancelled`.
   Connection state is not a run outcome.
8. Each requested persona has a terminal Persona Outcome: `completed`,
   `failed`, or `not_completed`. Every terminal summary satisfies
   `completed + failed + not_completed == total`.
9. An Answer Outcome is `answered` or `failed`. Failed questions contain safe
   error metadata and never fabricated answer text.
10. One backend process owns a given history database. Multiple observers are
    supported; multiple app processes are not.

## 2. HTTP contract

### `POST /api/survey/run`

This endpoint returns JSON and never streams.

The frontend creates an `Idempotency-Key` before sending the request and keeps
it in `sessionStorage` until it has stored the returned `run_id`. The server
persists the key and a canonical request fingerprint.

Validate before a Survey Run exists:

- `survey_theme` is nonblank after trimming.
- `persona_ids` contains 1–200 unique IDs.
- Every persona exists and can be captured as a Persona Snapshot.
- Omitted or `null` `questions` means generate them in the background.
- An explicit empty question list is invalid.
- Supplied questions are nonblank after trimming and within configured count
  and length limits.

Unknown or duplicate personas and malformed inputs return `422` without
creating a run or event.

For a new valid key, one transaction:

1. inserts `survey_runs` with `status='running'` and `questions_json='[]'` when
   questions must be generated;
2. inserts ordered Persona Snapshots into `run_personas`;
3. appends `run_created` as sequence 1; and
4. commits before background execution starts.

The server then creates a strongly referenced background task and returns
`202 Accepted` with `{ "run_id": "...", "status": "running" }`.

Retrying the same key and identical request returns the original run ID without
starting duplicate work. Reusing a key with a different fingerprint returns
`409 Conflict`. If a committed run lacks a live handle because the first
request failed between commit and task creation, an identical retry may restore
execution from its persisted configuration before returning.

### `GET /api/survey/stream/{run_id}`

The endpoint accepts a cursor from `Last-Event-ID`; `?last_event_id=` exists for
tests and explicit clients. A fresh Run Observer starts at zero after loading
the run detail and Persona Snapshots.

The server subscribes before replay, queries all Run Events with `seq > cursor`,
then tails live notifications. Queued persisted events at or below the replay
high-water mark are discarded. A 15-second SSE comment heartbeat keeps idle
connections alive.

Persisted frames use:

```text
id: <seq>
event: <event_type>
data: <json>

```

Live Deltas have no `id:` line. The stream closes after a terminal Run Event.
If a legacy terminal run has no event log, return a structured
`replay_unavailable` response rather than inventing events.

### `POST /api/survey/{run_id}/cancel`

- Unknown run: `404`.
- Active run or cancellation already pending: idempotently request
  cancellation and return `202`.
- Already cancelled: return the cancelled outcome successfully.
- Already completed or failed: `409` with the existing outcome.

The first accepted cancellation reserves the terminal outcome, cancels
outstanding work, retains committed results, atomically appends
`survey_cancelled` with `status='cancelled'`, and closes observers after that
event is delivered.

### History, deletion, and reports

`GET /api/history/{run_id}` returns Persona Snapshots, Answer Outcomes, run
outcome, and whether replay is available. Selecting a running history item
attaches automatically.

`DELETE /api/history/{run_id}` returns `409` for an active run. Only terminal
runs can be deleted. Deletion removes the run, snapshots, answers, events,
chats, and reports in one transaction. The UI may expose one confirmed Delete
action that calls cancel, waits for `survey_cancelled`, and then calls delete;
the backend operations remain distinct.

Standard report generation is allowed only for `completed` runs. Other
outcomes return `409`. Reports exclude failed Answer Outcomes and disclose
failed-answer and failed-persona counts.

The old streaming `POST /api/survey/run` behavior is removed without a legacy
execution endpoint. Frontend and backend deploy together. Health/capabilities
should expose support for resumable runs for deployment diagnostics.

## 3. Event contract

Persist these Run Events:

- `run_created`
- `questions_generated`
- `persona_start`
- `persona_answer`
- `persona_complete`
- `persona_error`
- `survey_complete`
- `survey_error`
- `survey_cancelled`

`persona_answer_chunk` remains a Live Delta. Incremental thinking may add
`persona_thinking_chunk` as another Live Delta. Completed thinking belongs in
the authoritative `persona_answer` payload; no thinking delta is persisted.

`persona_error` requires `scope: "question" | "persona"`:

- Question scope records a failed Answer Outcome and allows the persona to
  continue. It never increments the persona-failure count.
- Persona scope is emitted exactly once when that persona cannot continue and
  establishes a failed Persona Outcome.

Every public error payload contains only:

- a stable `code`;
- a safe Japanese `message`;
- `scope` where applicable;
- `retryable`;
- a correlation ID; and
- identifiers needed to locate the run, persona, or question.

Raw exception text is logged server-side with the correlation ID and is never
persisted or streamed. Initial codes include `llm_unreachable`,
`generation_timeout`, `server_restart`, `server_shutdown`, `run_cancelled`,
`replay_unavailable`, and `internal_error`.

Terminal payloads contain `run_id`, `total`, `completed`, `failed`, and
`not_completed`. For `survey_complete`, `not_completed` is zero. For failed or
cancelled runs, personas without their own terminal event derive
`not_completed_reason: run_failed | run_cancelled`.

## 4. Schema and database access

Add nullable upgrade-safe columns to `survey_runs`:

```sql
idempotency_key    TEXT UNIQUE,
request_fingerprint TEXT
```

Statuses remain stored in `survey_runs.status`, now including `cancelled`.

Add Persona Snapshots:

```sql
CREATE TABLE IF NOT EXISTS run_personas (
    run_id             TEXT NOT NULL REFERENCES survey_runs(id) ON DELETE CASCADE,
    persona_uuid       TEXT NOT NULL,
    position           INTEGER NOT NULL,
    persona_summary    TEXT NOT NULL,
    persona_full_json  TEXT NOT NULL,
    PRIMARY KEY (run_id, persona_uuid),
    UNIQUE (run_id, position)
);
```

Extend `survey_answers` additively:

```sql
outcome         TEXT NOT NULL DEFAULT 'answered',
error_code      TEXT,
error_message   TEXT,
correlation_id  TEXT
```

`answer` is absent/null for a failed Answer Outcome. Existing answer rows
default to `answered`. Keep `persona_full_json` on answers temporarily for
legacy reads; later persona-normalization work may remove the duplication.

Add the event log:

```sql
CREATE TABLE IF NOT EXISTS run_events (
    run_id      TEXT NOT NULL REFERENCES survey_runs(id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL,
    event_type  TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_run_events_run
ON run_events(run_id, seq);
```

Run Events have no time-based sweep. They are deleted with the owning Survey
Run or explicit history wipe.

Create one history-database connection factory and route survey, history,
report, follow-up, and run-manager access through it. Every connection enables
foreign keys, WAL mode, and a defined busy timeout. Do not use scattered raw
`aiosqlite.connect(settings.history_db_path)` calls in these paths.

## 5. Transaction boundaries

At minimum, commit these pairs/groups atomically under a per-run event lock:

- run row + Persona Snapshots + `run_created`;
- generated `questions_json` + `questions_generated`;
- answered row + `persona_answer`;
- failed-answer row + question-scoped `persona_error`;
- final run status + terminal Run Event.

Sequence allocation occurs inside the same serialized append boundary. Fan-out
starts only after commit. If persistence fails, no uncommitted event is shown;
the runner attempts a safe run-level failure and logs full diagnostics.

## 6. Run manager and process lifecycle

Create `backend/run_manager.py` with process-local `RunHandle` objects held in a
strong registry. A handle owns:

- the background task;
- current persisted sequence;
- a terminal/cancellation guard;
- bounded per-observer queues and dirty/gap state;
- a completion event; and
- bounded cleanup metadata for reaping finished handles after a grace period.

The runner uses a bounded fan-in queue and sentinel/persona-terminal counting;
there is no polling with `get_nowait()` and `sleep(0.05)`. A slow observer never
blocks Survey Run execution. If its queue cannot receive a persisted
notification, mark it dirty and refill its cursor from the database. Dropping
Live Deltas is allowed.

Acquire an exclusive advisory lock associated with the configured history DB
during application startup. Refuse to start a second backend process with a
clear error. Redis or other multi-process coordination is out of scope.

Before accepting traffic, reconcile every orphaned `running` row without a live
handle: append one `survey_error` with code `server_restart` and mark the run
failed in the same transaction. Remove the current blind status-only update.
Graceful shutdown similarly fails active runs with `server_shutdown` when the
database remains available. Cross-restart continuation is out of scope.

## 7. Frontend behavior

Replace `startSurveySSE` with:

- a plain start request using a session-stored idempotency key; and
- native `EventSource` for the GET stream.

For a fresh observer or page reload:

1. verify the stored or selected run ID;
2. load history detail and Persona Snapshots;
3. initialize persona state;
4. replay from sequence zero; and
5. remain attached for live progress when the run is active.

For automatic EventSource reconnect, let the browser send `Last-Event-ID`.
Track the highest applied persisted sequence in the client and ignore any event
at or below it. Reducers must be idempotent.

Expose connection state as `live | reconnecting | disconnected`, visibly but
separately from Survey Run outcome. Closing or navigating away only closes the
observer. The explicit Cancel control calls the cancellation endpoint and
keeps the stream open until `survey_cancelled`.

Question-scoped errors render an inline failed-answer slot without changing the
persona card to failed. On run failure or cancellation, remaining personas
render neutrally as not completed. The authoritative `persona_answer` replaces
buffered partial content. Keep the existing 100 ms Live Delta flush batching.

Native EventSource cannot attach bearer headers. Browser observer
authentication should use a secure same-origin HTTP-only session cookie;
bearer tokens remain available for CLI/server clients. Never put tokens in
stream URLs.

## 8. Upgrade behavior

Do not wipe a version-1 local history database and do not fabricate missing Run
Events.

- Existing runs, answers, reports, and chats remain viewable.
- Existing answer rows default to `answered`.
- Do not backfill old event sequences or Persona Snapshots.
- Old terminal runs are explicitly non-replayable.
- Old `running` rows receive only the truthful startup `server_restart`
  terminal event and become failed.
- The complete resumable contract applies only to runs created by the durable
  implementation.

No database file is tracked by the public repository; runtime history remains
under ignored `data/` paths.

## 9. Required tests

Backend tests must cover:

- validation creates no row for invalid requests;
- identical idempotent retries return one run; mismatched reuse returns `409`;
- immediate durable creation followed by background question generation;
- gapless persisted sequences and exactly one max-sequence terminal event;
- atomic answer/event and status/terminal writes under injected failures;
- replay from a mid-run cursor;
- ordered at-least-once client handling and duplicate suppression;
- two concurrent observers receiving identical persisted sequences;
- disconnecting every observer while execution still completes;
- bounded-queue overflow recovering persisted gaps while allowing delta loss;
- question failures producing failed Answer Outcomes without persona failure;
- `completed + failed + not_completed == total` for every terminal event;
- idempotent cancellation, completion races, and retained partial results;
- active-run deletion conflict and terminal cascade deletion;
- startup reconciliation creating a durable `server_restart` failure;
- legacy histories remaining readable but non-replayable;
- raw exception text never reaching public event data;
- configured SQLite connections tolerating concurrent reads and writes; and
- a second process failing the ownership lock clearly.

Frontend tests must cover:

- start POST followed by EventSource attachment;
- automatic reload/history reattachment from Persona Snapshots;
- connection-state badge transitions;
- duplicate persisted events being ignored;
- authoritative answers replacing partial buffers;
- question failures rendering inline without card failure;
- failed/cancelled runs marking remaining personas not completed;
- explicit cancellation waiting for the terminal event;
- one-click cancel-then-delete orchestration; and
- report generation remaining unavailable for non-completed runs.

Update the real-LLM interruption E2E to prove that closing the observer does not
stop the run and reattachment loses no persisted events.

After the task, both required suites must pass:

```bash
cd backend
pytest -q

cd ../frontend
npm test
```

## 10. Out of scope

- Multi-worker or multi-replica execution and Redis fan-out
- Continuing in-flight model generation across a process restart
- Persisting Live Deltas
- Incremental thinking presentation
- Docker/Compose packaging
- Persona-filter latency work (a separate future task)
- Full removal of legacy persona JSON duplication
- Authentication implementation
