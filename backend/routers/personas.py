"""Persona filter, count, and sample endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Query

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
    financial_literacy: Optional[str] = Query(None),
):
    store = get_store()
    total = store.count(
        sex=sex, age_min=age_min, age_max=age_max,
        region=region, prefecture=prefecture,
        occupation=occupation, education=education,
        financial_literacy=financial_literacy,
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
    financial_literacy: Optional[str] = Query(None),
    count: int = Query(8, ge=1, le=200),
):
    store = get_store()
    total, rows = store.sample(
        count=count,
        sex=sex, age_min=age_min, age_max=age_max,
        region=region, prefecture=prefecture,
        occupation=occupation, education=education,
        financial_literacy=financial_literacy,
    )
    personas = []
    for record in rows:
        fin_ext = None
        if record.get('financial_literacy'):
            fin_ext = FinancialExtension(
                financial_literacy=record.get('financial_literacy'),
                investment_experience=record.get('investment_experience'),
                financial_concerns=record.get('financial_concerns'),
                annual_income_bracket=record.get('annual_income_bracket'),
                asset_bracket=record.get('asset_bracket'),
                primary_bank_type=record.get('primary_bank_type'),
            )
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
