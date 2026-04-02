import re
import pytest
from pydantic import ValidationError
from matrix_models import (
    AxisConfig, QuadrantDef, AxisPreset, AXIS_PRESETS,
    ScoredPersona, KeywordEntry, MatrixReportData,
)


def test_axis_config_from_preset():
    preset = AXIS_PRESETS["interest_barrier"]
    assert preset.x_axis.name == "関心度"
    assert preset.y_axis.name == "導入ハードル"
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


def test_quadrant_def_rejects_invalid_position():
    with pytest.raises(ValidationError) as excinfo:
        QuadrantDef(position="top_lef", label="x", subtitle="y")
    assert "position" in str(excinfo.value)


def test_axis_preset_rejects_duplicate_quadrant_positions():
    base = AXIS_PRESETS["interest_barrier"]
    with pytest.raises(ValidationError) as excinfo:
        AxisPreset(
            x_axis=base.x_axis,
            y_axis=base.y_axis,
            quadrants=[
                QuadrantDef(position="top-left", label="a", subtitle="a"),
                QuadrantDef(position="top-left", label="b", subtitle="b"),
                QuadrantDef(position="bottom-left", label="c", subtitle="c"),
                QuadrantDef(position="bottom-right", label="d", subtitle="d"),
            ],
        )
    # The most actionable error here is the duplicate itself (even though a duplicate implies a missing position).
    assert "duplicate positions" in str(excinfo.value)


def test_axis_preset_rejects_missing_quadrant_position():
    base = AXIS_PRESETS["interest_barrier"]
    preset = AxisPreset.model_construct(
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        quadrants=[
            QuadrantDef(position="top-left", label="a", subtitle="a"),
            QuadrantDef(position="top-right", label="b", subtitle="b"),
            QuadrantDef(position="bottom-left", label="c", subtitle="c"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        preset._validate_quadrants()
    assert "missing positions" in str(excinfo.value)
    assert "bottom-right" in str(excinfo.value)


def test_axis_preset_rejects_unexpected_quadrant_position_on_non_validating_instance():
    base = AXIS_PRESETS["interest_barrier"]
    preset = AxisPreset.model_construct(
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        quadrants=[
            QuadrantDef(position="top-left", label="a", subtitle="a"),
            QuadrantDef(position="top-right", label="b", subtitle="b"),
            QuadrantDef.model_construct(position=None, label="c", subtitle="c"),
            QuadrantDef.model_construct(position="top_lef", label="d", subtitle="d"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        preset._validate_quadrants()
    assert "unexpected positions" in str(excinfo.value)
    assert "None" in str(excinfo.value)
    assert "top_lef" in str(excinfo.value)


def test_axis_preset_non_validating_instance_unexpected_position_with_buggy_str_does_not_crash_error_formatting():
    class BuggyStr:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    base = AXIS_PRESETS["interest_barrier"]
    preset = AxisPreset.model_construct(
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        quadrants=[
            QuadrantDef(position="top-left", label="a", subtitle="a"),
            QuadrantDef(position="top-right", label="b", subtitle="b"),
            QuadrantDef(position="bottom-left", label="c", subtitle="c"),
            QuadrantDef.model_construct(position=BuggyStr(), label="d", subtitle="d"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        preset._validate_quadrants()
    msg = str(excinfo.value)
    assert "unexpected positions" in msg
    # Ensure the unexpected value is represented in a stable way (no address dependence).
    assert "BuggyStr" in msg
    assert re.search(r"0x[0-9a-fA-F]+", msg) is None


def test_axis_preset_non_validating_instance_unexpected_position_with_buggy_repr_does_not_crash_error_formatting():
    class BuggyRepr:
        def __repr__(self) -> str:
            raise RuntimeError("boom")

    base = AXIS_PRESETS["interest_barrier"]
    preset = AxisPreset.model_construct(
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        quadrants=[
            QuadrantDef(position="top-left", label="a", subtitle="a"),
            QuadrantDef(position="top-right", label="b", subtitle="b"),
            QuadrantDef(position="bottom-left", label="c", subtitle="c"),
            QuadrantDef.model_construct(position=BuggyRepr(), label="d", subtitle="d"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        preset._validate_quadrants()
    msg = str(excinfo.value)
    assert "unexpected positions" in msg
    # Ensure we still get a useful representation even when __repr__ raises.
    assert "BuggyRepr" in msg
    assert re.search(r"0x[0-9a-fA-F]+", msg) is None


def test_axis_preset_non_validating_instance_non_hashable_unexpected_position_is_validation_error():
    base = AXIS_PRESETS["interest_barrier"]
    preset = AxisPreset.model_construct(
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        quadrants=[
            QuadrantDef(position="top-left", label="a", subtitle="a"),
            QuadrantDef(position="top-right", label="b", subtitle="b"),
            QuadrantDef(position="bottom-left", label="c", subtitle="c"),
            QuadrantDef.model_construct(position=[], label="d", subtitle="d"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        preset._validate_quadrants()
    assert "unexpected positions" in str(excinfo.value)
    assert "[]" in str(excinfo.value)


def test_axis_preset_non_validating_instance_non_hashable_duplicate_position_is_duplicate_error():
    base = AXIS_PRESETS["interest_barrier"]
    preset = AxisPreset.model_construct(
        x_axis=base.x_axis,
        y_axis=base.y_axis,
        quadrants=[
            QuadrantDef.model_construct(position=[], label="a", subtitle="a"),
            QuadrantDef.model_construct(position=[], label="b", subtitle="b"),
            QuadrantDef(position="bottom-left", label="c", subtitle="c"),
            QuadrantDef(position="bottom-right", label="d", subtitle="d"),
        ],
    )
    with pytest.raises(ValueError) as excinfo:
        preset._validate_quadrants()
    assert "duplicate positions" in str(excinfo.value)
    assert "[]" in str(excinfo.value)
