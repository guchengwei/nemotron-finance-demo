"""Sanitize follow-up chat text before display, reuse, or persistence."""

import re

from llm import sanitize_answer_text

_ASSISTANT_ROLE_PREFIX_RE = re.compile(
    r"(?is)^assistant(?:\s*[:：]\s*|\s*\r?\n\s*|$)"
)

_ENGLISH_META_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:"
    r"okay,\s*let'?s see|"
    r"let'?s see|"
    r"the user is asking|"
    r"first,\s*i need to|"
    r"i need to make sure|"
    r"in the previous answers\b|"
    r"wait,|"
    r"so structure:|"
    r"check character count\b|"
    r"count characters\b"
    r")"
)


def _strip_leading_assistant_label(text: str) -> str:
    stripped = text.lstrip()
    match = _ASSISTANT_ROLE_PREFIX_RE.match(stripped)
    if not match:
        return text
    return stripped[match.end():].lstrip()


def sanitize_followup_message_content(role: str, text: str) -> str:
    """Remove leaked markup and discard non-user-facing assistant meta-reasoning."""
    cleaned = sanitize_answer_text(text or "")
    if role != "assistant":
        return cleaned

    cleaned = _strip_leading_assistant_label(cleaned)
    if _ENGLISH_META_PREFIX_RE.match(cleaned):
        return ""
    return cleaned

