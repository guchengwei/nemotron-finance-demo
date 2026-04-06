"""Matrix report pipeline orchestrator.

Uses asyncio.Queue pattern from survey.py for progressive SSE streaming.
Each stage yields (event_type, event_data) tuples.
"""

import asyncio
import logging
import re
from typing import Any, AsyncGenerator

from config import settings
from llm import get_client, get_semaphore
from matrix_models import (
    AXIS_PRESETS, AxisPreset, ScoredPersona, KeywordEntry,
    KeywordSummary, Recommendation, MatrixReportData,
)
from matrix_scorer import score_persona, _strip_fences
from matrix_keywords import aggregate_keywords
from matrix_projection import spread_scores, assign_quadrant

import json_repair  # type: ignore

logger = logging.getLogger(__name__)

RECOMMENDATIONS_PROMPT = """あなたはフィンテック戦略アドバイザーです。アンケート分析結果を基に、製品改善の提言を3つ生成してください。

【弱点キーワード（上位）】
{weakness_keywords}

【象限分布】
{quadrant_distribution}

以下のJSON配列のみで回答してください（他のテキストは不要）:
[
  {{"title": "<提言タイトル>", "highlight_tag": "<キーワードタグ>", "body": "<具体的な提言内容>"}},
  {{"title": "<提言タイトル>", "highlight_tag": "<キーワードタグ>", "body": "<具体的な提言内容>"}},
  {{"title": "<提言タイトル>", "highlight_tag": "<キーワードタグ>", "body": "<具体的な提言内容>"}}
]"""

MOCK_ELABORATIONS: dict[str, str] = {
    "手数料の安さ": "競合他社と比べた手数料の低さが強みとして認識されており、コスト意識の高いユーザー層を引き付けています。",
    "セキュリティ不安": "個人情報や資産管理に対する不安感が障壁となっており、信頼性向上施策が求められます。",
    "高金利・資産管理": "高い利回りや資産管理機能への期待が採用動機となっており、投資意欲の高い層に訴求しています。",
    "24時間・場所不問": "いつでもどこでも利用できる利便性が支持されており、忙しいビジネスパーソンに特に響いています。",
    "対面サポート欠如": "オンラインのみのサポートに不満を感じるユーザーが多く、対面や電話での相談窓口整備が課題です。",
    "業務連携ツール": "既存の業務システムとの連携機能が評価されており、業務効率化を重視する企業ユーザーに支持されています。",
    "学習コスト": "新しいシステムの習得に時間とコストがかかることへの懸念があり、直感的なUIの改善が求められます。",
}

ELABORATION_PROMPT = """あなたはフィンテック調査の分析専門家です。アンケートで複数のペルソナから言及されたキーワードについて、それぞれ1〜2文の日本語で説明してください。

【キーワード一覧】
{keyword_list}

以下のJSON形式のみで回答してください（他のテキストは不要）:
{{"<キーワード>": "<1〜2文の説明>", "<キーワード>": "<1〜2文の説明>"}}"""


async def elaborate_keywords(keywords: KeywordSummary) -> dict[str, str]:
    """Call LLM once to elaborate all aggregated keywords.

    Returns a dict mapping keyword text → elaboration sentence.
    Falls back to empty dict on any error (caller uses DEFAULT_ELABORATION).
    """
    all_kws = [kw.text for kw in keywords.strengths + keywords.weaknesses]
    if not all_kws:
        return {}

    keyword_list = "\n".join(f"- {t}" for t in all_kws)
    prompt = ELABORATION_PROMPT.format(keyword_list=keyword_list)

    try:
        async with get_semaphore():
            client = get_client()
            response = await client.chat.completions.create(
                model=settings.vllm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=settings.report_temperature,
                max_tokens=settings.report_max_tokens,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )

        raw = response.choices[0].message.content or ""
        text = _strip_fences(raw)
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            logger.warning("No JSON object in elaboration response")
            return {}

        data = json_repair.loads(match.group())
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}

    except Exception as e:
        logger.error("Keyword elaboration failed: %s", e)
        return {}


async def generate_recommendations(keywords: KeywordSummary, scored: list[ScoredPersona]) -> list[dict]:
    """Call LLM to generate 3 strategic recommendations.

    Uses the same get_client() + get_semaphore() pattern from llm.py.
    Returns a list of recommendation dicts matching the Recommendation model.
    """
    weakness_kws = ", ".join(kw.text for kw in keywords.weaknesses[:5]) or "（なし）"

    quadrant_counts: dict[str, int] = {}
    for p in scored:
        label = p.quadrant_label or "不明"
        quadrant_counts[label] = quadrant_counts.get(label, 0) + 1
    quadrant_dist = "、".join(f"{label}: {count}名" for label, count in quadrant_counts.items())

    prompt = RECOMMENDATIONS_PROMPT.format(
        weakness_keywords=weakness_kws,
        quadrant_distribution=quadrant_dist or "（データなし）",
    )

    async with get_semaphore():
        client = get_client()
        response = await client.chat.completions.create(
            model=settings.vllm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=settings.report_temperature,
            max_tokens=settings.report_max_tokens,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )

    raw = response.choices[0].message.content or ""
    text = _strip_fences(raw)

    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        logger.warning("No JSON array found in recommendations response")
        return []

    try:
        data = json_repair.loads(match.group())
    except Exception:
        logger.warning("Failed to parse recommendations JSON")
        return []

    if not isinstance(data, list):
        return []

    recs = []
    for item in data[:3]:
        if isinstance(item, dict) and "title" in item and "body" in item:
            recs.append({
                "title": str(item.get("title", "")),
                "highlight_tag": str(item.get("highlight_tag", "")),
                "body": str(item.get("body", "")),
            })
    return recs


async def run_matrix_pipeline(
    survey_data: dict,
    preset_key: str = "interest_barrier",
) -> AsyncGenerator[tuple[str, Any], None]:
    """
    Main orchestrator. Yields (event_type, event_data) tuples.

    Uses asyncio.Queue for concurrent persona scoring (same pattern as
    survey.py:210-256), NOT asyncio.gather with yield.
    """
    # Stage 1: Resolve axes
    if preset_key not in AXIS_PRESETS:
        yield ("report_error", {"error": f"Unknown preset: {preset_key}"})
        return

    axes = AXIS_PRESETS[preset_key]
    yield ("axis_ready", axes.model_dump())

    # Stage 2: Score personas concurrently via Queue
    personas_input = survey_data.get("personas", [])
    if not personas_input:
        yield ("report_error", {"error": "No persona data to score"})
        return

    event_queue: asyncio.Queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(settings.llm_concurrency)
    scored: list[ScoredPersona] = []

    async def score_one(p: dict):
        async with semaphore:
            try:
                result = await score_persona(
                    p["persona_id"],
                    p["name"],
                    p.get("industry", ""),
                    p.get("age", 0),
                    p.get("qa_text", ""),
                    axes,
                )
                await event_queue.put(("persona_scored", result))
            except Exception as e:
                logger.error("Scoring failed for %s: %s", p.get("name", "?"), e)
                await event_queue.put(("persona_score_error", {
                    "persona_id": p.get("persona_id", ""),
                    "name": p.get("name", ""),
                    "error": str(e),
                }))

    tasks = [asyncio.create_task(score_one(p)) for p in personas_input]
    pending = set(tasks)

    while pending or not event_queue.empty():
        try:
            event_type, event_data = event_queue.get_nowait()
            if event_type != "persona_scored":
                yield (event_type, event_data)
            if event_type == "persona_scored":
                scored.append(ScoredPersona(**event_data))
        except asyncio.QueueEmpty:
            done = {t for t in pending if t.done()}
            pending -= done
            if pending:
                await asyncio.sleep(0.05)
            else:
                while not event_queue.empty():
                    event_type, event_data = event_queue.get_nowait()
                    if event_type != "persona_scored":
                        yield (event_type, event_data)
                    if event_type == "persona_scored":
                        scored.append(ScoredPersona(**event_data))
                break

    # Stage 2b: Project scores for better distribution
    # Sort by persona_id for deterministic tie-breaking in spread_scores()
    if len(scored) >= 2:
        scored.sort(key=lambda p: p.persona_id or p.name or "")
        raw_xs = [p.x_score for p in scored]
        raw_ys = [p.y_score for p in scored]
        spread_xs = spread_scores(raw_xs)
        spread_ys = spread_scores(raw_ys)
        for p, sx, sy in zip(scored, spread_xs, spread_ys):
            p.x_score_raw = p.x_score
            p.y_score_raw = p.y_score
            p.x_score = sx
            p.y_score = sy
            p.quadrant_label = assign_quadrant(sx, sy, axes)
    elif len(scored) == 1:
        scored[0].x_score_raw = scored[0].x_score
        scored[0].y_score_raw = scored[0].y_score
        scored[0].quadrant_label = assign_quadrant(scored[0].x_score, scored[0].y_score, axes)

    # Yield all scored personas (after projection applied)
    for p in scored:
        yield ("persona_scored", p.model_dump())

    # Stage 3: Keyword aggregation (deterministic, no LLM)
    keywords = aggregate_keywords(scored)
    yield ("keywords_ready", keywords.model_dump())

    # Stage 3b: Keyword elaboration
    all_keywords = list(keywords.strengths) + list(keywords.weaknesses)
    if settings.mock_llm:
        for kw in all_keywords:
            elaboration = MOCK_ELABORATIONS.get(kw.text, "")
            yield ("keyword_elaborated", {"keyword_text": kw.text, "elaboration": elaboration})
    else:
        elaboration_map = await elaborate_keywords(keywords)
        for kw in all_keywords:
            elaboration = elaboration_map.get(kw.text, "")
            yield ("keyword_elaborated", {"keyword_text": kw.text, "elaboration": elaboration})

    # Stage 4: Recommendations
    if settings.mock_llm:
        mock_recs = [
            {"title": "段階的な移行支援", "highlight_tag": "併用モデル",
             "body": "地方銀行との併用モデルで不安を緩和。既存口座との連携機能を前面に出す"},
            {"title": "地域特化コンテンツ", "highlight_tag": "地産地消・物流",
             "body": "高知の地産地消に特化した決済・送金機能。地方の現金文化にも対応"},
            {"title": "リテラシー支援", "highlight_tag": "シンプルUI",
             "body": "専門家相談窓口の整備。初心者向け動画・チュートリアルを充実"},
        ]
        yield ("recommendations_ready", mock_recs)
    else:
        try:
            recs = await generate_recommendations(keywords, scored)
        except Exception as e:
            logger.error("Recommendation generation failed: %s", e)
            recs = []
        yield ("recommendations_ready", recs)

    # Build score table
    table = [
        {"persona_id": p.persona_id, "name": p.name,
         "x_score": p.x_score, "y_score": p.y_score,
         "x_score_raw": p.x_score_raw, "y_score_raw": p.y_score_raw,
         "industry": p.industry, "age": p.age,
         "quadrant_label": p.quadrant_label}
        for p in scored
    ]
    yield ("score_table_ready", table)

    yield ("report_complete", {
        "total_scored": len(scored),
        "total_failed": len(personas_input) - len(scored),
    })
