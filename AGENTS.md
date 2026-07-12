# Repository agent instructions

## Shell commands

Agents must prefix every external shell command they execute with `rtk`.
Human-facing command examples may omit the wrapper; when an agent executes an
example, it inserts `rtk` before each external command. Shell syntax and
built-ins such as `cd` are not external commands and do not take the prefix.

## Pull request review feedback

When asked to address pull request review feedback and push, treat the task as
an end-to-end review-feedback workflow:

- Re-read the pull request head and thread state immediately before writing to
  GitHub.
- After the fix is pushed and verification passes, reply to each objectively
  addressed thread with the fixing commit and relevant test evidence, then
  resolve the thread.
- If feedback is superseded or outdated, explain why before resolving it.
- Leave ambiguous, disputed, security-sensitive, or product-judgment threads
  unresolved and request reviewer direction.
- If feedback is out of scope, create and link a follow-up issue only when that
  issue-tracker write is authorized.

This workflow does not authorize the agent to approve its own pull request,
dismiss reviews, merge, or override branch protections.
