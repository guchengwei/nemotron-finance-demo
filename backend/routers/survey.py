"""Survey run endpoint with SSE streaming."""

import asyncio
import json
import logging
import re
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import aiosqlite

from config import settings
from models import SurveyRunRequest
from llm import stream_survey_answer, generate_questions
from prompts import build_survey_system_prompt, sex_display

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/survey", tags=["survey"])

# Score extraction patterns
_SCORE_RE_1 = re.compile(r'【評価[:：]\s*(\d)】')
_SCORE_RE_2 = re.compile(r'^(\d)\s*[。、.:/／]')


def extract_score(text: str) -> int | None:
    m = _SCORE_RE_1.search(text)
    if m:
        return int(m.group(1))
    m = _SCORE_RE_2.match(text.strip())
    if m:
        return int(m.group(1))
    return None


async def _get_persona(db: aiosqlite.Connection, persona_id: str) -> dict | None:
    db.row_factory = aiosqlite.Row
    rows = await db.execute_fetchall(
        "SELECT p.*, pfc.financial_literacy, pfc.investment_experience, "
        "pfc.financial_concerns, pfc.annual_income_bracket, pfc.asset_bracket, "
        "pfc.primary_bank_type "
        "FROM personas p "
        "LEFT JOIN persona_financial_context pfc ON p.uuid = pfc.persona_uuid "
        "WHERE p.uuid = ?",
        [persona_id]
    )
    if not rows:
        return None
    return dict(rows[0])


def _build_financial_ext(row: dict) -> dict | None:
    if row.get("financial_literacy"):
        return {
            "financial_literacy": row.get("financial_literacy"),
            "investment_experience": row.get("investment_experience"),
            "financial_concerns": row.get("financial_concerns"),
            "annual_income_bracket": row.get("annual_income_bracket"),
            "asset_bracket": row.get("asset_bracket"),
            "primary_bank_type": row.get("primary_bank_type"),
        }
    return None


def _persona_summary(p: dict) -> str:
    sex_str = sex_display(p.get("sex", ""))
    return f"{p.get('name', '不明')}, {p.get('age', '?')}歳{sex_str}, {p.get('occupation', '')}, {p.get('prefecture', '')}"


async def _run_persona_survey(
    persona_id: str,
    persona_index: int,
    total: int,
    questions: list[str],
    run_id: str,
    survey_theme: str,
    event_queue: asyncio.Queue,
    persona_db: aiosqlite.Connection,
    history_db: aiosqlite.Connection,
):
    """Run all questions for a single persona and queue SSE events."""
    try:
        persona = await _get_persona(persona_db, persona_id)
        if not persona:
            logger.warning("Persona %s not found", persona_id)
            return

        name = persona.get("name", "不明")
        await event_queue.put({
            "event": "persona_start",
            "data": {"persona_uuid": persona_id, "name": name, "index": persona_index, "total": total}
        })

        fin_ext = _build_financial_ext(persona)
        system_prompt = build_survey_system_prompt(persona, fin_ext)
        persona_summary = _persona_summary(persona)
        persona_full_json = json.dumps(persona, ensure_ascii=False, default=str)

        for q_idx, question in enumerate(questions):
            full_answer = ""
            full_thinking = ""
            try:
                async for kind, chunk in stream_survey_answer(persona, system_prompt, question, q_idx):
                    if kind == 'think':
                        full_thinking = chunk
                        await event_queue.put({
                            "event": "persona_thinking",
                            "data": {"persona_uuid": persona_id, "question_index": q_idx, "thinking": chunk}
                        })
                    else:
                        full_answer += chunk
                        await event_queue.put({
                            "event": "persona_answer_chunk",
                            "data": {"persona_uuid": persona_id, "question_index": q_idx, "chunk": chunk}
                        })
            except Exception as e:
                logger.error("LLM error for persona %s q%d: %s", persona_id, q_idx, e)
                full_answer = "（回答を取得できませんでした）"
                await event_queue.put({
                    "event": "persona_error",
                    "data": {
                        "persona_uuid": persona_id,
                        "question_index": q_idx,
                        "error": str(e),
                    },
                })

            score = extract_score(full_answer)

            # Save to history
            try:
                await history_db.execute(
                    "INSERT INTO survey_answers "
                    "(run_id, persona_uuid, persona_summary, persona_full_json, "
                    "question_index, question_text, answer, score) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [run_id, persona_id, persona_summary, persona_full_json,
                     q_idx, question, full_answer, score]
                )
                await history_db.commit()
            except Exception as e:
                logger.error("History save error: %s", e)

            await event_queue.put({
                "event": "persona_answer",
                "data": {
                    "persona_uuid": persona_id,
                    "question_index": q_idx,
                    "answer": full_answer,
                    "score": score,
                    "thinking": full_thinking or None,
                }
            })

        await event_queue.put({
            "event": "persona_complete",
            "data": {"persona_uuid": persona_id, "index": persona_index}
        })

    except Exception as e:
        logger.error("Persona %s survey failed: %s", persona_id, e)
        await event_queue.put({
            "event": "persona_error",
            "data": {"persona_uuid": persona_id, "error": str(e)}
        })


async def _survey_stream(request: SurveyRunRequest) -> AsyncGenerator[str, None]:
    run_id = str(uuid.uuid4())
    persona_ids = request.persona_ids
    total = len(persona_ids)

    async with aiosqlite.connect(settings.history_db_path) as history_db:
        # Resolve questions
        questions = request.questions or []
        if not questions:
            questions = await generate_questions(request.survey_theme)
            yield f"event: questions_generated\ndata: {json.dumps({'questions': questions}, ensure_ascii=False)}\n\n"

        # Create run record
        await history_db.execute(
            "INSERT INTO survey_runs (id, survey_theme, questions_json, persona_count, status, label) "
            "VALUES (?, ?, ?, ?, 'running', ?)",
            [run_id, request.survey_theme, json.dumps(questions, ensure_ascii=False),
             total, request.label]
        )
        await history_db.commit()

        yield f"event: run_created\ndata: {json.dumps({'run_id': run_id, 'total_personas': total}, ensure_ascii=False)}\n\n"

        if request.questions:
            yield f"event: questions_generated\ndata: {json.dumps({'questions': questions}, ensure_ascii=False)}\n\n"

        # Run personas with concurrency limit
        event_queue: asyncio.Queue = asyncio.Queue()
        semaphore = asyncio.Semaphore(settings.llm_concurrency)
        completed = 0
        failed = 0

        async def run_with_sem(pid, idx):
            async with semaphore:
                async with aiosqlite.connect(settings.db_path) as persona_db:
                    await _run_persona_survey(
                        pid, idx, total, questions, run_id,
                        request.survey_theme, event_queue, persona_db, history_db
                    )

        tasks = [asyncio.create_task(run_with_sem(pid, i)) for i, pid in enumerate(persona_ids)]

        pending_tasks = set(tasks)
        while pending_tasks or not event_queue.empty():
            try:
                event = event_queue.get_nowait()
                etype = event["event"]
                edata = json.dumps(event["data"], ensure_ascii=False)
                yield f"event: {etype}\ndata: {edata}\n\n"
                if etype == "persona_complete":
                    completed += 1
                elif etype == "persona_error":
                    failed += 1
            except asyncio.QueueEmpty:
                # Check if tasks are done
                done = {t for t in pending_tasks if t.done()}
                pending_tasks -= done
                if pending_tasks:
                    await asyncio.sleep(0.05)
                else:
                    # Drain remaining queue
                    while not event_queue.empty():
                        event = event_queue.get_nowait()
                        etype = event["event"]
                        edata = json.dumps(event["data"], ensure_ascii=False)
                        yield f"event: {etype}\ndata: {edata}\n\n"
                        if etype == "persona_complete":
                            completed += 1
                        elif etype == "persona_error":
                            failed += 1
                    break

        # Mark run complete
        await history_db.execute(
            "UPDATE survey_runs SET status = 'completed' WHERE id = ?",
            [run_id]
        )
        await history_db.commit()

        yield f"event: survey_complete\ndata: {json.dumps({'run_id': run_id, 'completed': completed, 'failed': failed}, ensure_ascii=False)}\n\n"


@router.post("/run")
async def run_survey(request: SurveyRunRequest):
    """Run a survey across personas with SSE streaming."""
    return StreamingResponse(
        _survey_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
