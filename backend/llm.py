"""LLM client with mock mode support.

Mock mode (MOCK_LLM=true) returns template responses with persona details
injected. Adds 0.5-2s random delay to simulate streaming.
"""

import asyncio
import json
import logging
import random
import re
from typing import Any, AsyncGenerator, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from config import settings
import report_parsing

logger = logging.getLogger(__name__)
REPORT_ALLOWED_KEYS = {
    "group_tendency",
    "conclusion_summary",
    "recommended_actions",
    "conclusion",
    "top_picks",
}

# Semaphore for concurrency control
_semaphore: asyncio.Semaphore | None = None


def get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.llm_concurrency)
    return _semaphore


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        base_url=settings.vllm_url,
        api_key="dummy",  # vLLM doesn't require real key
    )


# -- Mock responses -----------------------------------------------------------

MOCK_SURVEY_TEMPLATES = [
    "【評価: {score}】{name}と申します。{occupation}として働いており、このサービスについては{sentiment}関心を持っています。特に{feature}の面が重要だと感じます。",
    "【評価: {score}】{age}歳の{occupation}の立場からすると、{sentiment}思います。{concern}点については慎重に考える必要があります。",
    "【評価: {score}】{prefecture}に住む{occupation}として、このようなサービスは{sentiment}です。{feature}が整備されれば積極的に利用したいと思います。",
]

MOCK_SENTIMENTS_POSITIVE = ["非常に魅力的", "大変興味深い", "期待している"]
MOCK_SENTIMENTS_NEGATIVE = ["やや懸念がある", "慎重に検討したい", "まだ不安が残る"]
MOCK_FEATURES = ["セキュリティ", "手数料の透明性", "使いやすさ", "サポート体制", "投資商品の多様性"]
MOCK_CONCERNS = ["セキュリティ", "情報漏洩", "手数料の高さ", "使い方の複雑さ"]

MOCK_FREETEXT_TEMPLATES = [
    "{name}の立場から申しますと、{feature}が最も重要だと考えます。{occupation}として長年の経験から、{concern}については特に注意が必要です。",
    "このサービスにおいて最も重視するのは{feature}です。{age}歳として、{concern}への対応が整っていれば利用を検討したいと思います。",
    "率直に申し上げると、{feature}の改善が急務だと感じます。{occupation}の視点では、現状{concern}の問題が解決されていない印象があります。",
]

MOCK_QUESTIONS = [
    "このようなサービスに対する全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）",
    "最も重要だと考える機能や特徴は何ですか？",
    "利用にあたって最も懸念される点は何ですか？",
    "料金体系についてどのようにお考えですか？",
]

MOCK_REPORT = {
    "overall_score": 3.4,
    "score_distribution": {"1": 1, "2": 2, "3": 3, "4": 2, "5": 0},
    "group_tendency": "全体として中程度の関心度。40代以上の金融経験者層がより積極的な評価を示す傾向。セキュリティと手数料透明性への懸念が共通テーマとして浮上。",
    "conclusion_summary": "全体としては中程度の関心度で、導入判断には不安解消が必要です。",
    "recommended_actions": [
        "セキュリティ対策を具体的に示す",
        "手数料体系をわかりやすく開示する",
        "初心者向けの利用導線を整える",
    ],
    "conclusion": "サービス導入に向けては、セキュリティ対策の強化と手数料体系の明確化が最優先課題。特に専門家層のニーズに応える高度な機能と、初心者向けの使いやすいインターフェースの両立が求められる。",
    "top_picks": [
        {
            "persona_uuid": "mock-uuid-1",
            "persona_name": "田中 太郎",
            "persona_summary": "45歳男性、銀行員、東京都、金融リテラシー:専門家",
            "highlight_reason": "具体的な改善提案を含む最も詳細な回答",
            "highlight_quote": "手数料体系の透明性が確保されれば積極的に利用したい"
        },
        {
            "persona_uuid": "mock-uuid-2",
            "persona_name": "佐藤 花子",
            "persona_summary": "32歳女性、会社員、大阪府、金融リテラシー:初心者",
            "highlight_reason": "初心者目線での懸念を的確に表現",
            "highlight_quote": "操作が複雑すぎると使いこなせない不安がある"
        },
        {
            "persona_uuid": "mock-uuid-3",
            "persona_name": "山田 健一",
            "persona_summary": "58歳男性、自営業、愛知県、金融リテラシー:中級者",
            "highlight_reason": "独自の視点から業界全体への提言を含む回答",
            "highlight_quote": "既存の銀行との連携強化が普及の鍵になる"
        }
    ],
    "demographic_breakdown": {
        "by_age": {"20-39": 3.1, "40-59": 3.8, "60+": 2.9},
        "by_sex": {"男性": 3.5, "女性": 3.2},
        "by_financial_literacy": {"初心者": 2.8, "中級者": 3.4, "上級者": 3.9, "専門家": 4.1}
    }
}


def _mock_survey_answer(persona: dict, question: str, question_index: int) -> str:
    """Generate a mock survey answer for a persona."""
    name = persona.get("name", "不明")
    age = persona.get("age", 40)
    occupation = persona.get("occupation", "会社員")
    prefecture = persona.get("prefecture", "東京都")

    score = random.randint(2, 5)
    sentiment = random.choice(MOCK_SENTIMENTS_POSITIVE if score >= 3 else MOCK_SENTIMENTS_NEGATIVE)
    feature = random.choice(MOCK_FEATURES)
    concern = random.choice(MOCK_CONCERNS)

    if question_index == 0:
        template = random.choice(MOCK_SURVEY_TEMPLATES)
        return template.format(
            score=score, name=name, age=age, occupation=occupation,
            prefecture=prefecture, sentiment=sentiment, feature=feature, concern=concern
        )
    else:
        template = random.choice(MOCK_FREETEXT_TEMPLATES)
        return template.format(
            name=name, age=age, occupation=occupation,
            feature=feature, concern=concern
        )


async def _mock_stream_answer(text: str) -> AsyncGenerator[str, None]:
    """Stream a mock answer character by character with delay."""
    delay = random.uniform(0.5, 2.0) / len(text) if text else 0.01
    delay = min(delay, 0.05)  # cap at 50ms per char
    for char in text:
        yield char
        await asyncio.sleep(delay)


# -- Real LLM calls -----------------------------------------------------------

def _strip_thinking(text: str) -> str:
    """Strip <think>...</think> blocks from non-streaming responses."""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'</?think>', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _strip_thinking_stream_chunk(text: str) -> str:
    """Remove leaked think markup from a streamed answer chunk without trimming spacing."""
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'</?think>', '', cleaned, flags=re.IGNORECASE)
    return cleaned


def sanitize_answer_text(text: str) -> str:
    """Remove leaked reasoning markup from model-visible answer text."""
    cleaned = _strip_thinking(text)
    # Aggressively strip any residual think tag fragments
    cleaned = re.sub(r'</?think[^>]*>', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def detect_prompt_echo(prompt: str, response: str, min_chunk: int = 20) -> bool:
    """Detect if a response contains significant substring overlap with the prompt.

    Uses sliding-window check: if any contiguous chunk of the prompt
    (>= min_chunk characters) appears in the response, it's an echo.
    """
    if not prompt or not response or len(prompt) < min_chunk:
        return False
    for i in range(len(prompt) - min_chunk + 1):
        chunk = prompt[i : i + min_chunk]
        if chunk in response:
            return True
    return False


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


def _normalize_followup_question(text: str) -> str:
    return text.strip()


async def _stream_split_thinking(
    source: AsyncGenerator[str, None],
) -> AsyncGenerator[tuple[str, str], None]:
    """Split stream into ('think', full_thinking) and ('answer', chunk) tuples.

    Buffers the entire <think>...</think> block, then emits it as a single
    ('think', text) item. Answer tokens are yielded one chunk at a time as
    ('answer', chunk) so the UI can stream them live.
    """
    buf = ""
    in_think = False
    think_buf = ""

    async for delta in source:
        buf += delta
        while True:
            if not in_think:
                if buf.startswith('</think>'):
                    buf = buf[len('</think>'):]
                    continue
                start = buf.find('<think>')
                if start == -1:
                    if buf:
                        answer_chunk = re.sub(r'</think>', '', buf, flags=re.IGNORECASE)
                        if answer_chunk:
                            yield ('answer', answer_chunk)
                        buf = ""
                    break
                # flush answer content before <think> (rare but handle it)
                if start > 0:
                    answer_chunk = re.sub(r'</think>', '', buf[:start], flags=re.IGNORECASE)
                    if answer_chunk:
                        yield ('answer', answer_chunk)
                buf = buf[start + len('<think>'):]
                in_think = True
                think_buf = ""
            else:
                end = buf.find('</think>')
                if end == -1:
                    think_buf += buf
                    buf = ""
                    break
                think_buf += buf[:end]
                yield ('think', think_buf)
                buf = buf[end + len('</think>'):]
                in_think = False
    # Stream ended inside an unclosed <think> block — emit what we have
    if in_think and (think_buf or buf):
        yield ('think', think_buf + buf)
    elif buf:
        answer_chunk = re.sub(r'</think>', '', buf, flags=re.IGNORECASE)
        if answer_chunk:
            yield ('answer', answer_chunk)


async def _stream_split_reasoning(
    raw,  # vLLM streaming response (AsyncIterable of chunks)
) -> AsyncGenerator[tuple[str, str], None]:
    """Split vLLM streaming response using reasoning / reasoning_content fields.

    With --reasoning-parser active, delta.reasoning holds thinking and
    delta.content holds the clean answer. Both can appear in the same chunk
    (transition chunk), so both fields are checked independently (not elif).
    Buffers all reasoning into one ('think', full_text) emission, streams
    answer as ('answer', chunk).
    """
    think_buf = ""
    think_emitted = False

    async for chunk in raw:
        if not chunk.choices:
            continue  # final usage-only chunk
        delta = chunk.choices[0].delta
        reasoning = (
            getattr(delta, 'reasoning', None)
            or getattr(delta, 'reasoning_content', None)
        )
        content = delta.content

        # Process both independently — they can appear in the same chunk
        if reasoning:
            think_buf += reasoning
        if content is not None:
            content = _strip_thinking_stream_chunk(content)
        if content:
            # Emit buffered thinking once before first answer chunk
            if think_buf and not think_emitted:
                yield ('think', think_buf)
                think_emitted = True
            yield ('answer', content)

    # Edge case: model thought but produced no answer (generation truncated)
    if think_buf and not think_emitted:
        yield ('think', think_buf)


async def call_llm(
    system_prompt: str,
    user_message: str,
    max_tokens: Optional[int] = None,
    stream: bool = False,
    extra_body: Optional[dict] = None,
    temperature: Optional[float] = None,
) -> str:
    """Single LLM call (non-streaming). Returns full response text."""
    async with get_semaphore():
        if settings.mock_llm:
            await asyncio.sleep(random.uniform(0.5, 2.0))
            return user_message  # caller handles mock logic separately

        client = get_client()
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=temperature if temperature is not None else settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
            **({"extra_body": extra_body} if extra_body else {}),
        )
        return sanitize_answer_text(resp.choices[0].message.content or "")


async def stream_survey_answer(
    persona: dict,
    system_prompt: str,
    question: str,
    question_index: int,
    enable_thinking: bool = True,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream a survey answer. Yields ('think', full_text) then ('answer', chunk) tuples."""
    async with get_semaphore():
        if settings.mock_llm:
            text = _mock_survey_answer(persona, question, question_index)
            async for char in _mock_stream_answer(text):
                yield ('answer', char)
            return

        client = get_client()
        extra_body = {}
        if not enable_thinking:
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}

        raw = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
            **({"extra_body": extra_body} if extra_body else {}),
        )

        async for item in _stream_split_reasoning(raw):
            yield item


async def stream_followup_answer(
    system_prompt: str,
    messages: list[dict],
    enable_thinking: bool = True,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream a follow-up chat response. Yields ('think', full_text) then ('answer', chunk) tuples."""
    async with get_semaphore():
        if settings.mock_llm:
            text = "ご質問いただきありがとうございます。詳しく説明しますと、この件については私の経験から考えると慎重に検討する必要があると思います。具体的には、リスク管理と費用対効果のバランスが重要なポイントです。"
            async for char in _mock_stream_answer(text):
                yield ('answer', char)
            return

        client = get_client()
        extra_body: dict = {}
        if not enable_thinking:
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}

        raw = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=settings.followup_temperature,
            max_tokens=settings.followup_max_tokens,
            stream=True,
            extra_body=extra_body,
        )

        async for item in _stream_split_reasoning(raw):
            yield item


async def generate_questions(survey_theme: str, enable_thinking: bool = True) -> list[str]:
    """Generate survey questions from theme."""
    from prompts import QUESTION_GEN_PROMPT
    variation_seed = random.randint(1, 10000)
    prompt = QUESTION_GEN_PROMPT.format(
        survey_theme=survey_theme,
        variation_seed=variation_seed,
    )

    if settings.mock_llm:
        await asyncio.sleep(0.5)
        theme = survey_theme.strip() or "金融サービス"
        return [
            f"{theme}について、全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）",
            f"{theme}で最も魅力を感じる点、または期待する体験は何ですか？",
            f"{theme}を利用する際に不安に感じる点や、事前に知りたい情報は何ですか？",
            f"{theme}をより使いやすくするために必要だと思う改善点を教えてください。",
        ]

    client = get_client()
    extra_body: dict = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=1024,
            extra_body=extra_body,
        )
    except Exception as e:
        logger.error("Question generation LLM call failed: %s", e)
        return MOCK_QUESTIONS[:3]
    text = sanitize_answer_text(resp.choices[0].message.content or "[]")
    # Strip markdown code blocks if present
    text = re.sub(r'```(?:json)?\s*', '', text).strip()
    # Try to extract JSON array from the response
    json_match = re.search(r'\[.*\]', text, re.DOTALL)
    if json_match:
        text = json_match.group(0)
    try:
        questions = json.loads(text)
        if isinstance(questions, list) and len(questions) > 0:
            return [str(q) for q in questions]
    except Exception:
        logger.warning("Question generation JSON parse failed: %s", text[:200])
    return MOCK_QUESTIONS[:3]


def _fallback_followup_suggestions(
    previous_answers: list[dict],
    chat_history: list[dict],
    excluded_questions: set[str] | None = None,
) -> list[str]:
    del chat_history  # fallback exclusions are controlled by normalized exclusion keys
    excluded = {q for q in (excluded_questions or set()) if q}
    suggestions: list[str] = []
    suggestion_keys: set[str] = set()

    def try_append(candidate: str) -> None:
        cleaned = str(candidate).strip()
        if not cleaned:
            return
        normalized = _normalize_followup_question(cleaned)
        if not normalized or normalized in excluded or normalized in suggestion_keys:
            return
        suggestions.append(cleaned)
        suggestion_keys.add(normalized)

    for answer in previous_answers:
        question = str(answer.get("question_text") or "").strip()
        if question:
            try_append(question)
        if len(suggestions) == 3:
            break
    for fallback in FALLBACK_SUGGESTIONS:
        try_append(fallback)
        if len(suggestions) == 3:
            break
    return suggestions[:3]


FALLBACK_SUGGESTIONS = [
    "具体的にどの程度の手数料なら許容できますか？",
    "どのような情報があれば判断しやすいですか？",
    "このサービスを知人に勧めますか？その理由は？",
]


async def generate_followup_suggestions(
    survey_theme: str,
    persona: dict,
    previous_answers: list[dict],
    chat_history: list[dict],
    excluded_questions: set[str] | None = None,
) -> list[str]:
    """Generate 3 follow-up question suggestions."""
    from prompts import FOLLOWUP_SUGGESTIONS_PROMPT
    excluded = {q for q in (excluded_questions or set()) if q}

    if settings.mock_llm:
        await asyncio.sleep(0.05)
        return _fallback_followup_suggestions(
            previous_answers,
            chat_history,
            excluded_questions=excluded,
        )

    persona_summary = (
        f"{persona.get('name', '不明')}、{persona.get('age', '不明')}歳、"
        f"{persona.get('occupation', '不明')}、{persona.get('prefecture', '不明')}"
    )
    previous_answers_formatted = "\n".join(
        f"- 設問{a.get('question_index', 0) + 1}: {a.get('question_text', '')}\n"
        f"  回答要旨: {sanitize_answer_text(str(a.get('answer') or ''))}"
        for a in previous_answers
    )
    chat_history_formatted = "\n".join(
        f"- {msg.get('role')}: {sanitize_answer_text(str(msg.get('content') or ''))}"
        for msg in chat_history[-6:]
    ) or "（まだ会話なし）"

    prompt = FOLLOWUP_SUGGESTIONS_PROMPT.format(
        survey_theme=survey_theme,
        persona_summary=persona_summary,
        previous_answers_formatted=previous_answers_formatted,
        chat_history_formatted=chat_history_formatted,
    )
    extra_body: dict = {"chat_template_kwargs": {"enable_thinking": False}}

    try:
        resp = await get_client().chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=512,
            extra_body=extra_body,
        )
        text = sanitize_answer_text(resp.choices[0].message.content or "[]")
        text = re.sub(r'```(?:json)?\s*', '', text).strip()

        # Primary: numbered-line parser (more robust for this model)
        raw_items: list[str] = re.findall(r'^\d+[.。)）]\s*(.+)', text, re.MULTILINE)
        if len(raw_items) < 3:
            # Fallback: JSON array parser
            json_match = re.search(r'\[.*\]', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        # Extract first string value from dict (e.g. {"question": "..."})
                        extracted = next(
                            (v for v in item.values() if isinstance(v, str) and v.strip()),
                            None,
                        )
                        if extracted:
                            raw_items.append(extracted)
                    elif isinstance(item, str):
                        raw_items.append(item)

        accepted: list[str] = []
        accepted_keys: set[str] = set()
        for raw in raw_items:
            cleaned = str(raw).strip()
            # Safety guard: reject strings that look like code/JSON objects
            if not cleaned or "{" in cleaned or "}" in cleaned:
                continue
            normalized_cleaned = _normalize_followup_question(cleaned)
            if (
                not normalized_cleaned
                or normalized_cleaned in excluded
                or normalized_cleaned in accepted_keys
            ):
                continue
            accepted.append(cleaned)
            accepted_keys.add(normalized_cleaned)
            if len(accepted) == 3:
                break
        if len(accepted) < 3:
            backfill = _fallback_followup_suggestions(
                previous_answers,
                chat_history,
                excluded_questions=excluded | accepted_keys,
            )
            for candidate in backfill:
                normalized_candidate = _normalize_followup_question(candidate)
                if (
                    not normalized_candidate
                    or normalized_candidate in excluded
                    or normalized_candidate in accepted_keys
                ):
                    continue
                accepted.append(candidate)
                accepted_keys.add(normalized_candidate)
                if len(accepted) == 3:
                    break
        if accepted:
            return accepted[:3]
    except Exception as e:
        logger.warning("Followup suggestions generation failed: %s", e)

    return _fallback_followup_suggestions(
        previous_answers,
        chat_history,
        excluded_questions=excluded,
    )


async def check_llm_health() -> bool:
    """Return True if vLLM endpoint is reachable, False otherwise."""
    if settings.mock_llm:
        return True
    try:
        client = get_client()
        await client.models.list()
        return True
    except Exception:
        return False


async def generate_report_raw(
    survey_theme: str,
    persona_count: int,
    questions: list[str],
    answers_summary: str,
    candidate_personas: str,
) -> str:
    """Run the report LLM call and return raw sanitized text."""
    from prompts import REPORT_SYSTEM_PROMPT

    if settings.mock_llm:
        await asyncio.sleep(1.0)
        qualitative = {
            "group_tendency": MOCK_REPORT["group_tendency"],
            "conclusion_summary": MOCK_REPORT["conclusion_summary"],
            "recommended_actions": MOCK_REPORT["recommended_actions"],
            "conclusion": MOCK_REPORT["conclusion"],
            "top_picks": MOCK_REPORT["top_picks"],
        }
        return json.dumps(qualitative, ensure_ascii=False)

    questions_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    prompt = REPORT_SYSTEM_PROMPT.format(
        survey_theme=survey_theme,
        persona_count=persona_count,
        questions_formatted=questions_formatted,
        answers_summary=answers_summary,
        candidate_personas=candidate_personas,
    )

    client = get_client()
    extra_body: dict = {"chat_template_kwargs": {"enable_thinking": False}}
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=settings.report_max_tokens,
            extra_body=extra_body,
        )
    except Exception as e:
        logger.error("Report generation LLM call failed: %s", e)
        return ""
    return sanitize_answer_text(resp.choices[0].message.content or "")


parse_report_qualitative = report_parsing.parse_report_qualitative
normalize_report_qualitative = report_parsing.normalize_report_qualitative


async def generate_report(
    survey_theme: str,
    persona_count: int,
    questions: list[str],
    answers_summary: str,
    candidate_personas: str,
) -> dict:
    """Generate a report from survey answers."""
    raw_text = await generate_report_raw(
        survey_theme=survey_theme,
        persona_count=persona_count,
        questions=questions,
        answers_summary=answers_summary,
        candidate_personas=candidate_personas,
    )
    parsed = parse_report_qualitative(raw_text)
    if not parsed:
        logger.warning("report raw response was non-json: %s", raw_text[:200])
    elif set(parsed) != set(normalize_report_qualitative(parsed)):
        logger.warning("report parse partially succeeded: %s", raw_text[:200])
    return normalize_report_qualitative(parsed)


# -- Split report generation (3 focused calls with KV-cache shared prefix) ----

async def generate_report_group_tendency(
    shared_system: str,
) -> str:
    """Generate group_tendency as plain text. Returns empty string on failure."""
    from prompts import REPORT_GROUP_TENDENCY_USER

    if settings.mock_llm:
        await asyncio.sleep(0.3)
        return MOCK_REPORT["group_tendency"]

    client = get_client()
    extra_body: dict = {
        "chat_template_kwargs": {"enable_thinking": False},
        "repetition_penalty": settings.report_repetition_penalty,
    }
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": shared_system},
                {"role": "user", "content": REPORT_GROUP_TENDENCY_USER},
            ],
            temperature=settings.report_temperature,
            frequency_penalty=settings.report_frequency_penalty,
            max_tokens=2048,
            extra_body=extra_body,
        )
        reasoning = getattr(resp.choices[0].message, 'reasoning_content', None)
        if reasoning:
            logger.info("group_tendency reasoning_content_len=%d", len(reasoning))
        raw = sanitize_answer_text(resp.choices[0].message.content or "")
        cached = resp.usage and getattr(resp.usage, "prompt_tokens_details", None)
        if cached:
            logger.info("group_tendency cached_tokens=%s", getattr(cached, "cached_tokens", "?"))
        result = _strip_thinking(raw).strip()
        if not result:
            logger.warning("group_tendency: empty after stripping thinking tags")
            return ""
        # Detect prompt echo-back
        if detect_prompt_echo(REPORT_GROUP_TENDENCY_USER, result):
            logger.warning("group_tendency: detected prompt echo, triggering fallback")
            return ""
        return result
    except Exception as e:
        logger.error("generate_report_group_tendency failed: %s", e)
        return ""


async def generate_report_conclusion(
    shared_system: str,
    group_tendency: str,
) -> str:
    """Generate conclusion as plain text. Returns empty string on failure."""
    from prompts import REPORT_CONCLUSION_USER

    if settings.mock_llm:
        await asyncio.sleep(0.3)
        return MOCK_REPORT["conclusion"]

    client = get_client()
    extra_body: dict = {
        "chat_template_kwargs": {"enable_thinking": False},
        "repetition_penalty": settings.report_repetition_penalty,
    }
    user_content = REPORT_CONCLUSION_USER.format(group_tendency=group_tendency or "（傾向データなし）")
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": shared_system},
                {"role": "user", "content": user_content},
            ],
            temperature=settings.report_temperature,
            frequency_penalty=settings.report_frequency_penalty,
            max_tokens=4096,
            extra_body=extra_body,
        )
        reasoning = getattr(resp.choices[0].message, 'reasoning_content', None)
        if reasoning:
            logger.info("conclusion reasoning_content_len=%d", len(reasoning))
        raw = sanitize_answer_text(resp.choices[0].message.content or "")
        cached = resp.usage and getattr(resp.usage, "prompt_tokens_details", None)
        if cached:
            logger.info("conclusion cached_tokens=%s", getattr(cached, "cached_tokens", "?"))
        result = _strip_thinking(raw).strip()
        if not result:
            logger.warning("conclusion: empty after stripping thinking tags")
            return ""
        # Detect prompt echo-back using ONLY the static instruction portion,
        # NOT the dynamic group_tendency (which the model legitimately reuses)
        from prompts import REPORT_CONCLUSION_INSTRUCTION
        if detect_prompt_echo(REPORT_CONCLUSION_INSTRUCTION, result):
            logger.warning("conclusion: detected prompt echo, triggering fallback")
            return ""
        return result
    except Exception as e:
        logger.error("generate_report_conclusion failed: %s", e)
        return ""


async def generate_report_top_picks(
    shared_system: str,
    top_pick_candidates: str,
) -> list[dict]:
    """Generate top_picks using structured output. Returns list of pick dicts."""
    from prompts import REPORT_TOP_PICKS_USER
    from pydantic import BaseModel as _BaseModel

    if settings.mock_llm:
        await asyncio.sleep(0.3)
        return MOCK_REPORT.get("top_picks", [])

    class _TopPickItem(_BaseModel):
        persona_uuid: str
        persona_name: str
        persona_summary: str
        highlight_reason: str
        highlight_quote: str

    class _TopPicksResponse(_BaseModel):
        picks: list[_TopPickItem]

    user_content = REPORT_TOP_PICKS_USER.format(top_pick_candidates=top_pick_candidates)
    schema = _TopPicksResponse.model_json_schema()
    client = get_client()
    extra_body: dict = {
        "structured_outputs": {"json": schema},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    try:
        resp = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": shared_system},
                {"role": "user", "content": user_content},
            ],
            temperature=settings.report_temperature,
            max_tokens=2048,
            extra_body=extra_body,
        )
        reasoning = getattr(resp.choices[0].message, 'reasoning_content', None)
        if reasoning:
            logger.info("top_picks reasoning_content_len=%d", len(reasoning))
        cached = resp.usage and getattr(resp.usage, "prompt_tokens_details", None)
        if cached:
            logger.info("top_picks cached_tokens=%s", getattr(cached, "cached_tokens", "?"))
        raw = resp.choices[0].message.content or ""
        try:
            import json_repair
        except ImportError:
            json_repair = None  # type: ignore[assignment]
        data = json_repair.loads(raw) if json_repair else json.loads(raw)
        if isinstance(data, dict) and "picks" in data:
            return [item if isinstance(item, dict) else {} for item in data["picks"]]
        if isinstance(data, list):
            return data
        return []
    except Exception as e:
        logger.error("generate_report_top_picks failed: %s", e)
        return []


# -- Financial extension generation -------------------------------------------

_FINANCIAL_BATCH_SIZE = 8


def _random_financial_extension() -> "FinancialExtension":
    """Random fallback used for mock mode or parse failures. Result is NOT cached."""
    from models import FinancialExtension
    return FinancialExtension(
        financial_literacy=random.choices(
            ["初心者", "中級者", "上級者", "専門家"],
            weights=[40, 38, 17, 5],
        )[0],
        investment_experience="",
        financial_concerns="",
        annual_income_bracket=random.choice(
            ["300万未満", "300-500万", "500-800万", "800-1200万", "1200万以上"]
        ),
        asset_bracket=random.choice(["500万未満", "500-2000万", "2000-5000万", "5000万以上"]),
        primary_bank_type=random.choice(
            ["メガバンク", "地方銀行", "ネット銀行", "信用金庫", "証券会社"]
        ),
    )


async def _generate_financial_extension_single(
    persona: dict,
) -> tuple["FinancialExtension", bool]:
    """Generate financial profile for one persona. Returns (extension, should_cache)."""
    from models import FinancialExtensionSchema, FinancialExtension
    from prompts import FINANCIAL_EXTENSION_PROMPT, sex_display

    prompt = FINANCIAL_EXTENSION_PROMPT.format(
        name=persona.get("name", "不明"),
        age=persona.get("age", "不明"),
        sex_display=sex_display(persona.get("sex", "")),
        prefecture=persona.get("prefecture", "不明"),
        region=persona.get("region", "不明"),
        occupation=persona.get("occupation", "不明"),
        education_level=persona.get("education_level", "不明"),
        marital_status=persona.get("marital_status", "不明"),
        persona=persona.get("persona", ""),
        skills_and_expertise=persona.get("skills_and_expertise", ""),
    )
    schema = FinancialExtensionSchema.model_json_schema()
    extra_body = {
        "structured_outputs": {"json": schema},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    raw = ""
    try:
        raw = await call_llm(
            system_prompt="あなたは金融プロファイル生成AIです。",
            user_message=prompt,
            max_tokens=300,
            extra_body=extra_body,
            temperature=1.1,
        )
        data = json.loads(raw)
        return FinancialExtension(**data), True
    except Exception:
        try:
            try:
                import json_repair
            except ImportError:
                json_repair = None  # type: ignore[assignment]
            if json_repair is not None and raw:
                repaired = json_repair.loads(raw)
                return FinancialExtension(**repaired), True
        except Exception:
            pass
        return _random_financial_extension(), False


class _ProfileBatch(BaseModel):
    """Wrapper for structured output of N financial profiles."""
    profiles: list["FinancialExtensionSchema"]


async def generate_financial_extension_batch(
    personas: list[dict],
) -> list[tuple["FinancialExtension", bool]]:
    """
    Generate financial profiles for a small batch (≤8) in one LLM call.
    Returns list of (FinancialExtension, should_cache) tuples, same order as input.
    Falls back to per-persona on parse failure (result not cached).
    """
    from models import FinancialExtension, FinancialExtensionSchema
    from prompts import FINANCIAL_EXTENSION_BATCH_PROMPT, sex_display

    if settings.mock_llm:
        return [(_random_financial_extension(), True) for _ in personas]

    lines = []
    for i, p in enumerate(personas, 1):
        persona_excerpt = (p.get("professional_persona") or p.get("persona") or "")[:80]
        lines.append(
            f"[{i}] {p.get('name', '不明')}, {p.get('age', '?')}歳, "
            f"{sex_display(p.get('sex', ''))}, 職業: {p.get('occupation', '不明')}, "
            f"学歴: {p.get('education_level', '不明')}, 特徴: {persona_excerpt}"
        )
    personas_block = "\n".join(lines)
    n = len(personas)

    # Build batch schema with concrete FinancialExtensionSchema
    class _BatchModel(BaseModel):
        profiles: list[FinancialExtensionSchema]

    schema = _BatchModel.model_json_schema()
    extra_body = {
        "structured_outputs": {"json": schema},
        "chat_template_kwargs": {"enable_thinking": False},
    }

    try:
        raw = await call_llm(
            system_prompt="あなたは金融プロファイル生成AIです。",
            user_message=FINANCIAL_EXTENSION_BATCH_PROMPT.format(
                n=n, personas_block=personas_block
            ),
            max_tokens=400 * n,
            extra_body=extra_body,
            temperature=1.1,
        )
        data = json.loads(raw)
        batch = _BatchModel.model_validate(data)
        if len(batch.profiles) != n:
            raise ValueError(f"Expected {n} profiles, got {len(batch.profiles)}")
        return [(FinancialExtension(**p.model_dump()), True) for p in batch.profiles]
    except Exception as e:
        logger.warning(
            "batch financial_extension parse failed (%s), falling back to per-persona", e
        )
        tasks = [_generate_financial_extension_single(p) for p in personas]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: list[tuple[FinancialExtension, bool]] = []
        for r, p in zip(results, personas):
            if isinstance(r, Exception):
                logger.warning("per-persona fallback failed for %s: %s", p.get("uuid"), r)
                out.append((_random_financial_extension(), False))
            else:
                out.append(r)  # type: ignore[arg-type]
        return out


async def generate_financial_extensions(
    personas: list[dict],
) -> list[tuple["FinancialExtension", bool]]:
    """
    Generate financial profiles for any number of personas.
    Splits into chunks of _FINANCIAL_BATCH_SIZE, runs batches concurrently.
    """
    chunks = [
        personas[i:i + _FINANCIAL_BATCH_SIZE]
        for i in range(0, len(personas), _FINANCIAL_BATCH_SIZE)
    ]
    chunk_results = await asyncio.gather(
        *[generate_financial_extension_batch(chunk) for chunk in chunks]
    )
    return [item for sublist in chunk_results for item in sublist]
