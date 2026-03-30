"""Matrix report pipeline orchestrator.

Uses asyncio.Queue pattern from survey.py for progressive SSE streaming.
Each stage yields (event_type, event_data) tuples.
"""

import asyncio
import logging
from typing import AsyncGenerator

from config import settings
from matrix_models import (
    AXIS_PRESETS, AxisPreset, ScoredPersona, KeywordEntry,
    KeywordSummary, Recommendation, MatrixReportData,
)
from matrix_scorer import score_persona
from matrix_keywords import aggregate_keywords

logger = logging.getLogger(__name__)


async def run_matrix_pipeline(
    survey_data: dict,
    preset_key: str = "interest_barrier",
) -> AsyncGenerator[tuple[str, dict], None]:
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
                    yield (event_type, event_data)
                    if event_type == "persona_scored":
                        scored.append(ScoredPersona(**event_data))
                break

    # Stage 3: Keyword aggregation (deterministic, no LLM)
    keywords = aggregate_keywords(scored)
    yield ("keywords_ready", keywords.model_dump())

    # Stage 4: Recommendations (mock only for now)
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

    # Build score table
    table = [
        {"persona_id": p.persona_id, "name": p.name,
         "x_score": p.x_score, "y_score": p.y_score,
         "industry": p.industry, "age": p.age,
         "quadrant_label": p.quadrant_label}
        for p in scored
    ]
    yield ("score_table_ready", table)

    yield ("report_complete", {
        "total_scored": len(scored),
        "total_failed": len(personas_input) - len(scored),
    })
