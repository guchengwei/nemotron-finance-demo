import json
import re
from typing import Any

REPORT_ALLOWED_KEYS = {
    "group_tendency",
    "conclusion_summary",
    "recommended_actions",
    "conclusion",
    "top_picks",
}


def _strip_thinking(text: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"</?think>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _strip_code_fences(text: str) -> str:
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```", "", text)
    return text.strip()


def _extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        return text.strip()

    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        char = text[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1].strip()
    return text[start:].strip()


def _extract_json_array_fragment(text: str, field_name: str) -> str | None:
    marker = f'"{field_name}"'
    idx = text.find(marker)
    if idx == -1:
        return None
    start = text.find("[", idx)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for pos in range(start, len(text)):
        char = text[pos]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return text[start:pos + 1]
    return None


def _extract_string_field(text: str, field_name: str) -> str | None:
    pattern = re.compile(
        rf'"{re.escape(field_name)}"\s*:\s*"((?:\\.|[^"\\])*)"',
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return None
    try:
        return json.loads(f'"{match.group(1)}"')
    except Exception:
        return match.group(1).strip()


def _extract_string_array_field(text: str, field_name: str) -> list[str] | None:
    fragment = _extract_json_array_fragment(text, field_name)
    if not fragment:
        return None
    try:
        parsed = json.loads(fragment)
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
    return cleaned or None


def parse_report_qualitative(raw_text: str) -> dict[str, Any]:
    try:
        import json_repair
    except ImportError:
        json_repair = None

    cleaned = _strip_code_fences(_strip_thinking(raw_text or ""))
    json_candidate = _extract_first_json_object(cleaned)

    candidates = []
    if json_candidate:
        candidates.append(json_candidate)
    if cleaned and cleaned not in candidates:
        candidates.append(cleaned)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json_repair.loads(candidate) if json_repair is not None else json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue

    partial: dict[str, Any] = {}
    for field_name in ("group_tendency", "conclusion_summary", "conclusion"):
        value = _extract_string_field(cleaned, field_name)
        if isinstance(value, str) and value.strip():
            partial[field_name] = value.strip()

    recommended_actions = _extract_string_array_field(cleaned, "recommended_actions")
    if recommended_actions:
        partial["recommended_actions"] = recommended_actions

    top_picks_fragment = _extract_json_array_fragment(cleaned, "top_picks")
    if top_picks_fragment:
        try:
            parsed_picks = (
                json_repair.loads(top_picks_fragment)
                if json_repair is not None
                else json.loads(top_picks_fragment)
            )
            if isinstance(parsed_picks, list):
                partial["top_picks"] = parsed_picks
        except Exception:
            pass

    return partial


def normalize_report_qualitative(parsed: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    if not isinstance(parsed, dict):
        return normalized

    group_tendency = parsed.get("group_tendency")
    if isinstance(group_tendency, str) and group_tendency.strip():
        normalized["group_tendency"] = group_tendency.strip()

    conclusion = parsed.get("conclusion")
    if isinstance(conclusion, str) and conclusion.strip():
        normalized["conclusion"] = conclusion.strip()

    conclusion_summary = parsed.get("conclusion_summary")
    if isinstance(conclusion_summary, str) and conclusion_summary.strip():
        normalized["conclusion_summary"] = conclusion_summary.strip()

    recommended_actions = parsed.get("recommended_actions")
    if isinstance(recommended_actions, list):
        cleaned_actions = [
            str(item).strip()
            for item in recommended_actions
            if isinstance(item, str) and item.strip()
        ]
        if cleaned_actions:
            normalized["recommended_actions"] = cleaned_actions

    top_picks = parsed.get("top_picks")
    if isinstance(top_picks, list):
        cleaned_picks = []
        for item in top_picks:
            if not isinstance(item, dict):
                continue
            clean_item = {
                key: value.strip()
                for key, value in item.items()
                if key in {
                    "persona_uuid",
                    "persona_name",
                    "persona_summary",
                    "highlight_reason",
                    "highlight_quote",
                }
                and isinstance(value, str)
                and value.strip()
            }
            if clean_item:
                cleaned_picks.append(clean_item)
        normalized["top_picks"] = cleaned_picks

    return {key: value for key, value in normalized.items() if key in REPORT_ALLOWED_KEYS}
