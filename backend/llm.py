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

logger = logging.getLogger(__name__)
REPORT_ALLOWED_KEYS = {"group_tendency", "conclusion", "top_picks"}

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


def sanitize_answer_text(text: str) -> str:
    """Remove leaked reasoning markup from model-visible answer text."""
    cleaned = _strip_thinking(text)
    # Aggressively strip any residual think tag fragments
    cleaned = re.sub(r'</?think[^>]*>', '', cleaned, flags=re.IGNORECASE)
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

        async def _chunks() -> AsyncGenerator[str, None]:
            async for chunk in raw:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        async for item in _stream_split_thinking(_chunks()):
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
        extra_body = {}
        if not enable_thinking:
            extra_body["chat_template_kwargs"] = {"enable_thinking": False}

        raw = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.followup_max_tokens,
            stream=True,
            **({"extra_body": extra_body} if extra_body else {}),
        )

        async def _chunks() -> AsyncGenerator[str, None]:
            async for chunk in raw:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        async for item in _stream_split_thinking(_chunks()):
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


def parse_report_qualitative(raw_text: str) -> dict[str, Any]:
    """Parse report JSON loosely and keep partial qualitative fields when possible."""
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
    for field_name in ("group_tendency", "conclusion"):
        value = _extract_string_field(cleaned, field_name)
        if isinstance(value, str) and value.strip():
            partial[field_name] = value.strip()

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
    """Keep only allowed qualitative keys and tolerate malformed fields."""
    normalized: dict[str, Any] = {}
    if not isinstance(parsed, dict):
        return normalized

    group_tendency = parsed.get("group_tendency")
    if isinstance(group_tendency, str) and group_tendency.strip():
        normalized["group_tendency"] = group_tendency.strip()

    conclusion = parsed.get("conclusion")
    if isinstance(conclusion, str) and conclusion.strip():
        normalized["conclusion"] = conclusion.strip()

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
