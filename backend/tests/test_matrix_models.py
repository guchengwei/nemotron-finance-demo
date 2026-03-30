import pytest
from matrix_models import (
    AxisConfig, QuadrantDef, AxisPreset, AXIS_PRESETS,
    ScoredPersona, KeywordEntry, MatrixReportData,
)


def test_axis_config_from_preset():
    preset = AXIS_PRESETS["interest_barrier"]
    assert preset.x_axis.name == "関心度"
    assert preset.y_axis.name == "利用障壁"
    assert len(preset.quadrants) == 4
    labels = {q.label for q in preset.quadrants}
    assert labels == {"様子見層", "潜在採用層", "慎重観察層", "即時採用層"}


def test_axis_config_from_risk_innovation_preset():
    preset = AXIS_PRESETS["risk_innovation"]
    assert preset.x_axis.name == "リスク許容度"
    assert len(preset.quadrants) == 4
    labels = {q.label for q in preset.quadrants}
    assert labels == {"慎重革新層", "積極採用層", "現状維持層", "実利追求層"}


def test_scored_persona_validation():
    p = ScoredPersona(
        persona_id="abc", name="田中", x_score=3, y_score=4,
        industry="小売業", age=40, quadrant_label="様子見層",
        keywords=[KeywordEntry(text="手数料の安さ", polarity="strength")],
    )
    assert p.x_score == 3
    assert p.keywords[0].polarity == "strength"


def test_scored_persona_rejects_out_of_range():
    with pytest.raises(Exception):
        ScoredPersona(persona_id="x", name="x", x_score=0, y_score=6)


def test_matrix_report_data_roundtrip():
    preset = AXIS_PRESETS["interest_barrier"]
    report = MatrixReportData(axes=preset)
    d = report.model_dump()
    restored = MatrixReportData(**d)
    assert restored.axes.x_axis.name == "関心度"
