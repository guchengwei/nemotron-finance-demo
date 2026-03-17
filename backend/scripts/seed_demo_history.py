"""Pre-generate demo survey runs for booth presentation.

Usage:
    MOCK_LLM=true python scripts/seed_demo_history.py
"""

import asyncio
import json
import logging
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEMO_RUNS = [
    {
        "theme": "投資信託のオンライン販売プラットフォームに対する関心度と懸念点",
        "label": "投信オンライン_混合デモグラフィック",
        "questions": [
            "このようなサービスに対する全体的な関心度を教えてください（1:全く関心がない〜5:非常に関心がある）",
            "最も重要だと考える機能や特徴は何ですか？",
            "利用にあたって最も懸念される点は何ですか？",
        ],
        "persona_count": 8,
        "days_ago": 5,
    },
    {
        "theme": "AIを活用した資産運用アドバイザリーサービスの導入に対する金融機関顧客の反応",
        "label": "AI資産運用_高所得層",
        "questions": [
            "AIによる資産運用アドバイスをどの程度信頼できると思いますか？（1:全く信頼できない〜5:非常に信頼できる）",
            "AIアドバイザーに期待する主な機能を教えてください",
            "人間のFPとAIアドバイザーをどのように使い分けたいですか？",
            "セキュリティや個人情報保護についての懸念をお聞かせください",
        ],
        "persona_count": 8,
        "days_ago": 2,
    },
    {
        "theme": "デジタル銀行サービスの利便性と若年層の金融リテラシー向上への活用",
        "label": "デジタル銀行_20-30代",
        "questions": [
            "デジタル専業銀行のサービスにどの程度関心がありますか？（1:全く関心がない〜5:非常に関心がある）",
            "既存の銀行と比較して魅力的だと思う点は何ですか？",
            "利用を躊躇する理由があれば教えてください",
        ],
        "persona_count": 8,
        "days_ago": 1,
    },
]

MOCK_ANSWERS_TEMPLATE = [
    {
        "score": 4,
        "answers": [
            "【評価: 4】このサービスには大変興味があります。手数料の透明性と使いやすさが確保されれば、積極的に利用を検討したいと思います。",
            "セキュリティ対策の充実と直感的な操作画面が最も重要だと考えます。複雑な手続きは利用の妨げになります。",
            "個人情報の取り扱いとシステム障害時の対応が最大の懸念事項です。信頼できるサポート体制が必要です。",
            "手数料体系の明確化と、既存の金融機関との連携が課題だと感じます。",
        ]
    },
    {
        "score": 2,
        "answers": [
            "【評価: 2】まだ様子見の段階です。実績や信頼性が積み上がるまで、慎重に判断したいと思います。",
            "現時点では従来の方法で十分だと感じています。新しいサービスへの移行コストも考慮が必要です。",
            "セキュリティリスクと、トラブル時の補償が明確でない点が気になります。",
            "まずは小額から試せる仕組みがあれば検討しやすいと思います。",
        ]
    },
    {
        "score": 5,
        "answers": [
            "【評価: 5】非常に魅力的なサービスだと思います。効率性とコスト削減の観点から、ぜひ活用したいです。",
            "リアルタイムな資産状況確認と自動リバランス機能が特に魅力です。",
            "特に大きな懸念はありません。むしろ早期導入を検討しています。",
            "より多くの金融商品ラインナップがあれば完璧です。",
        ]
    },
    {
        "score": 3,
        "answers": [
            "【評価: 3】一定の関心はありますが、まだ判断する情報が不足しています。もう少し詳細が知りたいです。",
            "コストパフォーマンスと利便性のバランスが重要です。",
            "新しいサービスへの信頼構築に時間がかかりそうな点が懸念です。",
            "試験的に少額から始められる導入プランがあれば良いと思います。",
        ]
    },
]


def create_mock_run(run_config: dict, personas: list[dict]) -> dict:
    """Create a complete mock survey run."""
    run_id = str(uuid.uuid4())
    questions = run_config["questions"]
    theme = run_config["theme"]
    created_at = datetime.now() - timedelta(days=run_config["days_ago"])

    answers = []
    scores = []
    for i, persona in enumerate(personas):
        template = MOCK_ANSWERS_TEMPLATE[i % len(MOCK_ANSWERS_TEMPLATE)]
        score = template["score"]
        scores.append(score)
        for q_idx, question in enumerate(questions):
            ans_text = template["answers"][q_idx] if q_idx < len(template["answers"]) else "（回答なし）"
            answers.append({
                "run_id": run_id,
                "persona_uuid": persona["uuid"],
                "persona_summary": f"{persona['name']}, {persona['age']}歳, {persona['occupation']}, {persona['prefecture']}",
                "persona_full_json": json.dumps(persona, ensure_ascii=False, default=str),
                "question_index": q_idx,
                "question_text": question,
                "answer": ans_text,
                "score": score if q_idx == 0 else None,
            })

    overall_score = round(sum(scores) / len(scores), 1)
    report = {
        "overall_score": overall_score,
        "score_distribution": {
            str(s): scores.count(s) for s in range(1, 6)
        },
        "group_tendency": f"全体として{overall_score}点の評価。特に40代以上の層でより積極的な評価が見られた。セキュリティと手数料の透明性への関心が高い。",
        "conclusion": f"「{theme}」に対し、回答者の約{len([s for s in scores if s >= 4])*100//len(scores)}%が肯定的（4-5点）。主な懸念事項はセキュリティと使いやすさ。段階的な導入と十分なサポート体制が成功の鍵。",
        "top_picks": [
            {
                "persona_uuid": personas[0]["uuid"] if personas else "mock-1",
                "persona_name": personas[0]["name"] if personas else "田中太郎",
                "persona_summary": f"{personas[0]['age']}歳, {personas[0]['occupation']}" if personas else "テストユーザー",
                "highlight_reason": "最も詳細で具体的な改善提案を含む回答",
                "highlight_quote": "手数料体系の透明性が確保されれば積極的に利用したい"
            },
            {
                "persona_uuid": personas[1]["uuid"] if len(personas) > 1 else "mock-2",
                "persona_name": personas[1]["name"] if len(personas) > 1 else "佐藤花子",
                "persona_summary": f"{personas[1]['age']}歳, {personas[1]['occupation']}" if len(personas) > 1 else "テストユーザー2",
                "highlight_reason": "懸念点を明確に表現した慎重派の典型的意見",
                "highlight_quote": "実績が積み上がるまで様子見したい"
            },
            {
                "persona_uuid": personas[2]["uuid"] if len(personas) > 2 else "mock-3",
                "persona_name": personas[2]["name"] if len(personas) > 2 else "山田健一",
                "persona_summary": f"{personas[2]['age']}歳, {personas[2]['occupation']}" if len(personas) > 2 else "テストユーザー3",
                "highlight_reason": "業界全体への提言を含む独自視点",
                "highlight_quote": "既存銀行との連携強化が普及の鍵になる"
            },
        ],
        "demographic_breakdown": {
            "by_age": {"20-39": 3.1, "40-59": 3.8, "60+": 2.9},
            "by_sex": {"男性": 3.5, "女性": 3.3},
            "by_financial_literacy": {"初心者": 2.8, "中級者": 3.4, "上級者": 3.9, "専門家": 4.1}
        }
    }

    return {
        "run_id": run_id,
        "created_at": created_at.isoformat(),
        "theme": theme,
        "questions": questions,
        "label": run_config["label"],
        "persona_count": len(personas),
        "answers": answers,
        "report": report,
    }


def seed_history():
    """Seed the history database with demo runs."""
    # Load sample personas
    persona_conn = sqlite3.connect(settings.db_path)
    persona_conn.row_factory = sqlite3.Row

    total = persona_conn.execute("SELECT COUNT(*) FROM personas").fetchone()[0]
    if total == 0:
        logger.error("Persona database is empty. Run db loading first.")
        return

    history_conn = sqlite3.connect(settings.history_db_path)

    for run_config in DEMO_RUNS:
        # Check if a run with this label already exists
        existing = history_conn.execute(
            "SELECT id FROM survey_runs WHERE label = ?", [run_config["label"]]
        ).fetchone()
        if existing:
            logger.info("Run '%s' already exists — skipping", run_config["label"])
            continue

        # Sample personas
        persona_rows = persona_conn.execute(
            "SELECT * FROM personas ORDER BY RANDOM() LIMIT ?",
            [run_config["persona_count"]]
        ).fetchall()
        personas = [dict(r) for r in persona_rows]

        run_data = create_mock_run(run_config, personas)

        # Insert run
        history_conn.execute(
            "INSERT INTO survey_runs (id, created_at, survey_theme, questions_json, "
            "persona_count, status, report_json, label) VALUES (?, ?, ?, ?, ?, 'completed', ?, ?)",
            [
                run_data["run_id"],
                run_data["created_at"],
                run_data["theme"],
                json.dumps(run_data["questions"], ensure_ascii=False),
                run_data["persona_count"],
                json.dumps(run_data["report"], ensure_ascii=False),
                run_data["label"],
            ]
        )

        # Insert answers
        for ans in run_data["answers"]:
            history_conn.execute(
                "INSERT INTO survey_answers (run_id, persona_uuid, persona_summary, "
                "persona_full_json, question_index, question_text, answer, score) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [ans["run_id"], ans["persona_uuid"], ans["persona_summary"],
                 ans["persona_full_json"], ans["question_index"], ans["question_text"],
                 ans["answer"], ans["score"]]
            )

        history_conn.commit()
        logger.info("Seeded run: %s (run_id: %s)", run_config["label"], run_data["run_id"])

    persona_conn.close()
    history_conn.close()
    logger.info("Demo history seeding complete.")


if __name__ == "__main__":
    seed_history()
