"""Rank-based score projection for matrix report.

Spreads clustered LLM scores across the 1.0-5.0 range using
rank-percentile mapping. Preserves relative ordering, handles
ties with averaged ranks. No scipy dependency.
"""

from __future__ import annotations

from matrix_models import AxisPreset


_POSITION_TO_FLAGS: dict[str, tuple[bool, bool]] = {
    "top-left": (False, True),
    "top-right": (True, True),
    "bottom-left": (False, False),
    "bottom-right": (True, False),
}


def spread_scores(raw: list[float], lo: float = 1.0, hi: float = 5.0) -> list[float]:
    """Map raw scores to [lo, hi] via rank-based linear interpolation.

    - Ties receive averaged rank -> same output position.
    - Single value or all-identical -> midpoint.
    - Empty list -> empty list.
    """
    n = len(raw)
    if n == 0:
        return []
    if n == 1:
        return [round((lo + hi) / 2, 1)]
    if len(set(raw)) == 1:
        return [round((lo + hi) / 2, 1)] * n

    # Compute 1-based averaged ranks (pure Python, no scipy)
    indexed = sorted(range(n), key=lambda i: raw[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and raw[indexed[j]] == raw[indexed[i]]:
            j += 1
        tie_count = j - i
        avg_rank = (i + j - 1) / 2.0 + 1  # 1-based average
        for k in range(i, j):
            # Spread ties symmetrically around avg_rank with 0.3-rank spacing
            tie_offset = (k - i - (tie_count - 1) / 2) * 0.3
            ranks[indexed[k]] = avg_rank + tie_offset
        i = j

    spread = [round(lo + (r - 1) / (n - 1) * (hi - lo), 1) for r in ranks]
    return spread


def assign_quadrant(x_score: float, y_score: float, preset: AxisPreset) -> str:
    """Deterministically assign quadrant label from projected scores.

    Threshold: x > 3.0 -> right (high axis), y > 3.0 -> top (high axis).
    Exact 3.0 falls to the low side.
    """
    allowed_positions = set(_POSITION_TO_FLAGS.keys())
    seen_positions: set[str] = set()
    quadrant_map: dict[tuple[bool, bool], str] = {}

    for q in preset.quadrants:
        pos = q.position
        if pos not in allowed_positions:
            raise ValueError(
                f"Invalid quadrant position '{pos}'. "
                f"Allowed positions: {sorted(allowed_positions)}"
            )
        if pos in seen_positions:
            raise ValueError(f"Duplicate quadrant position '{pos}' in preset.quadrants")
        seen_positions.add(pos)
        quadrant_map[_POSITION_TO_FLAGS[pos]] = q.label

    missing = sorted(allowed_positions - seen_positions)
    if missing:
        raise ValueError(f"Preset quadrants mapping is incomplete; missing: {missing}")

    try:
        return quadrant_map[(x_score > 3.0, y_score > 3.0)]
    except KeyError:
        # Should be unreachable if we validated the preset properly.
        raise ValueError("Preset quadrants mapping is incomplete") from None
