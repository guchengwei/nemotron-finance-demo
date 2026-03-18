"""LLM client with mock mode support.

Mock mode (MOCK_LLM=true) returns template responses with persona details
injected. Adds 0.5-2s random delay to simulate streaming.
"""

import asyncio
import json
import logging
import random
import re
from typing import AsyncGenerator, Optional

from openai import AsyncOpenAI

from config import settings

logger = logging.getLogger(__name__)

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
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()


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
                start = buf.find('<think>')
                if start == -1:
                    if buf:
                        yield ('answer', buf)
                        buf = ""
                    break
                # flush answer content before <think> (rare but handle it)
                if start > 0:
                    yield ('answer', buf[:start])
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
    if buf and not in_think:
        yield ('answer', buf)


async def call_llm(
    system_prompt: str,
    user_message: str,
    max_tokens: Optional[int] = None,
    stream: bool = False,
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
            temperature=settings.llm_temperature,
            max_tokens=max_tokens or settings.llm_max_tokens,
        )
        return _strip_thinking(resp.choices[0].message.content or "")


async def stream_survey_answer(
    persona: dict,
    system_prompt: str,
    question: str,
    question_index: int,
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream a survey answer. Yields ('think', full_text) then ('answer', chunk) tuples."""
    async with get_semaphore():
        if settings.mock_llm:
            text = _mock_survey_answer(persona, question, question_index)
            async for char in _mock_stream_answer(text):
                yield ('answer', char)
            return

        client = get_client()
        raw = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
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
) -> AsyncGenerator[tuple[str, str], None]:
    """Stream a follow-up chat response. Yields ('think', full_text) then ('answer', chunk) tuples."""
    async with get_semaphore():
        if settings.mock_llm:
            text = "ご質問いただきありがとうございます。詳しく説明しますと、この件については私の経験から考えると慎重に検討する必要があると思います。具体的には、リスク管理と費用対効果のバランスが重要なポイントです。"
            async for char in _mock_stream_answer(text):
                yield ('answer', char)
            return

        client = get_client()
        raw = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
        )

        async def _chunks() -> AsyncGenerator[str, None]:
            async for chunk in raw:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

        async for item in _stream_split_thinking(_chunks()):
            yield item


async def generate_questions(survey_theme: str) -> list[str]:
    """Generate survey questions from theme."""
    from prompts import QUESTION_GEN_PROMPT
    prompt = QUESTION_GEN_PROMPT.format(survey_theme=survey_theme)

    if settings.mock_llm:
        await asyncio.sleep(0.5)
        return MOCK_QUESTIONS[:4]

    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.vllm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=512,
    )
    text = _strip_thinking(resp.choices[0].message.content or "[]")
    # Strip markdown code blocks if present
    text = re.sub(r'```(?:json)?\s*', '', text).strip()
    try:
        questions = json.loads(text)
        if isinstance(questions, list):
            return [str(q) for q in questions]
    except Exception:
        pass
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


async def generate_report(
    survey_theme: str,
    persona_count: int,
    questions: list[str],
    answers_summary: str,
) -> dict:
    """Generate a report from survey answers."""
    from prompts import REPORT_SYSTEM_PROMPT
    import json_repair

    if settings.mock_llm:
        await asyncio.sleep(1.0)
        report = MOCK_REPORT.copy()
        report["overall_score"] = round(random.uniform(2.8, 4.2), 1)
        return report

    questions_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    prompt = REPORT_SYSTEM_PROMPT.format(
        survey_theme=survey_theme,
        persona_count=persona_count,
        questions_formatted=questions_formatted,
        answers_summary=answers_summary,
    )

    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.vllm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=settings.report_max_tokens,
    )
    text = _strip_thinking(resp.choices[0].message.content or "{}")
    text = re.sub(r'```(?:json)?\s*', '', text).strip()
    try:
        return json_repair.loads(text)
    except Exception:
        logger.error("Report JSON parse failed: %s", text[:200])
        return {}
