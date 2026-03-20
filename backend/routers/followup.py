"""Follow-up chat endpoint with SSE streaming."""

import asyncio
import json
import logging
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import aiosqlite

from config import settings
from models import FollowUpRequest, FollowUpSuggestionRequest, FollowUpSuggestionResponse
from llm import generate_followup_suggestions, sanitize_answer_text, stream_followup_answer
from prompts import build_followup_system_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/followup", tags=["followup"])

_ASSISTANT_ROLE_PREFIX_RE = re.compile(
    r"(?is)^assistant(?:\s*[:：]\s*|\s*\r?\n\s*|$)"
)


def _strip_leading_assistant_label(text: str) -> str:
    stripped = text.lstrip()
    match = _ASSISTANT_ROLE_PREFIX_RE.match(stripped)
    if not match:
        return text
    return stripped[match.end():].lstrip()


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
        chat_history = [{"role": r["role"], "content": r["content"]} for r in chat_rows]

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

        # Stream response
        messages = chat_history + [{"role": "user", "content": request.question}]
        full_answer = ""
        enable_thinking = bool(run.get("enable_thinking", True))
        assistant_fallback = "（回答を取得できませんでした。もう一度お試しください。）"

        try:
            pending_thinking: list[str] = []
            emitted = False

            async for kind, chunk in stream_followup_answer(
                system_prompt,
                messages,
                enable_thinking=enable_thinking,
            ):
                if kind == 'think':
                    if emitted:
                        data = json.dumps({"thinking": chunk}, ensure_ascii=False)
                        yield f"event: thinking\ndata: {data}\n\n"
                    else:
                        pending_thinking.append(chunk)
                    continue

                clean_chunk = sanitize_answer_text(chunk)
                if not emitted:
                    clean_chunk = _strip_leading_assistant_label(clean_chunk)
                    if not clean_chunk:
                        continue
                    emitted = True
                    for thinking_chunk in pending_thinking:
                        data = json.dumps({"thinking": thinking_chunk}, ensure_ascii=False)
                        yield f"event: thinking\ndata: {data}\n\n"

                full_answer += clean_chunk
                data = json.dumps({"text": clean_chunk}, ensure_ascii=False)
                yield f"event: token\ndata: {data}\n\n"

            if not full_answer:
                full_answer = assistant_fallback
        except asyncio.CancelledError:
            logger.warning("Followup stream cancelled for %s", request.persona_uuid)
            full_answer = "（通信が中断されたため、回答を完了できませんでした）"
        except Exception as e:
            logger.error("Followup LLM error for %s: %s", request.persona_uuid, e)
            err_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err_data}\n\n"
            full_answer = assistant_fallback

        full_answer = sanitize_answer_text(full_answer) or assistant_fallback

        # Save assistant response
        await history_db.execute(
            "INSERT INTO followup_chats (run_id, persona_uuid, role, content) VALUES (?, ?, 'assistant', ?)",
            [request.run_id, request.persona_uuid, full_answer]
        )
        await history_db.commit()

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

        chat_rows = await history_db.execute_fetchall(
            "SELECT role, content FROM followup_chats WHERE run_id = ? AND persona_uuid = ? ORDER BY created_at",
            [request.run_id, request.persona_uuid]
        )
        chat_history = [{"role": r["role"], "content": r["content"]} for r in chat_rows]

    try:
        persona = json.loads(answers[0].get("persona_full_json") or "{}")
    except Exception:
        persona = {}

    asked = {
        str(msg.get("content") or "").strip()
        for msg in chat_history
        if msg.get("role") == "user"
    }
    generated = await generate_followup_suggestions(
        survey_theme=run["survey_theme"],
        persona=persona,
        previous_answers=answers,
        chat_history=chat_history,
    )

    filtered: list[str] = []
    for question in generated:
        cleaned = str(question).strip()
        if not cleaned or cleaned in asked or cleaned in filtered:
            continue
        filtered.append(cleaned)
        if len(filtered) == 3:
            break

    return FollowUpSuggestionResponse(questions=filtered)
