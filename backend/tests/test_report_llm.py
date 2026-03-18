import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import normalize_report_qualitative, parse_report_qualitative


def test_parse_report_qualitative_parses_clean_json():
    raw = json.dumps(
        {
            "group_tendency": "全体では前向きです。",
            "conclusion": "導入検証を進めるべきです。",
            "top_picks": [{"persona_uuid": "p1", "persona_name": "田中"}],
        },
        ensure_ascii=False,
    )

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "全体では前向きです。"
    assert parsed["conclusion"] == "導入検証を進めるべきです。"
    assert parsed["top_picks"][0]["persona_uuid"] == "p1"


def test_parse_report_qualitative_extracts_json_from_prose():
    raw = '分析結果です。\n{"group_tendency":"慎重です","conclusion":"不安解消が必要です","top_picks":[]}\n以上です。'

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "慎重です"
    assert parsed["conclusion"] == "不安解消が必要です"


def test_parse_report_qualitative_extracts_fenced_json():
    raw = '```json\n{"group_tendency":"傾向","conclusion":"結論","top_picks":[]}\n```'

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "傾向"
    assert parsed["conclusion"] == "結論"


def test_parse_report_qualitative_returns_partial_fields_from_malformed_json():
    raw = """
    {
      "group_tendency": "前向きです",
      "conclusion": "透明性の説明を強めるべきです",
      "top_picks": [
        {"persona_uuid": "p1", "persona_name": "田中"}
      ]
    """

    parsed = parse_report_qualitative(raw)

    assert parsed["group_tendency"] == "前向きです"
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
