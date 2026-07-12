# Nemotron Finance Survey Simulation

This context describes the language of simulated financial surveys conducted
with synthetic Japanese personas.

## Language

**Survey Run**:
One accepted execution of a survey for a defined theme and set of personas. It
exists from request acceptance until it reaches a terminal outcome and owns the
questions and answers produced during that execution.
_Avoid_: Survey session, SSE session, stream

**Survey Run Outcome**:
The terminal disposition of a Survey Run: completed when every requested
persona is accounted for, failed after a run-level failure, or cancelled by an
explicit cancellation. Persona failures and viewer connection states are not
Survey Run outcomes.
_Avoid_: Interrupted, partial success, connection status

**Persona Snapshot**:
The immutable representation of a persona selected for a Survey Run, captured
when the run is accepted so every observer and later history view uses the same
persona identity and attributes.
_Avoid_: Live persona, persona reference

**Run Event**:
An ordered, durable milestone in a Survey Run that every observer can replay
without gaps. It is retained for the lifetime of its owning Survey Run.
_Avoid_: Token, chunk, Live Delta

**Live Delta**:
A best-effort fragment of an answer or reasoning trace used to visualize
generation in progress. It is not durable; the corresponding Run Event carries
the authoritative completed content.
_Avoid_: Run Event, persisted chunk

**Survey Run Cancellation**:
An explicit request to stop an active Survey Run while preserving results that
were already completed. It is a terminal outcome distinct from failure or loss
of a viewer connection.
_Avoid_: Disconnect, interruption, failure

**Answer Outcome**:
The result of asking one survey question to one persona. It is either answered
with persona-authored content or failed with error information; a failure is
never represented as fabricated answer text.
_Avoid_: Placeholder answer, error answer

**History Deletion**:
The permanent removal of a terminal Survey Run and all of its retained results.
It is distinct from Survey Run Cancellation, which stops active work but keeps
completed results.
_Avoid_: Cancellation, stop run

**Run Observer**:
A browser view attached to a Survey Run for live progress or replay. A Survey
Run may have multiple observers, and an observer disconnecting does not change
the run's lifecycle.
_Avoid_: Run owner, SSE connection, subscriber

**Persona Outcome**:
The terminal disposition of a persona within a Survey Run: completed, failed
independently, or not completed because the run ended first. A question-level
failure does not by itself determine the Persona Outcome.
_Avoid_: Card status, Run Outcome

**Survey Report**:
The client-facing aggregate interpretation of a completed Survey Run. It
excludes missing results and discloses failed Answer Outcomes and Persona
Outcomes rather than presenting partial execution as complete evidence.
_Avoid_: Partial report, diagnostic output
