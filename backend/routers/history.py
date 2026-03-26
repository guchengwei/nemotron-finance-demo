"""History CRUD endpoints."""

import json
import logging

from fastapi import APIRouter, HTTPException
import aiosqlite

from config import settings
from llm import sanitize_answer_text
from models import HistoryListResponse, SurveyRunSummary, SurveyRunDetail, ReportResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryListResponse)
async def list_history():
    """List all saved survey runs, sorted by date desc."""
    async with aiosqlite.connect(settings.history_db_path) as db:
        db.row_factory = aiosqlite.Row
        rows = await db.execute_fetchall(
            "SELECT id, created_at, label, survey_theme, persona_count, status, report_json "
            "FROM survey_runs ORDER BY created_at DESC"
        )

    runs = []
    for row in rows:
        r = dict(row)
        overall_score = None
        if r.get("report_json"):
            try:
                report = json.loads(r["report_json"])
                overall_score = report.get("overall_score")
            except Exception:
                pass
        runs.append(SurveyRunSummary(
            id=r["id"],
            created_at=r["created_at"],
            label=r.get("label"),
            survey_theme=r["survey_theme"],
            persona_count=r.get("persona_count") or 0,
            status=r.get("status") or "unknown",
            overall_score=overall_score,
        ))

    return HistoryListResponse(runs=runs)


@router.get("/{run_id}", response_model=SurveyRunDetail)
async def get_history_run(run_id: str):
    """Get full run data including answers, report, and follow-up chats."""
    async with aiosqlite.connect(settings.history_db_path) as db:
        db.row_factory = aiosqlite.Row

        run_rows = await db.execute_fetchall(
            "SELECT * FROM survey_runs WHERE id = ?", [run_id]
        )
        if not run_rows:
            raise HTTPException(status_code=404, detail="Run not found")
        run = dict(run_rows[0])

        answer_rows = await db.execute_fetchall(
            "SELECT * FROM survey_answers WHERE run_id = ? ORDER BY persona_uuid, question_index",
            [run_id]
        )
        answers = [dict(r) for r in answer_rows]

        chat_rows = await db.execute_fetchall(
            "SELECT persona_uuid, role, content, created_at FROM followup_chats "
            "WHERE run_id = ? ORDER BY created_at",
            [run_id]
        )

    # Group chats by persona while preserving the stored sequence for display.
    followup_chats: dict = {}
    for row in chat_rows:
        r = dict(row)
        pid = r["persona_uuid"]
        content = sanitize_answer_text(r["content"]) or r["content"]
        if pid not in followup_chats:
            followup_chats[pid] = []
        followup_chats[pid].append({"role": r["role"], "content": content})

    report = None
    if run.get("report_json"):
        try:
            report_data = json.loads(run["report_json"])
            report_data["run_id"] = run_id
            report = ReportResponse(**report_data)
        except Exception:
            pass

    questions = []
    if run.get("questions_json"):
        try:
            questions = json.loads(run["questions_json"])
        except Exception:
            pass

    filter_config = None
    if run.get("filter_config_json"):
        try:
            filter_config = json.loads(run["filter_config_json"])
        except Exception:
            pass

    return SurveyRunDetail(
        id=run["id"],
        created_at=run["created_at"],
        label=run.get("label"),
        survey_theme=run["survey_theme"],
        questions=questions,
        filter_config=filter_config,
        persona_count=run.get("persona_count") or 0,
        status=run.get("status") or "unknown",
        report=report,
        answers=answers,
        followup_chats=followup_chats,
        enable_thinking=bool(run.get("enable_thinking", True)),
    )


@router.delete("/{run_id}")
async def delete_history_run(run_id: str):
    """Delete a run and all associated data."""
    async with aiosqlite.connect(settings.history_db_path) as db:
        row = await db.execute_fetchall("SELECT id FROM survey_runs WHERE id = ?", [run_id])
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")

        await db.execute("DELETE FROM followup_chats WHERE run_id = ?", [run_id])
        await db.execute("DELETE FROM survey_answers WHERE run_id = ?", [run_id])
        await db.execute("DELETE FROM survey_runs WHERE id = ?", [run_id])
        await db.commit()

    return {"status": "deleted", "run_id": run_id}
