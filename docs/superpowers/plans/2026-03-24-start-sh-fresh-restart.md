# Start.sh Fresh Restart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make rerunning `./start.sh` always start this app from a fresh backend state by stopping an existing repo-owned backend on port `8080` before launching a new one.

**Architecture:** Keep the change local to `start.sh`. Before launching `uvicorn`, detect whether port `8080` is already occupied. If the listener matches this repo's backend launch shape, stop it and wait for the port to clear. If the listener belongs to another process, fail safely instead of killing it. Do not mix this work with the still-open Tab 5 follow-up garbage-output bug.

**Tech Stack:** Bash, `lsof`/`ps`/`kill`, uvicorn, curl

---

## Scope Guard

- This plan only changes backend process lifecycle behavior in `start.sh`.
- This plan does not attempt to fix the Tab 5 follow-up corruption / garbage-generation issue.
- After this plan is implemented, Tab 5 still needs separate debugging against the live backend with a known-fresh restart path.

## File Structure

- Modify: `start.sh`
  - Own repo-owned backend detection, stop/wait logic, and safe startup behavior.
- Create: `backend/tests/test_start_sh_restart.py`
  - Own detector-level regression coverage for identifying the repo-owned backend command line and rejecting unrelated listeners.

## Tasks

### Task 1: Add detector tests before touching startup logic

**Files:**
- Create: `backend/tests/test_start_sh_restart.py`

- [ ] **Step 1: Write the failing detector tests**

Add tests for two cases:
- a command line that matches this repo's backend launch shape is considered repo-owned
- an unrelated process on port `8080` is rejected and must not be killed

Keep the detector logic string-based and side-effect free so the tests can run without starting real processes.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd backend && . venv/bin/activate && pytest -q tests/test_start_sh_restart.py
```

Expected: FAIL because the detector helper does not exist yet.

- [ ] **Step 3: Do not commit the red state**

Keep the failing test local until the minimal `start.sh` support logic is in place.

### Task 2: Teach `start.sh` to replace an existing repo-owned backend

**Files:**
- Modify: `start.sh`

- [ ] **Step 1: Add a repo-owned backend detector**

Implement a small helper in `start.sh` that:
- discovers the PID listening on `8080`
- reads its command line
- treats it as repo-owned only if it matches this repo's `uvicorn main:app --host 0.0.0.0 --port 8080 --env-file "$REPO_DIR/.env"` launch shape

The match should be specific enough to avoid killing unrelated `uvicorn` instances.

- [ ] **Step 2: Add pre-start shutdown logic**

Before launching a new backend:
- if no listener exists on `8080`, continue normally
- if a repo-owned backend is found, send `TERM`, wait for the port to clear, and fail if it does not exit in time
- if another process owns `8080`, print a clear error and exit without killing it

- [ ] **Step 3: Preserve current startup contract**

Keep the existing behavior for:
- venv setup
- dependency install
- readiness polling via `/ready`
- demo-history seeding
- frontend build
- trap-based cleanup of the new child PID

Do not broaden the change into vLLM or frontend lifecycle management.

- [ ] **Step 4: Run the detector tests again**

Run:

```bash
cd backend && . venv/bin/activate && pytest -q tests/test_start_sh_restart.py
```

Expected: PASS

- [ ] **Step 5: Run a script-level smoke test**

Run:

```bash
./start.sh
```

Then, while it is still running in another shell, rerun:

```bash
./start.sh
```

Expected:
- the second run stops the first repo-owned backend
- a fresh backend comes up on `8080`
- the script does not kill unrelated listeners

### Task 3: Final verification and handoff

**Files:**
- No additional production files required

- [ ] **Step 1: Verify the active backend is newly started**

Check the listening PID and start time after rerunning `./start.sh` and confirm they changed from the prior backend process.

- [ ] **Step 2: Verify app readiness**

Confirm these still work after a rerun:
- `http://127.0.0.1:8080/ready`
- `http://localhost:8080`
- demo-history seeding does not regress startup

- [ ] **Step 3: Record follow-up debugging handoff**

After the restart behavior is verified, continue the separate Tab 5 investigation with a fresh backend process and explicitly re-check whether the garbage stream still reproduces.
