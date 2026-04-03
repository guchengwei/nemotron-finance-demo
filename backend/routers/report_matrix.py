"""Matrix report SSE endpoint.

POST /api/report/matrix — streams progressive report events.
GET  /api/report/matrix/{survey_id} — returns persisted report JSON.
"""

import json
import logging
import aiosqlite
from fastapi import APIRouter
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from db import get_history_db
from matrix_pipeline import run_matrix_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report/matrix", tags=["matrix-report"])


class MatrixReportRequest(BaseModel):
    survey_id: str
    preset_key: str = "interest_barrier"


def _extract_full_name(persona_full_json: str | None, persona_summary: str | None, persona_uuid: str) -> str:
    """Extract full name from persona data, with fallbacks."""
    if persona_full_json:
        try:
            pj = json.loads(persona_full_json)
            if isinstance(pj, dict):
                name = pj.get("name", "")
                if name:
                    return name
        except (json.JSONDecodeError, TypeError):
            pass
    if persona_summary:
        return persona_summary.split(",")[0].strip().rstrip(",")
    return persona_uuid[:8]


async def _matrix_stream(request: MatrixReportRequest):
    """Generator that yields SSE-formatted events from the pipeline."""
    import aiosqlite
    db = await get_history_db()
    db.row_factory = aiosqlite.Row
    row = await db.execute(
        "SELECT id, survey_theme, questions_json FROM survey_runs WHERE id = ?",
        [request.survey_id],
    )
    run = await row.fetchone()
    if not run:
        yield f"event: report_error\ndata: {json.dumps({'error': 'Survey run not found'})}\n\n"
        return

    answers_rows = await db.execute(
        "SELECT persona_uuid, persona_summary, persona_full_json, answer, question_index "
        "FROM survey_answers WHERE run_id = ? ORDER BY persona_uuid, question_index",
        [request.survey_id],
    )
    answers = await answers_rows.fetchall()

    persona_map: dict[str, dict] = {}
    for a in answers:
        pid = a["persona_uuid"]
        if pid not in persona_map:
            full_name = _extract_full_name(
                a["persona_full_json"], a["persona_summary"], pid
            )
            persona_map[pid] = {"persona_id": pid, "name": full_name, "industry": "", "age": 0, "qa_parts": []}
        persona_map[pid]["qa_parts"].append(f"Q{a['question_index']+1}: {a['answer']}")

    if persona_map:
        from persona_store import get_store
        store = get_store()
        for pid, pdata in persona_map.items():
            meta = store.get_persona(pid)
            if meta:
                pdata["industry"] = meta.get("occupation", meta.get("industry", ""))
                pdata["age"] = meta.get("age", 0)
            pdata["qa_text"] = "\n".join(pdata.pop("qa_parts"))


    survey_data = {
        "survey_id": request.survey_id,
        "personas": list(persona_map.values()),
    }

    full_report: dict = {}

    async for event_type, event_data in run_matrix_pipeline(
        survey_data=survey_data,
        preset_key=request.preset_key,
    ):
        yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        if event_type == "axis_ready":
            full_report["axes"] = event_data
        elif event_type == "persona_scored":
            full_report.setdefault("personas", []).append(event_data)
        elif event_type == "keywords_ready":
            full_report["keywords"] = event_data
        elif event_type == "keyword_elaborated":
            kw_data = event_data  # {"keyword_text": "...", "elaboration": "..."}
            if "keywords" in full_report:
                for group in ("strengths", "weaknesses"):
                    for kw in full_report["keywords"].get(group, []):
                        if kw["text"] == kw_data["keyword_text"]:
                            kw["elaboration"] = kw_data["elaboration"]
        elif event_type == "recommendations_ready":
            full_report["recommendations"] = event_data
        elif event_type == "report_complete":
            try:
                await db.execute(
                    "UPDATE survey_runs SET matrix_report_json = ? WHERE id = ?",
                    [json.dumps(full_report, ensure_ascii=False), request.survey_id],
                )
                await db.commit()
            except Exception as e:
                logger.error("Failed to persist matrix report: %s", e)


@router.post("")
async def generate_matrix_report(request: MatrixReportRequest):
    return StreamingResponse(
        _matrix_stream(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{survey_id}")
async def get_matrix_report(survey_id: str):
    """Return persisted matrix report JSON for history reload."""
    db = await get_history_db()
    db.row_factory = aiosqlite.Row
    row = await db.execute(
        "SELECT matrix_report_json FROM survey_runs WHERE id = ?", [survey_id]
    )
    result = await row.fetchone()
    if not result or not result["matrix_report_json"]:
        return JSONResponse(status_code=404, content={"error": "No matrix report found"})
    return JSONResponse(content=json.loads(result["matrix_report_json"]))
