import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import (
    build_report_request_specs,
    extract_cached_tokens,
    normalize_report_qualitative,
    parse_report_qualitative,
    render_chat_prompt_token_ids,
)


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


def test_build_report_request_specs_share_long_prefix_after_chat_templating():
    shared_system = "\n".join(
        [
            "あなたは金融マーケティングリサーチのシニアアナリストです。",
            "テーマ: AI家計管理アプリ",
            "回答者数: 24名",
            "質問一覧:",
            "1. このサービスへの関心度を教えてください",
            "2. 利用時に重視する点を教えてください",
            "全回答者の集計結果:",
            "Q1: 平均スコア 3.8, 分布: {'1': 1, '2': 2, '3': 6, '4': 9, '5': 6}",
            "Q2: 主要テーマ: 使いやすさ, 手数料, 安心感, 透明性",
            "代表回答: 手数料が分かりやすければ前向きに検討したい",
        ]
    )
    specs = build_report_request_specs(
        shared_system=shared_system,
        group_tendency="前向きな声が優勢だが、手数料の透明性に慎重な意見が残る。",
        top_pick_candidates="\n".join(
            [
                "persona_uuid: p1",
                "summary: 42歳会社員、東京都",
                "score: 5",
                "Q: このサービスへの関心度を教えてください",
                "A: 手数料と安心感の両立が見えれば積極的に使いたいです。",
            ]
        ),
    )

    tokenized = [render_chat_prompt_token_ids(spec["messages"]) for spec in specs]

    def common_prefix_len(left: list[int], right: list[int]) -> int:
        prefix = 0
        for lhs, rhs in zip(left, right):
            if lhs != rhs:
                break
            prefix += 1
        return prefix

    assert [spec["name"] for spec in specs] == [
        "group_tendency",
        "conclusion",
        "top_picks",
    ]
    assert common_prefix_len(tokenized[0], tokenized[1]) > 50
    assert common_prefix_len(tokenized[0], tokenized[2]) > 50
    assert common_prefix_len(tokenized[1], tokenized[2]) > 50
    assert specs[0]["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert specs[1]["extra_body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert "structured_outputs" in specs[2]["extra_body"]


def test_extract_cached_tokens_returns_none_without_prompt_token_details():
    assert extract_cached_tokens(SimpleNamespace(usage=None)) is None
    assert extract_cached_tokens(SimpleNamespace(usage=SimpleNamespace(prompt_tokens_details=None))) is None
    assert (
        extract_cached_tokens(
            SimpleNamespace(
                usage=SimpleNamespace(
                    prompt_tokens_details=SimpleNamespace(cached_tokens=128)
                )
            )
        )
        == 128
    )
