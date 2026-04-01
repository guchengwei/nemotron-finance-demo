"""Pydantic models for matrix report pipeline."""

from __future__ import annotations
from pydantic import BaseModel, Field


class AxisDef(BaseModel):
    name: str
    rubric: str
    label_low: str
    label_high: str


class QuadrantDef(BaseModel):
    position: str  # "top-left" | "top-right" | "bottom-left" | "bottom-right"
    label: str
    subtitle: str


class AxisPreset(BaseModel):
    x_axis: AxisDef
    y_axis: AxisDef
    quadrants: list[QuadrantDef]


# Alias for frontend compatibility
AxisConfig = AxisPreset


class KeywordEntry(BaseModel):
    text: str
    polarity: str  # "strength" | "weakness"


class ScoredPersona(BaseModel):
    persona_id: str
    name: str
    x_score: float = Field(ge=1, le=5)
    y_score: float = Field(ge=1, le=5)
    x_score_raw: float = Field(default=3.0, ge=1, le=5)
    y_score_raw: float = Field(default=3.0, ge=1, le=5)
    keywords: list[KeywordEntry] = []
    quadrant_label: str = ""
    industry: str = ""
    age: int = 0


class AggregatedKeyword(BaseModel):
    text: str
    polarity: str
    count: int = 1
    elaboration: str = ""
    persona_names: list[str] = []


class KeywordSummary(BaseModel):
    strengths: list[AggregatedKeyword] = []
    weaknesses: list[AggregatedKeyword] = []


class Recommendation(BaseModel):
    title: str
    highlight_tag: str
    body: str


class MatrixReportData(BaseModel):
    """Full report — persisted to SQLite as JSON."""
    axes: AxisPreset
    personas: list[ScoredPersona] = []
    keywords: KeywordSummary = KeywordSummary()
    recommendations: list[Recommendation] = []


# -- Axis presets (canonical quadrant labels) --------------------------------

AXIS_PRESETS: dict[str, AxisPreset] = {
    "interest_barrier": AxisPreset(
        x_axis=AxisDef(
            name="関心度",
            rubric="Q1の回答スコアおよび肯定的表現の強さから1-5で評価",
            label_low="関心低い",
            label_high="関心高い",
        ),
        y_axis=AxisDef(
            name="導入ハードル",
            rubric="Q2の回答スコアおよび懸念・不安の強さから1-5で評価",
            label_low="低障壁",
            label_high="高障壁",
        ),
        quadrants=[
            QuadrantDef(position="top-left", label="様子見層", subtitle="低関心・高障壁"),
            QuadrantDef(position="top-right", label="潜在採用層", subtitle="高関心・高障壁"),
            QuadrantDef(position="bottom-left", label="慎重観察層", subtitle="低関心・低障壁"),
            QuadrantDef(position="bottom-right", label="即時採用層", subtitle="高関心・低障壁"),
        ],
    ),
    "risk_innovation": AxisPreset(
        x_axis=AxisDef(
            name="リスク許容度",
            rubric="投資・導入リスクへの態度から1-5で評価",
            label_low="リスク回避",
            label_high="リスク許容",
        ),
        y_axis=AxisDef(
            name="革新性",
            rubric="新技術・新手法への積極性から1-5で評価",
            label_low="保守的",
            label_high="革新的",
        ),
        quadrants=[
            QuadrantDef(position="top-left", label="慎重革新層", subtitle="リスク回避・革新的"),
            QuadrantDef(position="top-right", label="積極採用層", subtitle="リスク許容・革新的"),
            QuadrantDef(position="bottom-left", label="現状維持層", subtitle="リスク回避・保守的"),
            QuadrantDef(position="bottom-right", label="実利追求層", subtitle="リスク許容・保守的"),
        ],
    ),
}
