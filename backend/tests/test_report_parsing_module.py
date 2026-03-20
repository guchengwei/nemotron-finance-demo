import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from report_parsing import normalize_report_qualitative, parse_report_qualitative


def test_report_parsing_module_keeps_existing_qualitative_behavior():
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
    normalized = normalize_report_qualitative(parsed)

    assert normalized["group_tendency"] == "全体では前向きです。"
    assert normalized["conclusion_summary"] == "導入判断は前向きです。"
    assert normalized["recommended_actions"] == ["説明を強化する", "料金を明確にする", "試用導線を整える"]
    assert normalized["conclusion"] == "導入検証を進めるべきです。"
    assert normalized["top_picks"] == [{"persona_uuid": "p1", "persona_name": "田中"}]
