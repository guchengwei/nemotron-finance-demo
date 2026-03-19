"""Pydantic models for API request/response types."""

from pydantic import BaseModel
from typing import Literal, Optional, List, Dict, Any


class FinancialExtension(BaseModel):
    financial_literacy: Optional[str] = None
    investment_experience: Optional[str] = None
    financial_concerns: Optional[str] = None
    annual_income_bracket: Optional[str] = None
    asset_bracket: Optional[str] = None
    primary_bank_type: Optional[str] = None


class FinancialExtensionSchema(BaseModel):
    """Strict schema for LLM structured output. All fields required (no Optional)."""
    financial_literacy: Literal["初心者", "中級者", "上級者", "専門家"]
    investment_experience: str
    financial_concerns: str
    annual_income_bracket: Literal["300万未満", "300-500万", "500-800万", "800-1200万", "1200万以上"]
    asset_bracket: Literal["500万未満", "500-2000万", "2000-5000万", "5000万以上"]
    primary_bank_type: Literal["メガバンク", "地方銀行", "ネット銀行", "信用金庫", "証券会社"]


class Persona(BaseModel):
    uuid: str
    name: str
    age: int
    sex: str
    prefecture: str
    region: str
    area: Optional[str] = None
    occupation: str
    education_level: str
    marital_status: str
    persona: str
    professional_persona: str
    sports_persona: Optional[str] = None
    arts_persona: Optional[str] = None
    travel_persona: Optional[str] = None
    culinary_persona: Optional[str] = None
    cultural_background: str
    skills_and_expertise: str
    skills_and_expertise_list: Optional[str] = None
    hobbies_and_interests: str
    hobbies_and_interests_list: Optional[str] = None
    career_goals_and_ambitions: str
    country: Optional[str] = None
    financial_extension: Optional[FinancialExtension] = None


class CountResponse(BaseModel):
    total_matching: int


class PersonaSample(BaseModel):
    total_matching: int
    sampled: List[Persona]


class FiltersResponse(BaseModel):
    sex: List[str]
    age_ranges: List[str]
    regions: List[str]
    prefectures: List[str]
    occupations_top50: List[str]
    education_levels: List[str]
    total_count: int


class SurveyRunRequest(BaseModel):
    persona_ids: List[str]
    survey_theme: str
    questions: Optional[List[str]] = None
    label: Optional[str] = None
    enable_thinking: Optional[bool] = True


class QuestionGenerationRequest(BaseModel):
    survey_theme: str
    enable_thinking: Optional[bool] = True


class QuestionGenerationResponse(BaseModel):
    questions: List[str]


class SurveyAnswer(BaseModel):
    persona_uuid: str
    question_index: int
    question_text: str
    answer: str
    score: Optional[int] = None


class TopPick(BaseModel):
    persona_uuid: str
    persona_name: str
    persona_summary: str
    highlight_reason: str
    highlight_quote: str


class ReportResponse(BaseModel):
    run_id: str
    overall_score: Optional[float] = None
    score_distribution: Optional[Dict[str, int]] = None
    group_tendency: Optional[str] = None
    conclusion: Optional[str] = None
    top_picks: Optional[List[TopPick]] = None
    demographic_breakdown: Optional[Dict[str, Dict[str, float]]] = None


class ReportRequest(BaseModel):
    run_id: str


class FollowUpRequest(BaseModel):
    run_id: str
    persona_uuid: str
    question: str


class SurveyRunSummary(BaseModel):
    id: str
    created_at: str
    label: Optional[str] = None
    survey_theme: str
    persona_count: int
    status: str
    overall_score: Optional[float] = None


class HistoryListResponse(BaseModel):
    runs: List[SurveyRunSummary]


class SurveyRunDetail(BaseModel):
    id: str
    created_at: str
    label: Optional[str] = None
    survey_theme: str
    questions: List[str]
    filter_config: Optional[Dict[str, Any]] = None
    persona_count: int
    status: str
    report: Optional[ReportResponse] = None
    answers: List[Dict[str, Any]] = []
    followup_chats: Dict[str, List[Dict[str, str]]] = {}
