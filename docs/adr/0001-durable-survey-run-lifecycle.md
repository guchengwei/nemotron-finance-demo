# ADR 0001: Survey Runs outlive their observers

- **Status:** Accepted
- **Date:** 2026-07-10
- **Related:** [Issue #18](https://github.com/guchengwei/nemotron-finance-demo/issues/18), [PR #26](https://github.com/guchengwei/nemotron-finance-demo/pull/26)

## Context

The original survey endpoint coupled execution to one streaming HTTP response.
A browser disconnect, reload, or second observer could therefore be confused
with the Survey Run lifecycle, and completed work was not represented by a
durable, replayable event sequence. The application also needs truthful
distinctions between a run-level failure, explicit cancellation, a failed
persona or answer, and loss of an observer connection.

The current deployment is one backend process backed by SQLite. It must support
multiple observers and restart reconciliation without pretending that in-flight
model generation can continue across a process restart.

## Decision

The accepted target is that a Survey Run is created durably before question
generation and executes in a single process independently of any browser
connection. Ordered Run Events and Persona Snapshots are the authoritative
basis for replay to multiple Run Observers, while high-volume Live Deltas
remain best-effort. Related state and events must commit atomically, delivery
is at-least-once, and observers must deduplicate by sequence.

Run completion, failure, and explicit cancellation are distinct terminal
outcomes guarded so exactly one can win. Under the target contract, viewer
disconnects do not affect the run, restart-orphaned runs fail durably during
startup, cancellation preserves partial results, and History Deletion is
allowed only after a run is terminal. The complete target contract is recorded
in the
[resumable Survey Runs specification](../specs/resumable-survey-runs.md).

## Verified baseline and residuals

The merged baseline establishes durable run records, Persona Snapshots, Run
Events, terminal outcomes, cancellation, and observer reattachment. Acceptance
of this decision does not mean every target requirement is complete. The
specification's
[baseline residual checklist](../specs/resumable-survey-runs.md#baseline-residual-checklist)
links the remaining implementation and verification work.

## Expected consequences and tradeoffs

- The target decouples browser reloads, disconnects, and concurrent observers
  from Survey Run execution.
- Persisted, gaplessly sequenced events are intended to provide replay and an
  auditable terminal outcome, at the cost of additional schema, transaction,
  and client deduplication complexity.
- Live Deltas may be dropped under backpressure; authoritative completed answers
  and lifecycle events must remain durable.
- Cancellation is designed to retain committed partial results, while deletion
  remains a separate terminal-only operation.
- Orphaned active runs must be marked failed after restart because
  cross-process continuation is deliberately unsupported.
- The target permits one backend process to own a history database.
  Multi-worker or multi-replica deployment requires a shared coordinator and
  is outside this decision.
