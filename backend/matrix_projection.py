"""Rank-based score projection for matrix report.

Spreads clustered LLM scores across the 1.0-5.0 range using
rank-percentile mapping. Preserves relative ordering, handles
ties with averaged ranks. No scipy dependency.
"""

from __future__ import annotations

# Canonical quadrant labels keyed by (x_high, y_high) booleans.
# x > 3.0 = right (high interest), y > 3.0 = top (high barrier).
_QUADRANT_MAP = {
    (False, True):  "様子見層",      # top-left:     low interest, high barrier
    (True,  True):  "潜在採用層",    # top-right:    high interest, high barrier
    (False, False): "慎重観察層",    # bottom-left:  low interest, low barrier
    (True,  False): "即時採用層",    # bottom-right: high interest, low barrier
}


def spread_scores(raw: list[float], lo: float = 1.0, hi: float = 5.0) -> list[float]:
    """Map raw scores to [lo, hi] via rank-based linear interpolation.

    - Ties receive averaged rank -> same output position.
    - Single value or all-identical -> preserve the shared raw-side value.
    - Empty list -> empty list.
    """
    n = len(raw)
    if n == 0:
        return []
    if n == 1:
        return [round(min(max(raw[0], lo), hi), 1)]
    if len(set(raw)) == 1:
        clamped = round(min(max(raw[0], lo), hi), 1)
        return [clamped] * n

    # Compute 1-based averaged ranks (pure Python, no scipy)
    indexed = sorted(range(n), key=lambda i: raw[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and raw[indexed[j]] == raw[indexed[i]]:
            j += 1
        avg_rank = (i + j - 1) / 2.0 + 1  # 1-based average
        for k in range(i, j):
            ranks[indexed[k]] = avg_rank
        i = j

    spread = [round(lo + (r - 1) / (n - 1) * (hi - lo), 1) for r in ranks]
    return spread


def assign_quadrant(x_score: float, y_score: float) -> str:
    """Deterministically assign quadrant label from projected scores.

    Threshold: x > 3.0 -> right (high interest), y > 3.0 -> top (high barrier).
    Exact 3.0 falls to the low side.
    """
    return _QUADRANT_MAP[(x_score > 3.0, y_score > 3.0)]
