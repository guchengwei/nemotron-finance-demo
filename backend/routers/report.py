"""Report generation endpoint."""

import json
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException
import aiosqlite

from config import settings
from models import ReportRequest, ReportResponse, TopPick
from llm import generate_report
from prompts import sex_display

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/report", tags=["report"])

LARGE_SURVEY_THRESHOLD = 50


def _aggregate_scores(answers: list[dict]) -> dict:
    """Python-side aggregation for large surveys."""
    scores = [a["score"] for a in answers if a.get("score") is not None and a["question_index"] == 0]
    distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for s in scores:
        key = str(s)
        if key in distribution:
            distribution[key] += 1

    overall = round(sum(scores) / len(scores), 1) if scores else None

    # Demographic breakdown
    by_age: dict = defaultdict(list)
    by_sex: dict = defaultdict(list)
    by_lit: dict = defaultdict(list)

    seen_personas: dict = {}
    for a in answers:
        if a["question_index"] != 0 or a.get("score") is None:
            continue
        uuid = a["persona_uuid"]
        if uuid in seen_personas:
            continue
        seen_personas[uuid] = True

        # Parse persona JSON for demographic info
        try:
            p = json.loads(a.get("persona_full_json") or "{}")
        except Exception:
            p = {}

        age = p.get("age", 0)
        if age < 40:
            by_age["20-39"].append(a["score"])
        elif age < 60:
            by_age["40-59"].append(a["score"])
        else:
            by_age["60+"].append(a["score"])

        sex_raw = p.get("sex", "")
        by_sex[sex_display(sex_raw)].append(a["score"])

        lit = p.get("financial_literacy") or (
            json.loads(a.get("persona_full_json") or "{}").get("financial_literacy")
        )
        if lit:
            by_lit[lit].append(a["score"])

    def avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0.0

    return {
        "overall_score": overall,
        "score_distribution": distribution,
        "demographic_breakdown": {
            "by_age": {k: avg(v) for k, v in by_age.items()},
            "by_sex": {k: avg(v) for k, v in by_sex.items()},
            "by_financial_literacy": {k: avg(v) for k, v in by_lit.items()},
        }
    }


def _build_answers_summary(answers: list[dict], questions: list[str], max_answers: int = 20) -> str:
    """Build a condensed summary for the LLM report prompt."""
    # Group answers by persona
    persona_answers: dict = defaultdict(list)
    for a in answers:
        persona_answers[a["persona_uuid"]].append(a)

    # Score per persona (first question)
    persona_scores = {}
    for uuid, ans_list in persona_answers.items():
        for a in ans_list:
            if a["question_index"] == 0 and a.get("score") is not None:
                persona_scores[uuid] = a["score"]

    # Select top N most detailed (by total answer length)
    def total_length(ans_list):
        return sum(len(a.get("answer", "")) for a in ans_list)

    sorted_personas = sorted(persona_answers.keys(), key=lambda u: total_length(persona_answers[u]), reverse=True)
    selected = sorted_personas[:max_answers]

    lines = []
    for uuid in selected:
        try:
            p = json.loads((persona_answers[uuid][0] or {}).get("persona_full_json") or "{}")
        except Exception:
            p = {}
        summary = persona_answers[uuid][0].get("persona_summary", uuid[:8])
        score = persona_scores.get(uuid, "N/A")
        lines.append(f"\n--- {summary} (評価: {score}) ---")
        for a in sorted(persona_answers[uuid], key=lambda x: x["question_index"]):
            q_text = questions[a["question_index"]] if a["question_index"] < len(questions) else f"Q{a['question_index']+1}"
            lines.append(f"Q: {q_text}")
            lines.append(f"A: {a.get('answer', '')[:200]}")

    return "\n".join(lines)


@router.post("/generate", response_model=ReportResponse)
async def generate_report_endpoint(request: ReportRequest):
    """Generate a report from a completed survey run."""
    async with aiosqlite.connect(settings.history_db_path) as db:
        db.row_factory = aiosqlite.Row

        # Load run
        run_rows = await db.execute_fetchall(
            "SELECT * FROM survey_runs WHERE id = ?", [request.run_id]
        )
        if not run_rows:
            raise HTTPException(status_code=404, detail="Run not found")
        run = dict(run_rows[0])

        # Return cached report if available
        if run.get("report_json"):
            try:
                cached = json.loads(run["report_json"])
                cached["run_id"] = request.run_id
                return ReportResponse(**cached)
            except Exception:
                pass

        # Load answers
        answer_rows = await db.execute_fetchall(
            "SELECT * FROM survey_answers WHERE run_id = ? ORDER BY persona_uuid, question_index",
            [request.run_id]
        )
        answers = [dict(r) for r in answer_rows]

        if not answers:
            raise HTTPException(status_code=400, detail="No answers found for this run")

        questions = json.loads(run["questions_json"])
        persona_count = len(set(a["persona_uuid"] for a in answers))
        large_survey = persona_count >= LARGE_SURVEY_THRESHOLD

        # Aggregate scores in Python
        aggregated = _aggregate_scores(answers)

        if large_survey:
            # 2-pass: Python aggregation + LLM qualitative on subset
            answers_summary = _build_answers_summary(answers, questions, max_answers=20)
        else:
            answers_summary = _build_answers_summary(answers, questions, max_answers=len(answers))

        # LLM for qualitative parts
        llm_result = await generate_report(
            survey_theme=run["survey_theme"],
            persona_count=persona_count,
            questions=questions,
            answers_summary=answers_summary,
        )

        # Merge Python aggregation (authoritative) with LLM qualitative
        report_data = {
            "run_id": request.run_id,
            "overall_score": aggregated["overall_score"] or llm_result.get("overall_score"),
            "score_distribution": aggregated["score_distribution"],
            "group_tendency": llm_result.get("group_tendency"),
            "conclusion": llm_result.get("conclusion"),
            "top_picks": llm_result.get("top_picks", []),
            "demographic_breakdown": aggregated["demographic_breakdown"] or llm_result.get("demographic_breakdown"),
        }

        # Validate and patch top_picks
        valid_uuids = {a["persona_uuid"] for a in answers}
        top_picks = []
        for tp in report_data.get("top_picks") or []:
            if isinstance(tp, dict):
                # Accept even if uuid doesn't match (LLM may fabricate in mock)
                top_picks.append(TopPick(
                    persona_uuid=tp.get("persona_uuid", ""),
                    persona_name=tp.get("persona_name", ""),
                    persona_summary=tp.get("persona_summary", ""),
                    highlight_reason=tp.get("highlight_reason", ""),
                    highlight_quote=tp.get("highlight_quote", ""),
                ))

        report_data["top_picks"] = top_picks

        # Save to DB
        save_data = {k: v for k, v in report_data.items() if k != "run_id"}
        # Convert top_picks to serializable
        save_data["top_picks"] = [tp.model_dump() for tp in top_picks]
        await db.execute(
            "UPDATE survey_runs SET report_json = ? WHERE id = ?",
            [json.dumps(save_data, ensure_ascii=False, default=str), request.run_id]
        )
        await db.commit()

        return ReportResponse(**report_data)
