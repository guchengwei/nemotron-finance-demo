"""Tests for rank-based score projection."""

from matrix_projection import spread_scores, assign_quadrant


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
        assert assign_quadrant(4.0, 2.0) == "即時採用層"

    def test_high_interest_high_barrier(self):
        assert assign_quadrant(4.0, 4.0) == "潜在採用層"

    def test_low_interest_high_barrier(self):
        assert assign_quadrant(2.0, 4.0) == "様子見層"

    def test_low_interest_low_barrier(self):
        assert assign_quadrant(2.0, 2.0) == "慎重観察層"

    def test_exact_midpoint_goes_bottom_left(self):
        """x=3.0, y=3.0 -> low side on both axes."""
        assert assign_quadrant(3.0, 3.0) == "慎重観察層"
