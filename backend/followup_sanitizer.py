"""Sanitize follow-up chat text before display, reuse, or persistence."""

import re

from llm import sanitize_answer_text

_ASSISTANT_ROLE_PREFIX_RE = re.compile(
    r"(?is)^assistant(?:\s*[:：]\s*|\s*\r?\n\s*|$)"
)

_LEADING_SCORE_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:【評価\s*[:：]\s*\d+\s*】|【評価】\s*\d+)\s*"
)

_LEADING_MEMORY_LABEL_RE = re.compile(r"(?is)^\s*回答要旨】\s*")

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

_JAPANESE_RULE_ECHO_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:"
    r"【評価】で始まる評価を付与してください|"
    r"【評価】から始めて回答してください|"
    r"から始めて回答してください|"
    r"過去アンケート回答と矛盾しないようにしてください|"
    r"回答はこの人物の立場から自然に導かれるものである必要があります|"
    r"過去アンケート回答は参考情報です|"
    r"【アンケートテーマ】|"
    r"【過去アンケート回答】|"
    r"【アンケートに関する重要なルール】|"
    r"【重要な注意】"
    r")"
)

_JAPANESE_RULE_ECHO_PHRASES = (
    "から始めて回答してください",
    "過去アンケート回答と矛盾しないようにしてください",
    "回答はこの人物の立場から自然に導かれるものである必要があります",
    "専門用語は適切に使ってください",
    "敬語を必ず使用してください",
    "過去アンケート回答は参考情報です",
    "回答の冒頭に必ず【評価:X】",
    "アンケートに関する重要なルール",
)

_FOLLOWUP_INSTRUCTION_ECHO_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:"
    r"現在の質問にだけ答えてください|"
    r"先の回答内容を再利用するのではなく|"
    r"新しい質問への応答として|"
    r"この人物の立場から自然に返答してください|"
    r"ユーザーの追加質問に一貫性を持って応答してください"
    r")"
)

_FOLLOWUP_TRAILING_INSTRUCTION_RE = re.compile(
    r"(?is)\s*(?:過去アンケート回答を参考にし、?\s*)?"
    r"ユーザーの追加質問に一貫性を持って応答してください。?\s*$"
)

_JAPANESE_CHAR_RE = re.compile(r"[ぁ-んァ-ヶ一-龠々ー]")
_LATIN_CHAR_RE = re.compile(r"[A-Za-z]")
_TOKEN_SOUP_FRAGMENT_RE = re.compile(
    r"(?i)(?:tasksinmoneygin|#include|console|function|comments|import|from|while|models|account-free)"
)

_QUESTION_ECHO_SKIP_CHARS = set(
    " \t\r\n\u3000"
    "「」『』“”‘’'\"`"
    "（）()【】[]<>〈〉《》"
    "、。，．.!！?？:：;；-ー～〜…"
)


def _strip_leading_assistant_label(text: str) -> str:
    stripped = text.lstrip()
    match = _ASSISTANT_ROLE_PREFIX_RE.match(stripped)
    if not match:
        return text
    return stripped[match.end():].lstrip()


def _strip_followup_format_noise(text: str) -> str:
    cleaned = text
    while True:
        updated = _LEADING_SCORE_PREFIX_RE.sub("", cleaned, count=1)
        updated = _LEADING_MEMORY_LABEL_RE.sub("", updated, count=1)
        if updated == cleaned:
            return cleaned
        cleaned = updated.lstrip()


def _looks_like_token_soup(text: str) -> bool:
    sample = text.strip()[:160]
    if not sample:
        return False
    japanese_chars = len(_JAPANESE_CHAR_RE.findall(sample))
    latin_chars = len(_LATIN_CHAR_RE.findall(sample))
    symbol_chars = len(re.findall(r"[^0-9A-Za-zぁ-んァ-ヶ一-龠々ー\s]", sample))
    fragment_hits = len(_TOKEN_SOUP_FRAGMENT_RE.findall(sample))
    if sample.startswith("【") and japanese_chars <= 2 and latin_chars >= 10 and fragment_hits >= 1:
        return True
    if japanese_chars <= 3 and latin_chars >= 18 and symbol_chars >= 6 and fragment_hits >= 1:
        return True
    return japanese_chars <= 2 and latin_chars >= 20 and symbol_chars >= 8 and fragment_hits >= 2


def _is_question_echo_skip_char(char: str) -> bool:
    return char.isspace() or char in _QUESTION_ECHO_SKIP_CHARS


def match_followup_question_echo_prefix(text: str, question: str) -> tuple[str, int]:
    """Return whether text begins with a normalized copy of the user question.

    Status values:
    - "none": no question echo match at the start
    - "partial": text is still only a prefix of the question
    - "full": text contains the whole echoed question; index points after the prefix
    """
    candidate = text or ""
    prompt = question or ""
    i = 0
    j = 0
    matched = False

    while True:
        while i < len(candidate) and _is_question_echo_skip_char(candidate[i]):
            i += 1
        while j < len(prompt) and _is_question_echo_skip_char(prompt[j]):
            j += 1

        if j >= len(prompt):
            while i < len(candidate) and _is_question_echo_skip_char(candidate[i]):
                i += 1
            return ("full", i) if matched else ("none", 0)
        if i >= len(candidate):
            return ("partial", i) if matched else ("none", 0)
        if candidate[i].casefold() != prompt[j].casefold():
            return ("none", 0)

        matched = True
        i += 1
        j += 1


def strip_followup_question_echo_prefix(text: str, question: str) -> str:
    status, end_index = match_followup_question_echo_prefix(text, question)
    if status != "full":
        return text
    return (text or "")[end_index:].lstrip()


def sanitize_followup_message_content(role: str, text: str) -> str:
    """Remove leaked markup and discard non-user-facing assistant meta-reasoning."""
    cleaned = sanitize_answer_text(text or "")
    if role != "assistant":
        return cleaned

    cleaned = _strip_leading_assistant_label(cleaned)
    if _JAPANESE_RULE_ECHO_PREFIX_RE.match(cleaned):
        return ""
    if sum(phrase in cleaned for phrase in _JAPANESE_RULE_ECHO_PHRASES) >= 2:
        return ""
    cleaned = _strip_followup_format_noise(cleaned)
    cleaned = _FOLLOWUP_TRAILING_INSTRUCTION_RE.sub("", cleaned).strip()
    if _FOLLOWUP_INSTRUCTION_ECHO_PREFIX_RE.match(cleaned):
        return ""
    if _ENGLISH_META_PREFIX_RE.match(cleaned):
        return ""
    if _looks_like_token_soup(cleaned):
        return ""
    return cleaned


def normalize_followup_user_question(text: str) -> str:
    """Normalize persisted user question text for replay and dedupe comparisons."""
    fallback = str(text or "").strip()
    cleaned = sanitize_answer_text(text or "")
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[\r\n\t\u3000]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    wrappers = (("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"), ("`", "`"))
    for left, right in wrappers:
        if len(cleaned) >= 2 and cleaned.startswith(left) and cleaned.endswith(right):
            inner = cleaned[1:-1].strip()
            if inner:
                cleaned = inner
            break

    return cleaned or fallback
