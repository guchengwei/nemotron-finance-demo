#!/usr/bin/env python3
"""Measure report prefix-cache behavior against the configured vLLM server."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from config import settings
from llm import (
    build_report_request_specs,
    extract_cached_tokens,
    get_client,
    render_chat_prompt_token_ids,
    sanitize_answer_text,
)
from prefix_cache_diagnostics import diff_metric_snapshots, parse_metric_snapshot
from prompts import REPORT_SHARED_SYSTEM
from routers import report as report_router


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure vLLM prefix-cache behavior for report generation."
    )
    parser.add_argument("--run-id", required=True, help="Completed survey run id")
    parser.add_argument(
        "--history-db",
        default=settings.history_db_path,
        help="SQLite history DB to inspect for the target run",
    )
    parser.add_argument(
        "--metrics-url",
        default="http://127.0.0.1:8000/metrics",
        help="Prometheus metrics endpoint for the active vLLM server",
    )
    return parser.parse_args()


def _load_run_data(history_db_path: str, run_id: str) -> tuple[dict, list[dict], str, str]:
    conn = sqlite3.connect(history_db_path)
    conn.row_factory = sqlite3.Row
    try:
        run_row = conn.execute(
            "SELECT * FROM survey_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise SystemExit(f"Run not found: {run_id}")
        answer_rows = conn.execute(
            "SELECT * FROM survey_answers WHERE run_id = ? ORDER BY persona_uuid, question_index",
            (run_id,),
        ).fetchall()
        if not answer_rows:
            raise SystemExit(f"No answers found for run: {run_id}")
        run = dict(run_row)
        answers = [dict(row) for row in answer_rows]
        questions = json.loads(run["questions_json"])
        persona_count = len(set(answer["persona_uuid"] for answer in answers))
        question_aggregation = report_router._build_question_aggregation(answers, questions)
        persona_records = report_router._build_persona_records(answers)
        top_pick_candidates = report_router._build_top_pick_candidates(persona_records, questions)
        questions_formatted = "\n".join(
            f"{index + 1}. {question}" for index, question in enumerate(questions)
        )
        shared_system = REPORT_SHARED_SYSTEM.format(
            survey_theme=run["survey_theme"],
            persona_count=persona_count,
            questions_formatted=questions_formatted,
            question_aggregation=question_aggregation,
        )
        return run, answers, shared_system, top_pick_candidates
    finally:
        conn.close()


def _fetch_metric_snapshot(metrics_url: str) -> dict[str, float]:
    try:
        with urlopen(metrics_url) as response:
            text = response.read().decode("utf-8")
    except URLError as exc:
        raise SystemExit(
            f"Could not reach vLLM metrics endpoint at {metrics_url}: {exc}"
        ) from exc
    return parse_metric_snapshot(text)


def _common_prefix_len(left: list[int], right: list[int]) -> int:
    prefix = 0
    for lhs, rhs in zip(left, right):
        if lhs != rhs:
            break
        prefix += 1
    return prefix


async def _execute_spec(spec: dict) -> tuple[object, str]:
    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.vllm_model,
        messages=spec["messages"],
        temperature=spec["temperature"],
        max_tokens=spec["max_tokens"],
        extra_body=spec["extra_body"],
    )
    content = resp.choices[0].message.content or ""
    return resp, content


async def _run_measurement(run_id: str, history_db_path: str, metrics_url: str) -> None:
    _, _, shared_system, top_pick_candidates = _load_run_data(history_db_path, run_id)

    before = _fetch_metric_snapshot(metrics_url)

    group_spec = build_report_request_specs(
        shared_system=shared_system,
        group_tendency="",
        top_pick_candidates=top_pick_candidates,
    )[0]
    group_resp, group_tendency = await _execute_spec(group_spec)
    clean_group_tendency = sanitize_answer_text(group_tendency).strip()

    specs = build_report_request_specs(
        shared_system=shared_system,
        group_tendency=clean_group_tendency,
        top_pick_candidates=top_pick_candidates,
    )
    conclusion_resp, _ = await _execute_spec(specs[1])
    top_picks_resp, _ = await _execute_spec(specs[2])

    after = _fetch_metric_snapshot(metrics_url)
    tokenized = [render_chat_prompt_token_ids(spec["messages"]) for spec in specs]

    print(f"run_id: {run_id}")
    print(f"history_db: {history_db_path}")
    print(f"model: {settings.vllm_model}")
    print(f"vllm_url: {settings.vllm_url}")
    print(f"metrics_url: {metrics_url}")
    print("request_order: group_tendency -> conclusion -> top_picks")
    print(
        "prompt_token_lengths:",
        {
            spec["name"]: len(ids)
            for spec, ids in zip(specs, tokenized)
        },
    )
    print(
        "common_prefix_lengths:",
        {
            "group_vs_conclusion": _common_prefix_len(tokenized[0], tokenized[1]),
            "group_vs_top_picks": _common_prefix_len(tokenized[0], tokenized[2]),
            "conclusion_vs_top_picks": _common_prefix_len(tokenized[1], tokenized[2]),
        },
    )
    print(
        "request_cached_tokens:",
        {
            "group_tendency": extract_cached_tokens(group_resp),
            "conclusion": extract_cached_tokens(conclusion_resp),
            "top_picks": extract_cached_tokens(top_picks_resp),
        },
    )
    print("metrics_before:", before)
    print("metrics_after:", after)
    print("metrics_delta:", diff_metric_snapshots(before, after))


def main() -> None:
    args = _parse_args()
    asyncio.run(_run_measurement(args.run_id, args.history_db, args.metrics_url))


if __name__ == "__main__":
    main()
