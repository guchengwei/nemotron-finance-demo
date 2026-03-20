import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import normalize_report_qualitative, parse_report_qualitative


def test_parse_report_qualitative_parses_clean_json():
    raw = json.dumps(
        {
            "group_tendency": "全体では前向きです。",
            "conclusion_summary": "導入判断は前向きです。",
            "recommended_actions": ["説明を強化する", "料金を明確にする", "試用導線を整える"],
            "conclusion": "導入検証を進めるべきです。",
            "top_picks": [{"persona_uuid": "p1", "persona_name": "田中"}],
        },
        ensure_ascii=False,
    )

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "全体では前向きです。"
    assert parsed["conclusion_summary"] == "導入判断は前向きです。"
    assert parsed["recommended_actions"] == ["説明を強化する", "料金を明確にする", "試用導線を整える"]
    assert parsed["conclusion"] == "導入検証を進めるべきです。"
    assert parsed["top_picks"][0]["persona_uuid"] == "p1"


def test_parse_report_qualitative_extracts_json_from_prose():
    raw = '分析結果です。\n{"group_tendency":"慎重です","conclusion_summary":"不安解消が必要です","recommended_actions":["安全性を示す","料金を整理する","導線を改善する"],"conclusion":"不安解消が必要です","top_picks":[]}\n以上です。'

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "慎重です"
    assert parsed["conclusion_summary"] == "不安解消が必要です"
    assert parsed["recommended_actions"] == ["安全性を示す", "料金を整理する", "導線を改善する"]
    assert parsed["conclusion"] == "不安解消が必要です"


def test_parse_report_qualitative_extracts_fenced_json():
    raw = '```json\n{"group_tendency":"傾向","conclusion_summary":"要点","recommended_actions":["a","b","c"],"conclusion":"結論","top_picks":[]}\n```'

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "傾向"
    assert parsed["conclusion_summary"] == "要点"
    assert parsed["recommended_actions"] == ["a", "b", "c"]
    assert parsed["conclusion"] == "結論"


def test_parse_report_qualitative_returns_partial_fields_from_malformed_json():
    raw = """
    {
      "group_tendency": "前向きです",
      "conclusion_summary": "透明性の説明を強めるべきです",
      "recommended_actions": [
        "料金体系を明示する",
        "不安点を先に解消する",
        "試用機会を作る"
      ],
      "conclusion": "透明性の説明を強めるべきです",
      "top_picks": [
        {"persona_uuid": "p1", "persona_name": "田中"}
      ]
    """

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "前向きです"
    assert parsed["conclusion_summary"] == "透明性の説明を強めるべきです"
    assert parsed["recommended_actions"] == ["料金体系を明示する", "不安点を先に解消する", "試用機会を作る"]
    assert parsed["conclusion"] == "透明性の説明を強めるべきです"
    assert parsed["top_picks"][0]["persona_uuid"] == "p1"


def test_parse_report_qualitative_handles_pure_prose_without_throwing():
    parsed = parse_report_qualitative("全体として慎重な意見が多く見られました。")

    assert parsed == {}


def test_normalize_report_qualitative_drops_malformed_top_pick_entries():
    normalized = normalize_report_qualitative(
        {
            "group_tendency": "前向き",
            "conclusion": "進めるべき",
            "unexpected": "ignore",
            "top_picks": [
                {"persona_uuid": "p1", "persona_name": "田中"},
                "bad",
                {"persona_uuid": " ", "highlight_quote": "  "},
                {"highlight_reason": "理由のみ"},
            ],
        }
    )

    assert normalized["group_tendency"] == "前向き"
    assert normalized["conclusion"] == "進めるべき"
    assert "unexpected" not in normalized
    assert normalized["top_picks"] == [
        {"persona_uuid": "p1", "persona_name": "田中"},
        {"highlight_reason": "理由のみ"},
    ]
