"""Tests for rank-based score projection."""

import pytest

from matrix_projection import spread_scores, assign_quadrant
from matrix_models import AXIS_PRESETS, AxisPreset, QuadrantDef


class TestSpreadScores:
    def test_preserves_order(self):
        """Higher raw scores should map to higher spread scores."""
        raw = [2.0, 3.0, 4.0, 5.0]
        spread = spread_scores(raw)
        assert spread == sorted(spread)

    def test_maps_to_full_range(self):
        """Min raw -> 1.0, max raw -> 5.0."""
        raw = [1.0, 2.0, 3.0, 4.0, 5.0]
        spread = spread_scores(raw)
        assert spread[0] == 1.0
        assert spread[-1] == 5.0

    def test_clustered_input_gets_spread(self):
        """All-3s and 4s should be spread across the range."""
        raw = [3.0, 3.0, 4.0, 4.0, 3.0, 4.0]
        spread = spread_scores(raw)
        assert min(spread) < 2.5
        assert max(spread) > 3.5

    def test_single_value_returns_midpoint(self):
        raw = [3.0]
        spread = spread_scores(raw)
        assert spread == [3.0]

    def test_all_identical_returns_midpoints(self):
        raw = [4.0, 4.0, 4.0]
        spread = spread_scores(raw)
        assert all(s == 3.0 for s in spread)

    def test_spread_values_stay_in_range(self):
        """Spread scores must always be within [1.0, 5.0]."""
        raw = [3.0] * 10
        spread = spread_scores(raw)
        assert all(1.0 <= s <= 5.0 for s in spread)

    def test_empty_returns_empty(self):
        assert spread_scores([]) == []

    def test_two_values_map_to_endpoints(self):
        raw = [2.0, 4.0]
        spread = spread_scores(raw)
        assert spread[0] == 1.0
        assert spread[1] == 5.0

    def test_ties_get_same_value(self):
        raw = [2.0, 3.0, 3.0, 4.0]
        spread = spread_scores(raw)
        assert spread[1] == spread[2]

    def test_results_are_rounded(self):
        """All values should be rounded to 1 decimal."""
        raw = [1.0, 2.0, 3.0, 4.0, 5.0, 2.0, 3.0]
        spread = spread_scores(raw)
        for v in spread:
            assert v == round(v, 1)


class TestAssignQuadrant:
    def test_high_interest_low_barrier(self):
        preset = AXIS_PRESETS["interest_barrier"]
        assert assign_quadrant(4.0, 2.0, preset) == "即時採用層"

    def test_high_interest_high_barrier(self):
        preset = AXIS_PRESETS["interest_barrier"]
        assert assign_quadrant(4.0, 4.0, preset) == "潜在採用層"

    def test_low_interest_high_barrier(self):
        preset = AXIS_PRESETS["interest_barrier"]
        assert assign_quadrant(2.0, 4.0, preset) == "様子見層"

    def test_low_interest_low_barrier(self):
        preset = AXIS_PRESETS["interest_barrier"]
        assert assign_quadrant(2.0, 2.0, preset) == "慎重観察層"

    def test_exact_midpoint_goes_bottom_left(self):
        """x=3.0, y=3.0 -> low side on both axes."""
        preset = AXIS_PRESETS["interest_barrier"]
        assert assign_quadrant(3.0, 3.0, preset) == "慎重観察層"

    def test_uses_preset_labels_for_risk_time(self):
        """Quadrant label must come from the selected preset, not a global map."""
        preset = AXIS_PRESETS["risk_time"]
        assert assign_quadrant(4.0, 2.0, preset) == "機動投機層"

    def test_raises_clear_error_on_incomplete_quadrant_mapping(self):
        """A preset with missing quadrant definitions should raise ValueError, not KeyError."""
        base = AXIS_PRESETS["interest_barrier"]
        # Intentionally bypass model validation; assign_quadrant should still guard against
        # incomplete/invalid presets because presets may arrive from external JSON.
        bad = AxisPreset.model_construct(
            x_axis=base.x_axis,
            y_axis=base.y_axis,
            quadrants=[
                QuadrantDef(position="top-left", label="tl", subtitle="tl"),
                QuadrantDef(position="top-right", label="tr", subtitle="tr"),
                QuadrantDef(position="bottom-left", label="bl", subtitle="bl"),
            ],
        )
        with pytest.raises(ValueError) as excinfo:
            assign_quadrant(4.0, 2.0, bad)
        assert "missing" in str(excinfo.value).lower()

    @pytest.mark.parametrize(
        ("x_score", "y_score", "expected"),
        [
            (2.0, 4.0, "堅実長期層"),  # top-left
            (4.0, 4.0, "積極投資層"),  # top-right
            (2.0, 2.0, "現金保守層"),  # bottom-left
            (4.0, 2.0, "機動投機層"),  # bottom-right
        ],
    )
    def test_risk_time_reaches_all_quadrants(self, x_score, y_score, expected):
        preset = AXIS_PRESETS["risk_time"]
        assert assign_quadrant(x_score, y_score, preset) == expected
