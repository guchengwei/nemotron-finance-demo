"""Persona filter and sample endpoints."""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
import aiosqlite

from config import settings
from models import FiltersResponse, PersonaSample, Persona, FinancialExtension

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/personas", tags=["personas"])

FINANCIAL_LITERACY_OPTIONS = ["初心者", "中級者", "上級者", "専門家"]
AGE_RANGES = ["20-29", "30-39", "40-49", "50-59", "60-69", "70+"]


@router.get("/filters", response_model=FiltersResponse)
async def get_filters():
    """Return distinct filter values from the persona database."""
    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        async def fetch_col(col: str) -> list[str]:
            rows = await db.execute_fetchall(
                f"SELECT DISTINCT {col} FROM personas WHERE {col} IS NOT NULL ORDER BY {col}"
            )
            return [r[0] for r in rows if r[0]]

        sex_vals = await fetch_col("sex")
        regions = await fetch_col("region")
        prefectures = await fetch_col("prefecture")
        education_levels = await fetch_col("education_level")

        # Top 50 occupations by count
        occ_rows = await db.execute_fetchall(
            "SELECT occupation, COUNT(*) as cnt FROM personas "
            "WHERE occupation IS NOT NULL GROUP BY occupation ORDER BY cnt DESC LIMIT 50"
        )
        top_occupations = [r[0] for r in occ_rows]

        # Total count
        count_row = await db.execute_fetchall("SELECT COUNT(*) FROM personas")
        total_count = count_row[0][0] if count_row else 0

    return FiltersResponse(
        sex=sex_vals,
        age_ranges=AGE_RANGES,
        regions=regions,
        prefectures=prefectures,
        occupations_top50=top_occupations,
        education_levels=education_levels,
        financial_literacy=FINANCIAL_LITERACY_OPTIONS,
        total_count=total_count,
    )


@router.get("/sample", response_model=PersonaSample)
async def get_sample(
    sex: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    prefecture: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    occupation: Optional[str] = Query(None),
    education: Optional[str] = Query(None),
    financial_literacy: Optional[str] = Query(None),
    count: int = Query(8, ge=1, le=200),
):
    """Return a filtered random sample of personas."""
    conditions = []
    params = []

    if sex:
        conditions.append("p.sex = ?")
        params.append(sex)
    if age_min is not None:
        conditions.append("p.age >= ?")
        params.append(age_min)
    if age_max is not None:
        conditions.append("p.age <= ?")
        params.append(age_max)
    if prefecture:
        conditions.append("p.prefecture = ?")
        params.append(prefecture)
    if region:
        conditions.append("p.region = ?")
        params.append(region)
    if occupation:
        conditions.append("p.occupation LIKE ?")
        params.append(f"%{occupation}%")
    if education:
        conditions.append("p.education_level LIKE ?")
        params.append(f"%{education}%")

    where_clause = ""
    join_clause = ""

    if financial_literacy:
        join_clause = "INNER JOIN persona_financial_context pfc ON p.uuid = pfc.persona_uuid"
        conditions.append("pfc.financial_literacy = ?")
        params.append(financial_literacy)
    else:
        join_clause = "LEFT JOIN persona_financial_context pfc ON p.uuid = pfc.persona_uuid"

    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Count matching
        count_query = f"SELECT COUNT(*) FROM personas p {join_clause} {where_clause}"
        count_row = await db.execute_fetchall(count_query, params)
        total_matching = count_row[0][0] if count_row else 0

        if total_matching == 0:
            return PersonaSample(total_matching=0, sampled=[])

        # Random sample
        sample_query = (
            f"SELECT p.*, pfc.financial_literacy, pfc.investment_experience, "
            f"pfc.financial_concerns, pfc.annual_income_bracket, pfc.asset_bracket, "
            f"pfc.primary_bank_type "
            f"FROM personas p {join_clause} {where_clause} "
            f"ORDER BY RANDOM() LIMIT ?"
        )
        rows = await db.execute_fetchall(sample_query, params + [count])

    personas = []
    for row in rows:
        r = dict(row)
        fin_ext = None
        if r.get("financial_literacy"):
            fin_ext = FinancialExtension(
                financial_literacy=r.get("financial_literacy"),
                investment_experience=r.get("investment_experience"),
                financial_concerns=r.get("financial_concerns"),
                annual_income_bracket=r.get("annual_income_bracket"),
                asset_bracket=r.get("asset_bracket"),
                primary_bank_type=r.get("primary_bank_type"),
            )
        personas.append(Persona(
            uuid=r["uuid"],
            name=r.get("name") or "不明",
            age=r.get("age") or 0,
            sex=r.get("sex") or "",
            prefecture=r.get("prefecture") or "",
            region=r.get("region") or "",
            area=r.get("area"),
            occupation=r.get("occupation") or "",
            education_level=r.get("education_level") or "",
            marital_status=r.get("marital_status") or "",
            persona=r.get("persona") or "",
            professional_persona=r.get("professional_persona") or "",
            sports_persona=r.get("sports_persona"),
            arts_persona=r.get("arts_persona"),
            travel_persona=r.get("travel_persona"),
            culinary_persona=r.get("culinary_persona"),
            cultural_background=r.get("cultural_background") or "",
            skills_and_expertise=r.get("skills_and_expertise") or "",
            skills_and_expertise_list=r.get("skills_and_expertise_list"),
            hobbies_and_interests=r.get("hobbies_and_interests") or "",
            hobbies_and_interests_list=r.get("hobbies_and_interests_list"),
            career_goals_and_ambitions=r.get("career_goals_and_ambitions") or "",
            country=r.get("country"),
            financial_extension=fin_ext,
        ))

    return PersonaSample(total_matching=total_matching, sampled=personas)
