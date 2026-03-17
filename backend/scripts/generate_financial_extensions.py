"""Batch job to generate financial extension data for personas.

Usage:
    python scripts/generate_financial_extensions.py --count 10000
    MOCK_LLM=true python scripts/generate_financial_extensions.py --count 100
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings
from prompts import FINANCIAL_EXTENSION_PROMPT, sex_display

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def generate_extension(persona: dict) -> dict | None:
    """Call LLM to generate financial profile for a persona."""
    import json_repair
    from llm import get_client

    prompt = FINANCIAL_EXTENSION_PROMPT.format(
        name=persona.get("name", "不明"),
        age=persona.get("age", "不明"),
        sex_display=sex_display(persona.get("sex", "")),
        prefecture=persona.get("prefecture", ""),
        region=persona.get("region", ""),
        occupation=persona.get("occupation", ""),
        education_level=persona.get("education_level", ""),
        marital_status=persona.get("marital_status", ""),
        persona=persona.get("persona", "")[:500],
        skills_and_expertise=persona.get("skills_and_expertise", "")[:300],
    )

    if settings.mock_llm:
        import random
        await asyncio.sleep(0.1)
        return {
            "financial_literacy": random.choice(["初心者", "中級者", "上級者", "専門家"]),
            "investment_experience": f"{persona.get('name', '不明')}は投資経験があります",
            "financial_concerns": "老後の資金と教育費が主な懸念",
            "annual_income_bracket": random.choice(["300万未満", "300-500万", "500-800万", "800-1200万", "1200万以上"]),
            "asset_bracket": random.choice(["500万未満", "500-2000万", "2000-5000万", "5000万以上"]),
            "primary_bank_type": random.choice(["メガバンク", "地方銀行", "ネット銀行", "信用金庫", "証券会社"]),
        }

    client = get_client()
    resp = await client.chat.completions.create(
        model=settings.vllm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=256,
    )
    text = resp.choices[0].message.content or "{}"
    text = re.sub(r'```(?:json)?\s*', '', text).strip()
    try:
        return json_repair.loads(text)
    except Exception:
        return None


async def process_batch(personas: list[dict], db_path: str, semaphore: asyncio.Semaphore):
    """Process a batch of personas concurrently."""
    conn = sqlite3.connect(db_path)

    async def process_one(p):
        async with semaphore:
            try:
                ext = await generate_extension(p)
                if ext:
                    conn.execute(
                        "INSERT OR REPLACE INTO persona_financial_context "
                        "(persona_uuid, financial_literacy, investment_experience, "
                        "financial_concerns, annual_income_bracket, asset_bracket, primary_bank_type) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [p["uuid"], ext.get("financial_literacy"), ext.get("investment_experience"),
                         ext.get("financial_concerns"), ext.get("annual_income_bracket"),
                         ext.get("asset_bracket"), ext.get("primary_bank_type")]
                    )
                    conn.commit()
                    logger.info("Done: %s (%s)", p.get("name", "?"), p["uuid"][:8])
                else:
                    logger.warning("Failed to generate extension for %s", p["uuid"][:8])
            except Exception as e:
                logger.error("Error processing %s: %s", p["uuid"][:8], e)

    tasks = [asyncio.create_task(process_one(p)) for p in personas]
    await asyncio.gather(*tasks)
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Generate financial extensions for personas")
    parser.add_argument("--count", type=int, default=1000, help="Number of personas to process")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent LLM calls")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N personas")
    args = parser.parse_args()

    # Load personas from DB
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row

    # Skip already processed
    rows = conn.execute(
        "SELECT p.* FROM personas p "
        "LEFT JOIN persona_financial_context pfc ON p.uuid = pfc.persona_uuid "
        "WHERE pfc.persona_uuid IS NULL "
        "LIMIT ? OFFSET ?",
        [args.count, args.offset]
    ).fetchall()
    conn.close()

    personas = [dict(r) for r in rows]
    logger.info("Processing %d personas (concurrency=%d)...", len(personas), args.concurrency)

    semaphore = asyncio.Semaphore(args.concurrency)
    asyncio.run(process_batch(personas, settings.db_path, semaphore))
    logger.info("Done.")


if __name__ == "__main__":
    main()
