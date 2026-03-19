"""Persona filter, count, and sample endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

from llm import generate_financial_extensions
from models import CountResponse, FiltersResponse, PersonaSample, Persona, FinancialExtension
from persona_store import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/personas', tags=['personas'])


@router.get('/filters', response_model=FiltersResponse)
async def get_filters():
    """Return distinct filter values from the persona store."""
    store = get_store()
    f = store.get_filters()
    return FiltersResponse(**f)


@router.get('/count', response_model=CountResponse)
async def get_count(
    sex: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    prefecture: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    occupation: Optional[str] = Query(None),
    education: Optional[str] = Query(None),
):
    store = get_store()
    total = store.count(
        sex=sex, age_min=age_min, age_max=age_max,
        region=region, prefecture=prefecture,
        occupation=occupation, education=education,
    )
    return CountResponse(total_matching=total)


@router.get('/sample', response_model=PersonaSample)
async def get_sample(
    sex: Optional[str] = Query(None),
    age_min: Optional[int] = Query(None, ge=0),
    age_max: Optional[int] = Query(None, le=120),
    prefecture: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    occupation: Optional[str] = Query(None),
    education: Optional[str] = Query(None),
    count: int = Query(8, ge=1, le=200),
):
    store = get_store()
    total, rows = store.sample(
        count=count,
        sex=sex, age_min=age_min, age_max=age_max,
        region=region, prefecture=prefecture,
        occupation=occupation, education=education,
    )

    # Enrich personas lacking cached financial extension
    uncached = [p for p in rows if store.get_cached_financial(p.get("uuid", "")) is None]
    if uncached:
        results = await generate_financial_extensions(uncached)
        for p, (ext, should_cache) in zip(uncached, results):
            if should_cache:
                store.set_cached_financial(p["uuid"], ext)

    personas = []
    for record in rows:
        fin = store.get_cached_financial(record.get("uuid", ""))
        fin_ext = FinancialExtension(**fin) if fin else None
        personas.append(Persona(
            uuid=record['uuid'],
            name=record.get('name') or '不明',
            age=record.get('age') or 0,
            sex=record.get('sex') or '',
            prefecture=record.get('prefecture') or '',
            region=record.get('region') or '',
            area=record.get('area'),
            occupation=record.get('occupation') or '',
            education_level=record.get('education_level') or '',
            marital_status=record.get('marital_status') or '',
            persona=record.get('persona') or '',
            professional_persona=record.get('professional_persona') or '',
            sports_persona=record.get('sports_persona'),
            arts_persona=record.get('arts_persona'),
            travel_persona=record.get('travel_persona'),
            culinary_persona=record.get('culinary_persona'),
            cultural_background=record.get('cultural_background') or '',
            skills_and_expertise=record.get('skills_and_expertise') or '',
            skills_and_expertise_list=record.get('skills_and_expertise_list'),
            hobbies_and_interests=record.get('hobbies_and_interests') or '',
            hobbies_and_interests_list=record.get('hobbies_and_interests_list'),
            career_goals_and_ambitions=record.get('career_goals_and_ambitions') or '',
            country=record.get('country'),
            financial_extension=fin_ext,
        ))
    return PersonaSample(total_matching=total, sampled=personas)
