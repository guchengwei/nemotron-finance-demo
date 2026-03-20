"""Report generation endpoint."""

import json
import logging
from collections import defaultdict
import re

from fastapi import APIRouter, HTTPException
import aiosqlite

from config import settings
from models import ReportRequest, ReportResponse, TopPick
import llm
import text_analysis
from prompts import sex_display

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/report", tags=["report"])

LARGE_SURVEY_THRESHOLD = 50
TOP_PICK_LIMIT = 3


def _load_persona_json(answer: dict) -> dict:
    try:
        return json.loads(answer.get("persona_full_json") or "{}")
    except Exception:
        return {}


def _strip_score_prefix(text: str) -> str:
    return re.sub(r"^【評価:\s*\d\s*】", "", text or "").strip()


def _clip_text(text: str, max_len: int = 50) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _first_sentence(text: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    for sep in ("。", "！", "!", "？", "?", "\n"):
        idx = cleaned.find(sep)
        if idx != -1:
            return cleaned[: idx + 1].strip()
    return _clip_text(cleaned, max_len)


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", cleaned) if part.strip()]
    return sentences


def _split_action_clauses(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = cleaned.rstrip("。！？!?")
    if not cleaned:
        return []
    clauses = []
    for part in re.split(r"[、,]", cleaned):
        clause = part.strip()
        if clause:
            clauses.append(clause)
    return clauses


def _persona_name(persona_data: dict, answer: dict) -> str:
    return persona_data.get("name") or answer.get("persona_summary", "不明").split()[0]


def _persona_summary(persona_data: dict, answer: dict) -> str:
    if answer.get("persona_summary"):
        return answer["persona_summary"]
    age = persona_data.get("age")
    sex = sex_display(persona_data.get("sex", ""))
    occupation = persona_data.get("occupation", "")
    prefecture = persona_data.get("prefecture", "")
    parts = [str(age) + "歳" if age else "", sex, occupation, prefecture]
    return "、".join(part for part in parts if part) or answer.get("persona_uuid", "不明")


def _build_persona_records(answers: list[dict]) -> dict[str, dict]:
    records: dict[str, dict] = {}
    for answer in answers:
        uuid = answer["persona_uuid"]
        record = records.setdefault(
            uuid,
            {
                "persona_uuid": uuid,
                "answers": [],
                "score": None,
            },
        )
        persona_data = _load_persona_json(answer)
        if persona_data:
            record["persona_data"] = persona_data
        record["answers"].append(answer)
        if answer.get("score") is not None:
            record.setdefault("_scores", []).append(answer["score"])
        record["persona_name"] = _persona_name(record.get("persona_data", {}), answer)
        record["persona_summary"] = _persona_summary(record.get("persona_data", {}), answer)

    for record in records.values():
        record["answers"].sort(key=lambda item: item["question_index"])
        scores = record.pop("_scores", [])
        if scores:
            record["score"] = round(sum(scores) / len(scores), 1)
    return records


def _first_answer_excerpt(record: dict) -> str:
    for answer in record.get("answers", []):
        if answer["question_index"] == 0:
            return _clip_text(_strip_score_prefix(answer.get("answer", "")), 50)
    for answer in record.get("answers", []):
        cleaned = _clip_text(_strip_score_prefix(answer.get("answer", "")), 50)
        if cleaned:
            return cleaned
    return ""


def _strong_answer_excerpts(record: dict, max_items: int = 2) -> list[str]:
    ranked = sorted(
        (
            _strip_score_prefix(answer.get("answer", ""))
            for answer in record.get("answers", [])
            if answer.get("answer")
        ),
        key=len,
        reverse=True,
    )
    excerpts = []
    seen = set()
    for answer in ranked:
        clipped = _clip_text(answer, 70)
        if clipped and clipped not in seen:
            seen.add(clipped)
            excerpts.append(clipped)
        if len(excerpts) >= max_items:
            break
    return excerpts


def _build_candidate_personas_block(persona_records: dict[str, dict], max_personas: int = 20) -> str:
    selected = sorted(
        persona_records.values(),
        key=lambda record: (
            record.get("score") is None,
            -(record.get("score") or 0),
            -sum(len(a.get("answer", "")) for a in record.get("answers", [])),
        ),
    )[:max_personas]

    blocks = []
    for record in selected:
        excerpts = _strong_answer_excerpts(record)
        excerpts_text = "\n".join(f"- 抜粋: {excerpt}" for excerpt in excerpts) or "- 抜粋: なし"
        blocks.append(
            "\n".join(
                [
                    f"persona_uuid: {record['persona_uuid']}",
                    f"summary: {record['persona_summary']}",
                    f"score: {record.get('score', 'N/A')}",
                    excerpts_text,
                ]
            )
        )
    return "\n\n".join(blocks)


def _extract_answer_themes(answers: list[dict]) -> list[str]:
    """Extract top keyword themes from answers using data-driven tokenization."""
    texts = [_strip_score_prefix(a.get("answer", "")) for a in answers]
    return text_analysis.extract_themes(texts)


def _pick_representative_excerpts(answers: list[dict], n: int = 5) -> list[str]:
    """Pick representative answer excerpts — stratified by score if Q1."""
    scored = [(a.get("score"), a) for a in answers if a.get("answer")]
    has_scores = any(s is not None for s, _ in scored)
    if has_scores:
        buckets: dict = {1: [], 2: [], 3: [], 4: [], 5: []}
        for s, a in scored:
            if s in buckets:
                buckets[s].append(a)
        selected = []
        for score in [5, 1, 3, 4, 2]:
            if buckets.get(score):
                selected.append(buckets[score][0])
            if len(selected) >= n:
                break
    else:
        selected = [a for _, a in scored[:n]]
    excerpts = []
    for a in selected:
        text = _clip_text(_strip_score_prefix(a.get("answer", "")), 80)
        if text:
            excerpts.append(text)
    return excerpts


def _build_question_aggregation(answers: list[dict], questions: list[str]) -> str:
    """Aggregate ALL answers per question into stats + themes. Scales to any survey size."""
    q_answers: dict[int, list] = defaultdict(list)
    for a in answers:
        q_answers[a["question_index"]].append(a)

    lines = []
    for q_idx, question in enumerate(questions):
        q_list = q_answers.get(q_idx, [])
        lines.append(f"Q{q_idx+1}: {question}")
        lines.append(f"  回答数: {len(q_list)}")

        scores = [a["score"] for a in q_list if a.get("score") is not None]
        if scores:
                dist = {str(i): scores.count(i) for i in range(1, 6)}
                avg = round(sum(scores) / len(scores), 1)
                lines.append(f"  平均スコア: {avg}, 分布: {dist}")

        themes = _extract_answer_themes(q_list)
        if themes:
            lines.append(f"  主要テーマ: {', '.join(themes[:5])}")

        representative = _pick_representative_excerpts(q_list, n=4)
        for excerpt in representative:
            lines.append(f"  - {excerpt}")

    return "\n".join(lines)


def _build_top_pick_candidates(persona_records: dict[str, dict], questions: list[str], token_polarities: dict[str, float], all_persona_lemmas: dict[str, int], max_candidates: int = 10) -> str:
    """Pre-select diverse candidates using Python scoring; give LLM full Q&A."""
    all_records = list(persona_records.values())
    if not all_records:
        return ""

    scored = []
    for record in all_records:
        scored.append({
            "uuid": record["persona_uuid"],
            "record": record,
            "sentiment": _record_sentiment_score(record, token_polarities),
            "concern": _record_concern_score(record, token_polarities),
            "uniqueness": _record_uniqueness_score(record, all_persona_lemmas),
        })

    candidates: list[str] = []
    for axis in ["sentiment", "concern", "uniqueness"]:
        top = sorted(scored, key=lambda x: x[axis], reverse=True)
        for item in top:
            if item["uuid"] not in candidates:
                candidates.append(item["uuid"])
            if len(candidates) >= max_candidates:
                break

    blocks = []
    for uuid in candidates:
        record = persona_records[uuid]
        block = [
            f"persona_uuid: {uuid}",
            f"summary: {record['persona_summary']}",
            f"score: {record.get('score', 'N/A')}",
        ]
        for ans in record.get("answers", []):
            q_text = questions[ans["question_index"]] if ans["question_index"] < len(questions) else f"Q{ans['question_index']+1}"
            answer_text = _strip_score_prefix(ans.get("answer", ""))[:200]
            block.append(f"Q: {q_text}")
            block.append(f"A: {answer_text}")
        blocks.append("\n".join(block))

    return "\n\n".join(blocks)


def _aggregate_scores(answers: list[dict]) -> dict:
    """Python-side aggregation using per-persona averaged scores across all questions."""
    # Step 1: Collect all scores per persona
    persona_scores: dict[str, list[int]] = defaultdict(list)
    persona_data_cache: dict[str, dict] = {}
    for a in answers:
        if a.get("score") is not None:
            uuid = a["persona_uuid"]
            persona_scores[uuid].append(a["score"])
            if uuid not in persona_data_cache:
                try:
                    persona_data_cache[uuid] = json.loads(a.get("persona_full_json") or "{}")
                except Exception:
                    persona_data_cache[uuid] = {}

    # Step 2: Compute per-persona averages
    persona_avgs: dict[str, float] = {}
    for uuid, scores_list in persona_scores.items():
        persona_avgs[uuid] = round(sum(scores_list) / len(scores_list), 1)

    # Step 3: Build score distribution from raw scored answers.
    all_avg_scores = list(persona_avgs.values())
    distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    for a in answers:
        score = a.get("score")
        if score is None:
            continue
        key = str(score)
        if key in distribution:
            distribution[key] += 1

    overall = round(sum(all_avg_scores) / len(all_avg_scores), 1) if all_avg_scores else None

    # Step 4: Demographics using per-persona averages
    by_age: dict = defaultdict(list)
    by_sex: dict = defaultdict(list)
    by_lit: dict = defaultdict(list)

    for uuid, avg_score in persona_avgs.items():
        p = persona_data_cache.get(uuid, {})

        age = p.get("age", 0)
        if age < 40:
            by_age["20-39"].append(avg_score)
        elif age < 60:
            by_age["40-59"].append(avg_score)
        else:
            by_age["60+"].append(avg_score)

        sex_raw = p.get("sex", "")
        by_sex[sex_display(sex_raw)].append(avg_score)

        fe = p.get("financial_extension") or {}
        lit = p.get("financial_literacy") or fe.get("financial_literacy")
        if lit:
            by_lit[lit].append(avg_score)

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


def _describe_score_level(overall_score: float | None) -> str:
    if overall_score is None:
        return "評価はまだ割れています"
    if overall_score >= 4.2:
        return "全体としてかなり前向きです"
    if overall_score >= 3.5:
        return "全体として前向き寄りです"
    if overall_score >= 2.8:
        return "全体として慎重な様子が目立ちます"
    return "全体として否定的な見方が強めです"


def _top_demographic_signal(demographic_breakdown: dict) -> str:
    signals = []
    for label, values in demographic_breakdown.items():
        if not isinstance(values, dict) or not values:
            continue
        best_group = max(values.items(), key=lambda item: item[1])
        signals.append((best_group[1], label, best_group[0]))
    if not signals:
        return ""
    _, label, group = max(signals, key=lambda item: item[0])
    labels = {
        "by_age": "年齢層",
        "by_sex": "性別",
        "by_financial_literacy": "金融リテラシー",
    }
    return f"{labels.get(label, label)}では{group}の反応が比較的強めです。"


def _extract_motifs(answers: list[dict]) -> tuple[str, str]:
    """Extract positive/negative motifs using learned token polarities."""
    texts = [_strip_score_prefix(a.get("answer", "")) for a in answers]
    scores: list[int | None] = [a.get("score") for a in answers]
    return text_analysis.extract_motifs(texts, scores)


def build_fallback_group_tendency(
    overall_score: float | None,
    score_distribution: dict[str, int],
    demographic_breakdown: dict,
) -> str:
    positive = score_distribution.get("4", 0) + score_distribution.get("5", 0)
    negative = score_distribution.get("1", 0) + score_distribution.get("2", 0)
    balance = "前向きな声がやや優勢" if positive >= negative else "慎重な声がやや優勢"
    demo_signal = _top_demographic_signal(demographic_breakdown)
    return f"{_describe_score_level(overall_score)}。{balance}で、評価3を含む様子見層も一定数います。{demo_signal}".strip()


def build_fallback_conclusion_summary(overall_score: float | None, answers: list[dict]) -> str:
    positive_motif, negative_motif = _extract_motifs(answers)
    if overall_score is None:
        lead = "評価はまだ十分に定まっていません"
    elif overall_score >= 3.5:
        lead = "全体としては前向きな反応が中心です"
    elif overall_score >= 2.8:
        lead = "全体としては賛否が分かれています"
    else:
        lead = "全体としては慎重な反応が目立ちます"
    return f"{lead}。{positive_motif}は追い風ですが、{negative_motif}への対応が導入判断の鍵です。"


def build_fallback_recommended_actions(
    overall_score: float | None,
    score_distribution: dict[str, int],
    answers: list[dict],
) -> list[str]:
    positive_motif, negative_motif = _extract_motifs(answers)
    positive_count = score_distribution.get("4", 0) + score_distribution.get("5", 0)
    negative_count = score_distribution.get("1", 0) + score_distribution.get("2", 0)

    actions = [
        (
            f"{negative_motif}に対する説明を先に整え、"
            f"不安要因を短時間で解消できる導線を用意する"
            if (overall_score or 0) < 3.5
            else f"{positive_motif}を訴求軸にして、利用イメージを具体化する"
        ),
        "料金、手数料、セキュリティの比較情報を一枚で見せる",
        (
            "初心者向けのサポートと問い合わせ導線を強化する"
            if negative_count >= positive_count
            else "高評価層向けの試用・段階導入プランを提示する"
        ),
    ]

    unique_actions: list[str] = []
    for action in actions:
        cleaned = action.strip()
        if cleaned and cleaned not in unique_actions:
            unique_actions.append(cleaned)

    while len(unique_actions) < 3:
        fallback = [
            "導入前の説明資料を簡潔に整備する",
            "想定質問への回答例を用意する",
            "利用開始までの手順を明確にする",
        ][len(unique_actions)]
        if fallback not in unique_actions:
            unique_actions.append(fallback)

    return unique_actions[:3]


def _pad_recommended_actions(actions: list[str], overall_score: float | None, score_distribution: dict[str, int], answers: list[dict]) -> list[str]:
    unique_actions: list[str] = []
    for action in actions:
        cleaned = action.strip()
        if cleaned and cleaned not in unique_actions:
            unique_actions.append(cleaned)

    if len(unique_actions) >= 3:
        return unique_actions[:3]

    fallback_actions = build_fallback_recommended_actions(overall_score, score_distribution, answers)
    for action in fallback_actions:
        if len(unique_actions) >= 3:
            break
        if action not in unique_actions:
            unique_actions.append(action)

    return unique_actions[:3]


def _extract_recommended_actions_from_conclusion(conclusion_raw: str) -> list[str]:
    sentences = _split_sentences(conclusion_raw)
    if len(sentences) > 1:
        tail = sentences[1:]
        if len(tail) == 1:
            clauses = _split_action_clauses(tail[0])
            if len(clauses) > 1:
                return clauses[:3]
        return tail[:3]

    if not sentences:
        return []

    clauses = _split_action_clauses(sentences[0])
    if len(clauses) > 1:
        return clauses[:3]

    return []


def synthesize_conclusion(conclusion_summary: str, recommended_actions: list[str]) -> str:
    summary = (conclusion_summary or "").strip()
    actions = [action.strip() for action in recommended_actions if action.strip()]
    parts = []
    if summary:
        parts.append(summary.rstrip("。"))
    if actions:
        parts.append("推奨アクションは、" + "。".join(actions) + "。")
    return "。".join(parts).strip("。") + ("。" if parts else "")


def build_conclusion_fields(
    overall_score: float | None,
    score_distribution: dict[str, int],
    answers: list[dict],
    conclusion_raw: str,
) -> tuple[str, list[str], str]:
    conclusion_summary = _first_sentence(conclusion_raw)
    if not conclusion_summary:
        conclusion_summary = build_fallback_conclusion_summary(overall_score, answers)

    recommended_actions = _pad_recommended_actions(
        _extract_recommended_actions_from_conclusion(conclusion_raw),
        overall_score,
        score_distribution,
        answers,
    )
    conclusion = conclusion_raw.strip() if conclusion_raw and conclusion_raw.strip() else synthesize_conclusion(
        conclusion_summary,
        recommended_actions,
    )
    return conclusion_summary, recommended_actions, conclusion


def _record_sentiment_score(record: dict, token_polarities: dict[str, float]) -> int:
    texts = [_strip_score_prefix(a.get("answer", "")) for a in record.get("answers", [])]
    score = record.get("score") or 0
    return score * 10 + text_analysis.sentiment_score(texts, token_polarities)


def _record_concern_score(record: dict, token_polarities: dict[str, float]) -> int:
    texts = [_strip_score_prefix(a.get("answer", "")) for a in record.get("answers", [])]
    score = record.get("score") or 0
    return text_analysis.concern_score(texts, token_polarities) * 10 - score


def _record_uniqueness_score(record: dict, all_persona_lemmas: dict[str, int]) -> int:
    texts = [_strip_score_prefix(a.get("answer", "")) for a in record.get("answers", [])]
    return text_analysis.uniqueness_score(texts, all_persona_lemmas)


def _fallback_pick_from_record(record: dict, reason: str) -> dict:
    return {
        "persona_uuid": record["persona_uuid"],
        "persona_name": record["persona_name"],
        "persona_summary": record["persona_summary"],
        "highlight_reason": reason,
        "highlight_quote": _first_answer_excerpt(record),
    }


def build_fallback_top_picks(persona_records: dict[str, dict], token_polarities: dict[str, float], all_persona_lemmas: dict[str, int], exclude_uuids: set[str] | None = None) -> list[dict]:
    exclude_uuids = exclude_uuids or set()
    available = [record for record in persona_records.values() if record["persona_uuid"] not in exclude_uuids]
    if not available:
        return []

    picks: list[dict] = []
    used = set(exclude_uuids)

    def select_best(records: list[dict], scorer, reason: str) -> None:
        remaining = [record for record in records if record["persona_uuid"] not in used]
        if not remaining:
            return
        best = max(remaining, key=scorer)
        used.add(best["persona_uuid"])
        picks.append(_fallback_pick_from_record(best, reason))

    select_best(
        sorted(available, key=lambda record: (record.get("score") or 0, _record_sentiment_score(record, token_polarities)), reverse=True),
        lambda r: _record_sentiment_score(r, token_polarities),
        "前向きな受容理由が具体的で、全体訴求の核を示しているため",
    )
    select_best(
        sorted(available, key=lambda record: (_record_concern_score(record, token_polarities), -(record.get("score") or 0)), reverse=True),
        lambda r: _record_concern_score(r, token_polarities),
        "懸念点が明確で、導入障壁の把握に役立つため",
    )
    select_best(
        sorted(available, key=lambda r: _record_uniqueness_score(r, all_persona_lemmas), reverse=True),
        lambda r: _record_uniqueness_score(r, all_persona_lemmas),
        "回答の切り口が比較的独自で、示唆の幅を広げるため",
    )

    while len(picks) < min(TOP_PICK_LIMIT, len(available)):
        select_best(available, lambda r: _record_uniqueness_score(r, all_persona_lemmas), "補完候補として追加")

    return picks


def _repair_top_pick(candidate: dict, persona_records: dict[str, dict]) -> dict | None:
    uuid = candidate.get("persona_uuid")
    if not isinstance(uuid, str) or uuid not in persona_records:
        return None
    record = persona_records[uuid]
    _pname = candidate.get("persona_name")
    _psum = candidate.get("persona_summary")
    _hreason = candidate.get("highlight_reason")
    _hquote = candidate.get("highlight_quote")
    persona_name: str = _pname if isinstance(_pname, str) else ""
    persona_summary: str = _psum if isinstance(_psum, str) else ""
    highlight_reason: str = _hreason if isinstance(_hreason, str) else ""
    highlight_quote: str = _hquote if isinstance(_hquote, str) else ""

    return {
        "persona_uuid": uuid,
        "persona_name": persona_name.strip() or record["persona_name"],
        "persona_summary": persona_summary.strip() or record["persona_summary"],
        "highlight_reason": highlight_reason.strip() or "回答傾向を代表する視点として有用なため",
        "highlight_quote": _clip_text(highlight_quote.strip() or _first_answer_excerpt(record), 50),
    }


def _merge_top_picks(llm_picks: list[dict], persona_records: dict[str, dict], token_polarities: dict[str, float], all_persona_lemmas: dict[str, int]) -> list[dict]:
    merged = []
    seen = set()
    for candidate in llm_picks:
        repaired = _repair_top_pick(candidate, persona_records)
        if not repaired or repaired["persona_uuid"] in seen:
            continue
        seen.add(repaired["persona_uuid"])
        merged.append(repaired)
        if len(merged) >= TOP_PICK_LIMIT:
            return merged

    if len(merged) < min(TOP_PICK_LIMIT, len(persona_records)):
        merged.extend(
            build_fallback_top_picks(persona_records, token_polarities, all_persona_lemmas, exclude_uuids=seen)[: TOP_PICK_LIMIT - len(merged)]
        )
    return merged


@router.post("/generate", response_model=ReportResponse)
async def generate_report_endpoint(request: ReportRequest):
    """Generate a report from a completed survey run."""
    async with aiosqlite.connect(settings.history_db_path) as db:
        db.row_factory = aiosqlite.Row

        # Load run
        _run_rows = await db.execute_fetchall(
            "SELECT * FROM survey_runs WHERE id = ?", [request.run_id]
        )
        run_rows: list = list(_run_rows)
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

        # New data preparation: aggregated per question + pre-scored top-pick candidates
        persona_records = _build_persona_records(answers)

        # Build corpus-wide lemma frequencies for uniqueness scoring
        all_persona_lemmas: dict[str, int] = defaultdict(int)
        for record in persona_records.values():
            texts = [_strip_score_prefix(a.get("answer", "")) for a in record.get("answers", [])]
            for text in texts:
                for lemma in text_analysis.tokenize(text):
                    all_persona_lemmas[lemma] += 1

        # Polarity learning: load historical, learn fresh, merge
        historical_polarities = text_analysis.load_polarities(settings.history_db_path)
        all_texts_by_persona = [
            [_strip_score_prefix(a.get("answer", "")) for a in record.get("answers", [])]
            for record in persona_records.values()
        ]
        q1_scores: list[int] = [int(record["score"]) for record in persona_records.values() if record.get("score") is not None]
        # Only learn if we have enough personas with scores
        if len(q1_scores) >= 2:
            fresh_polarities, fresh_counts = text_analysis.learn_token_polarities(all_texts_by_persona, q1_scores)  # type: ignore[arg-type]
            historical_counts: dict[str, int] = {lemma: text_analysis.SEED_COUNTS.get(lemma, 1) for lemma in historical_polarities}
            token_polarities = text_analysis.merge_polarities(fresh_polarities, fresh_counts, historical_polarities, historical_counts)
        else:
            fresh_polarities, fresh_counts = {}, {}
            token_polarities = historical_polarities

        question_aggregation = _build_question_aggregation(answers, questions)
        top_pick_candidates = _build_top_pick_candidates(persona_records, questions, token_polarities, all_persona_lemmas)

        # Build shared system prefix for KV-cache efficiency
        from prompts import REPORT_SHARED_SYSTEM
        questions_formatted = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
        shared_system = REPORT_SHARED_SYSTEM.format(
            survey_theme=run["survey_theme"],
            persona_count=persona_count,
            questions_formatted=questions_formatted,
            question_aggregation=question_aggregation,
        )

        # 3 sequential LLM calls (KV cache hit on calls 2+3 due to shared system prefix)
        group_tendency_raw = await llm.generate_report_group_tendency(shared_system)
        conclusion_raw = await llm.generate_report_conclusion(shared_system, group_tendency_raw)
        top_picks_raw = await llm.generate_report_top_picks(shared_system, top_pick_candidates)

        fallback_group_tendency = build_fallback_group_tendency(
            aggregated["overall_score"],
            aggregated["score_distribution"],
            aggregated["demographic_breakdown"],
        )
        merged_top_picks = _merge_top_picks(top_picks_raw, persona_records, token_polarities, all_persona_lemmas)

        # Persist fresh polarities for future surveys
        if fresh_polarities:
            text_analysis.save_polarities(settings.history_db_path, fresh_polarities, fresh_counts)

        if not group_tendency_raw:
            logger.warning("report fallback used for group_tendency")
        if not conclusion_raw:
            logger.warning("report fallback used for conclusion")
        if len(merged_top_picks) != len(top_picks_raw):
            logger.warning("report fallback used for top_picks (merged %d from %d)", len(merged_top_picks), len(top_picks_raw))

        conclusion_summary, recommended_actions, conclusion = build_conclusion_fields(
            aggregated["overall_score"],
            aggregated["score_distribution"],
            answers,
            conclusion_raw,
        )

        report_data = {
            "run_id": request.run_id,
            "overall_score": aggregated["overall_score"],
            "score_distribution": aggregated["score_distribution"],
            "group_tendency": group_tendency_raw or fallback_group_tendency,
            "conclusion_summary": conclusion_summary,
            "recommended_actions": recommended_actions,
            "conclusion": conclusion,
            "top_picks": [TopPick(**pick) for pick in merged_top_picks],
            "demographic_breakdown": aggregated["demographic_breakdown"],
        }

        # Save to DB
        save_data = {k: v for k, v in report_data.items() if k != "run_id"}
        save_data["top_picks"] = [tp.model_dump() for tp in report_data["top_picks"]]
        await db.execute(
            "UPDATE survey_runs SET report_json = ? WHERE id = ?",
            [json.dumps(save_data, ensure_ascii=False, default=str), request.run_id]
        )
        await db.commit()

        return ReportResponse(**report_data)
