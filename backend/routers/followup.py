"""Follow-up chat endpoint with SSE streaming."""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import aiosqlite

from config import settings
from models import (
    FollowUpClearRequest,
    FollowUpClearResponse,
    FollowUpRequest,
    FollowUpSuggestionRequest,
    FollowUpSuggestionResponse,
)
from llm import generate_followup_suggestions, sanitize_answer_text, stream_followup_answer
from prompts import build_followup_system_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/followup", tags=["followup"])


async def _followup_stream(request: FollowUpRequest):
    async with aiosqlite.connect(settings.history_db_path) as history_db:
        history_db.row_factory = aiosqlite.Row

        # Load run
        run_rows = await history_db.execute_fetchall(
            "SELECT * FROM survey_runs WHERE id = ?", [request.run_id]
        )
        if not run_rows:
            raise HTTPException(status_code=404, detail="Run not found")
        run = dict(run_rows[0])

        # Load persona answers for this run
        answer_rows = await history_db.execute_fetchall(
            "SELECT * FROM survey_answers WHERE run_id = ? AND persona_uuid = ? "
            "ORDER BY question_index",
            [request.run_id, request.persona_uuid]
        )
        answers = [dict(r) for r in answer_rows]

        if not answers:
            raise HTTPException(status_code=404, detail="No answers found for this persona in this run")

        # Extract persona data from first answer
        persona_full_json = answers[0].get("persona_full_json") or "{}"
        try:
            persona = json.loads(persona_full_json)
        except Exception:
            persona = {}

        # Load prior chat history
        chat_rows = await history_db.execute_fetchall(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? "
            "ORDER BY created_at",
            [request.run_id, request.persona_uuid]
        )

        # Get financial extension from persona data (may be nested under financial_extension)
        fe = persona.get("financial_extension") or {}
        fin_ext = None
        if persona.get("financial_literacy") or fe.get("financial_literacy"):
            fin_ext = {
                "financial_literacy": persona.get("financial_literacy") or fe.get("financial_literacy"),
                "investment_experience": persona.get("investment_experience") or fe.get("investment_experience"),
                "financial_concerns": persona.get("financial_concerns") or fe.get("financial_concerns"),
                "annual_income_bracket": persona.get("annual_income_bracket") or fe.get("annual_income_bracket"),
                "asset_bracket": persona.get("asset_bracket") or fe.get("asset_bracket"),
                "primary_bank_type": persona.get("primary_bank_type") or fe.get("primary_bank_type"),
            }

        # Build system prompt
        system_prompt = build_followup_system_prompt(
            persona=persona,
            financial_ext=fin_ext,
            survey_theme=run["survey_theme"],
            previous_answers=answers,
        )

        # Save user message to history
        await history_db.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'user', ?)",
            [request.run_id, request.persona_uuid, request.question]
        )
        await history_db.commit()

        # Build messages: raw history (last N) + new question
        messages = [
            {"role": r["role"], "content": r["content"]}
            for r in chat_rows[-settings.followup_max_history_messages:]
        ] + [{"role": "user", "content": request.question}]

        full_answer = ""
        enable_thinking = bool(run.get("enable_thinking", True))
        assistant_fallback = "（回答を取得できませんでした。もう一度お試しください。）"
        interrupted_fallback = "（通信が中断されたため、回答を完了できませんでした）"
        assistant_saved = False
        stream_stopped = False  # True once try-except exits cleanly or via known exception

        async def save_assistant_response() -> None:
            nonlocal assistant_saved, full_answer
            if assistant_saved:
                return
            save_answer = full_answer or assistant_fallback
            async with aiosqlite.connect(settings.history_db_path) as persist_db:
                await persist_db.execute(
                    "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
                    [request.run_id, request.persona_uuid, save_answer]
                )
                await persist_db.commit()
            assistant_saved = True

        try:
            async for kind, chunk in stream_followup_answer(
                system_prompt, messages, enable_thinking=enable_thinking
            ):
                if kind == "think":
                    data = json.dumps({"thinking": chunk}, ensure_ascii=False)
                    yield f"event: thinking\ndata: {data}\n\n"
                else:
                    clean = sanitize_answer_text(chunk)
                    if clean:
                        full_answer += clean
                        data = json.dumps({"text": clean}, ensure_ascii=False)
                        yield f"event: token\ndata: {data}\n\n"

            if not full_answer:
                full_answer = assistant_fallback
            stream_stopped = True
        except asyncio.CancelledError:
            logger.warning("Followup stream cancelled for %s", request.persona_uuid)
            full_answer = interrupted_fallback
            stream_stopped = True
        except Exception as e:
            logger.error("Followup LLM error for %s: %s", request.persona_uuid, e)
            err_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err_data}\n\n"
            full_answer = assistant_fallback
            stream_stopped = True
        finally:
            # GeneratorExit (early aclose) leaves stream_stopped=False
            if not stream_stopped:
                full_answer = interrupted_fallback
            save_task = asyncio.create_task(save_assistant_response())
            try:
                await asyncio.shield(save_task)
            except asyncio.CancelledError:
                await asyncio.shield(save_task)

        done_data = json.dumps({"full_answer": full_answer}, ensure_ascii=False)
        yield f"event: done\ndata: {done_data}\n\n"


@router.post("/ask")
async def ask_followup(request: FollowUpRequest):
    """Ask a follow-up question to a persona from a survey run."""
    return StreamingResponse(
        _followup_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/suggestions", response_model=FollowUpSuggestionResponse)
async def followup_suggestions(request: FollowUpSuggestionRequest):
    async with aiosqlite.connect(settings.history_db_path) as history_db:
        history_db.row_factory = aiosqlite.Row

        run_rows = await history_db.execute_fetchall(
            "SELECT * FROM survey_runs WHERE id = ?", [request.run_id]
        )
        if not run_rows:
            raise HTTPException(status_code=404, detail="Run not found")
        run = dict(run_rows[0])

        answer_rows = await history_db.execute_fetchall(
            "SELECT * FROM survey_answers WHERE run_id = ? AND persona_uuid = ? ORDER BY question_index",
            [request.run_id, request.persona_uuid]
        )
        answers = [dict(r) for r in answer_rows]
        if not answers:
            raise HTTPException(status_code=404, detail="No answers found for this persona in this run")

        # Read all chat rows for this persona
        all_chat_rows = await history_db.execute_fetchall(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY created_at",
            [request.run_id, request.persona_uuid]
        )

    try:
        persona = json.loads(answers[0].get("persona_full_json") or "{}")
    except Exception:
        persona = {}

    # Build chat history for LLM context (last 12 messages)
    chat_history = [
        {"role": r["role"], "content": r["content"]}
        for r in all_chat_rows[-12:]
    ]

    # Dedupe: all user messages asked so far
    asked = {r["content"].strip() for r in all_chat_rows if r["role"] == "user"}

    generated = await generate_followup_suggestions(
        survey_theme=run["survey_theme"],
        persona=persona,
        previous_answers=answers,
        chat_history=chat_history,
        excluded_questions=asked,
    )

    filtered: list[str] = []
    filtered_seen: set[str] = set()
    for question in generated:
        cleaned = str(question).strip()
        if not cleaned:
            continue
        if cleaned in asked or cleaned in filtered_seen:
            continue
        filtered.append(cleaned)
        filtered_seen.add(cleaned)
        if len(filtered) == 3:
            break

    return FollowUpSuggestionResponse(questions=filtered)


@router.post("/clear", response_model=FollowUpClearResponse)
async def clear_followup_history(request: FollowUpClearRequest):
    async with aiosqlite.connect(settings.history_db_path) as history_db:
        cursor = await history_db.execute(
            "DELETE FROM followup_chats WHERE run_id = ? AND persona_uuid = ?",
            [request.run_id, request.persona_uuid],
        )
        await history_db.commit()

    return FollowUpClearResponse(deleted_count=cursor.rowcount or 0)
