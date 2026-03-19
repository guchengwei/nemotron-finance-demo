"""Survey run endpoint with SSE streaming."""

import asyncio
import json
import logging
import re
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
import aiosqlite

from config import settings
from e2e_support import get_e2e_scenario
from models import QuestionGenerationRequest, QuestionGenerationResponse, SurveyRunRequest
from llm import generate_questions, sanitize_answer_text, stream_survey_answer
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


async def _get_persona(persona_id: str) -> dict | None:
    from persona_store import get_store
    return get_store().get_persona(persona_id)


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
    history_db: aiosqlite.Connection,
    e2e_scenario: str | None = None,
    enable_thinking: bool = True,
):
    """Run all questions for a single persona and queue SSE events."""
    try:
        persona = await _get_persona(persona_id)
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
                async for kind, chunk in stream_survey_answer(persona, system_prompt, question, q_idx, enable_thinking=enable_thinking):
                    if kind == 'think':
                        full_thinking = chunk
                        await event_queue.put({
                            "event": "persona_thinking",
                            "data": {"persona_uuid": persona_id, "question_index": q_idx, "thinking": chunk}
                        })
                    else:
                        full_answer += sanitize_answer_text(chunk)
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

            full_answer = sanitize_answer_text(full_answer)
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

            if e2e_scenario == "survey_fail_mid_run" and persona_index == 0 and q_idx == 0:
                await event_queue.put({
                    "event": "persona_error",
                    "data": {
                        "persona_uuid": persona_id,
                        "question_index": q_idx,
                        "error": "E2E forced survey interruption",
                    },
                })
                raise RuntimeError("E2E forced survey interruption after partial output")

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


async def _survey_stream(
    request: SurveyRunRequest,
    e2e_scenario: str | None = None,
) -> AsyncGenerator[str, None]:
    run_id = str(uuid.uuid4())
    persona_ids = request.persona_ids
    total = len(persona_ids)

    async with aiosqlite.connect(settings.history_db_path) as history_db:
        # Resolve questions
        questions = request.questions or []
        enable_thinking = request.enable_thinking if request.enable_thinking is not None else True
        if not questions:
            questions = await generate_questions(request.survey_theme, enable_thinking=enable_thinking)
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
        tasks = []

        async def run_with_sem(pid, idx):
            async with semaphore:
                await _run_persona_survey(
                    pid, idx, total, questions, run_id,
                    request.survey_theme, event_queue, history_db, e2e_scenario,
                    enable_thinking=enable_thinking,
                )

        try:
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

            yield f"event: survey_complete\ndata: {json.dumps({'run_id': run_id, 'completed': completed, 'failed': failed}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Survey stream error for run %s: %s", run_id, e)
            yield f"event: survey_error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # Cancel any still-running tasks
            for t in tasks:
                if not t.done():
                    t.cancel()
            # Always mark run as completed (or failed) so it doesn't stay "running" forever
            try:
                final_status = 'completed' if completed > 0 else 'failed'
                await history_db.execute(
                    "UPDATE survey_runs SET status = ? WHERE id = ?",
                    [final_status, run_id]
                )
                await history_db.commit()
            except Exception as e:
                logger.error("Failed to update run status for %s: %s", run_id, e)


@router.post("/questions", response_model=QuestionGenerationResponse)
async def create_questions(request: QuestionGenerationRequest):
    """Generate survey questions without creating a run record."""
    questions = await generate_questions(request.survey_theme, enable_thinking=request.enable_thinking if request.enable_thinking is not None else True)
    return QuestionGenerationResponse(questions=questions)


@router.post("/run")
async def run_survey(request: SurveyRunRequest, http_request: Request):
    """Run a survey across personas with SSE streaming."""
    e2e_scenario = get_e2e_scenario(http_request)
    return StreamingResponse(
        _survey_stream(request, e2e_scenario),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )
