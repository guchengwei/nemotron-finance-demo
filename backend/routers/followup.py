"""Follow-up chat endpoint with SSE streaming."""

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import aiosqlite

from config import settings
from models import FollowUpRequest
from llm import stream_followup_answer
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
        chat_history = [{"role": r["role"], "content": r["content"]} for r in chat_rows]

        # Get financial extension from persona data
        fin_ext = None
        if persona.get("financial_literacy"):
            fin_ext = {
                "financial_literacy": persona.get("financial_literacy"),
                "investment_experience": persona.get("investment_experience"),
                "financial_concerns": persona.get("financial_concerns"),
                "annual_income_bracket": persona.get("annual_income_bracket"),
                "asset_bracket": persona.get("asset_bracket"),
                "primary_bank_type": persona.get("primary_bank_type"),
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

        try:
            async for kind, chunk in stream_followup_answer(system_prompt, messages):
                if kind == 'think':
                    data = json.dumps({"thinking": chunk}, ensure_ascii=False)
                    yield f"event: thinking\ndata: {data}\n\n"
                else:
                    full_answer += chunk
                    data = json.dumps({"text": chunk}, ensure_ascii=False)
                    yield f"event: token\ndata: {data}\n\n"
        except Exception as e:
            logger.error("Followup LLM error for %s: %s", request.persona_uuid, e)
            err_data = json.dumps({"error": str(e)}, ensure_ascii=False)
            yield f"event: error\ndata: {err_data}\n\n"
            full_answer = "（回答を取得できませんでした）"

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
