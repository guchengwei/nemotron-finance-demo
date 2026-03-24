# Fix Plan: Tab(5) Chat UI Bugs 3, 4, 5

## Context

Tab(5) is the "深掘り" (Deep Dive) chat step rendered by `FollowUpChat.tsx`. Three UI/UX issues need fixing. Plan reviewed by Codex (gpt-5.4) and revised accordingly.

---

## Bug 3: Chatbox taller than one screen height

### Root Cause
- `Layout.tsx:15` — outer shell uses `min-h-screen` but not a strict viewport height constraint
- `Layout.tsx:21` — `<main className="flex-1 overflow-auto">` allows content to grow beyond viewport and scroll
- `Layout.tsx:21` — `<main>` is missing `min-h-0` which is required for flex children to shrink below content size
- `FollowUpChat.tsx:123` — chat container uses `h-full` but since the flex height chain is broken, it doesn't constrain to viewport
- Result: chat extends past screen, user must scroll to find send button

### Fix
**File: `frontend/src/components/Layout.tsx`**
1. Add `min-h-0` to `<main>` so it can shrink within the flex column
2. Read `currentStep` from the Zustand store (already available at `store.ts:49`)
3. Conditionally set overflow on `<main>`:
   - Step 5: `overflow-hidden` — chat owns its own scrolling internally
   - Other steps: `overflow-auto` — they need page-level scrolling

**No changes needed in `FollowUpChat.tsx`** for this bug — `h-full min-h-0` is correct once the parent height chain is fixed.

---

## Bug 4: Auto-scroll during LLM thinking/answering

### Root Cause
- `FollowUpChat.tsx:56-58` — `useEffect` fires `scrollIntoView({ behavior: 'smooth' })` on every `messages` change
- Streaming tokens update the messages array per-chunk (lines 71-78), and thinking updates do the same (lines 96-103)
- This causes constant forced scrolling that hijacks the user's scroll position — they can't scroll up to read earlier messages while LLM is responding

### Fix
**File: `frontend/src/components/FollowUpChat.tsx`**

Replace the unconditional auto-scroll with a **"stick to bottom"** pattern:

1. Add a `messagesContainerRef` to the scrollable `<div>` (line 179)
2. Track whether user is "pinned to bottom" via a `useRef<boolean>` (`stickToBottom`), defaulting to `true`
3. Add an `onScroll` handler on the messages container:
   - Calculate if user is near bottom: `scrollHeight - scrollTop - clientHeight < 100`
   - Update `stickToBottom.current` accordingly
4. In the `useEffect([messages])`, only scroll if `stickToBottom.current === true`
5. Use `behavior: 'auto'` (instant) during streaming instead of `'smooth'` to avoid janky smooth-scroll-per-chunk
6. On new user message send, force `stickToBottom.current = true` (user expects to see the response)

**Important**: Do NOT limit scrolling to only `messages.length` changes — that would break "following" a long streaming response. The key distinction is: scroll on any update IF the user is pinned to bottom; don't scroll if they've scrolled up.

---

## Bug 5: Suggested questions always the same & disappear after conversation starts

### Root Cause
**5a: Always the same questions**
- `FollowUpChat.tsx:6-10` — `SUGGESTED_QUESTIONS` is a hardcoded static array of 3 generic questions
- Not personalized to the selected persona or survey theme

**5b: Disappear once conversation happens**
- `FollowUpChat.tsx:219` — `{messages.length === 0 && (...)}` hides suggestions permanently after first message

### Fix
**File: `frontend/src/components/FollowUpChat.tsx`**

**5a — Derive suggestions from existing survey data:**
- The store already has `questions` (survey questions, `store.ts:59`) and `surveyTheme` (`store.ts:57`)
- `currentHistoryRun` also has `survey_theme` and `questions` (`types.ts:114-115`)
- Create a `getSuggestedQuestions(persona, theme, surveyQuestions)` function that:
  - Uses the actual survey questions from the run as the basis for follow-up suggestions
  - Reframes them as follow-up probes (e.g., survey Q "手数料の許容範囲は？" → follow-up "具体的にどの程度の手数料なら許容できますか？")
  - Falls back to generic questions only if survey data is unavailable

**5b — Keep showing after conversation starts:**
- Remove the `messages.length === 0` guard from the suggested questions block
- Always render suggestions above the input area, between messages and the text input
- When `messages.length > 0`: use reduced visual prominence (smaller, more subtle styling)
- Keep suggestions horizontally scrollable or compact to avoid adding vertical pressure, especially on small screens (below `xl` breakpoint where layout is column-first)

---

## Adjacent Defects to Fix (found during review)

### Stale messages on persona switch
- `FollowUpChat.tsx:48-54` — hydration effect only sets messages when `existing.length > 0`
- If user switches to a persona with no chat history, previous persona's messages remain visible
- **Fix**: Add an `else` branch to reset `messages` to `[]`; also reset `input` and `profileExpanded`

### SSE stream cleanup
- `cancelRef` (line 69) is never cleaned up on unmount or persona switch
- Error path (lines 91-95) leaves the placeholder assistant message in a streaming-looking state
- **Fix**: Add a cleanup return in the hydration `useEffect` that calls `cancelRef.current?.()` and resets `sending`; in the error handler, mark the last message as `streaming: false` with an error indicator

---

## Files to Modify

| File | Changes |
|------|---------|
| `frontend/src/components/Layout.tsx` | Read `currentStep` from store; add `min-h-0` to `<main>`; conditional `overflow-hidden` for step 5 |
| `frontend/src/components/FollowUpChat.tsx` | Stick-to-bottom auto-scroll; dynamic suggestions from survey data; persistent suggestion display; stale message reset; SSE cleanup |

No changes needed in `store.ts` or `App.tsx` — `currentStep` is already in the store.

## Verification

1. **Bug 3**: Navigate to tab 5 — chat input and send button visible without scrolling on any screen size
2. **Bug 4**: Send a message, then scroll up while LLM is responding — scroll position stays put; scroll down to bottom — it resumes following
3. **Bug 5**: Suggested questions reflect the survey theme/questions; they remain visible (subtly) after conversation starts
4. **Stale messages**: Switch between personas in tab 5 — messages update correctly, no stale content
5. **SSE cleanup**: Navigate away from tab 5 mid-stream — no console errors, no orphaned connections
6. Run unit tests: `cd frontend && npx vitest run`
7. Run E2E tests if available in `tests/` directory
