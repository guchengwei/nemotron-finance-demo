"""Normalize follow-up chat history before reuse."""

from collections.abc import Sequence

from followup_sanitizer import sanitize_followup_message_content


def normalize_followup_history(
    rows: Sequence[object],
) -> tuple[list[dict[str, str]], list[str]]:
    """Return replay-safe history plus user questions for dedupe.

    Replay history only includes complete user/assistant pairs. User questions
    are still tracked for dedupe even if they are later dropped from replay
    because they never received a usable assistant answer.
    """

    replay_history: list[dict[str, str]] = []
    asked_questions: list[str] = []
    asked_seen: set[str] = set()
    pending_user: str | None = None

    for row in rows:
        role = str(row["role"]) if row is not None else ""
        content = sanitize_followup_message_content(role, str(row["content"] or ""))
        if not content:
            continue

        if role == "user":
            content = content.strip()
            if not content:
                continue
            if content not in asked_seen:
                asked_seen.add(content)
                asked_questions.append(content)
            pending_user = content
            continue

        if role != "assistant" or pending_user is None:
            continue

        replay_history.append({"role": "user", "content": pending_user})
        replay_history.append({"role": "assistant", "content": content})
        pending_user = None

    return replay_history, asked_questions
