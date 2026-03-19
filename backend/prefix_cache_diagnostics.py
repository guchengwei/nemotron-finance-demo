"""Helpers for prefix-cache diagnostics and metric snapshot comparisons."""

from __future__ import annotations

import re

WATCHED_METRICS = (
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
    "vllm:prompt_tokens_total",
    "vllm:kv_cache_usage_perc",
)

_METRIC_LINE = re.compile(
    r"^(?P<name>[^\s{]+)(?:\{[^}]*\})?\s+(?P<value>[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)$"
)


def parse_metric_snapshot(metrics_text: str) -> dict[str, float]:
    """Aggregate selected Prometheus metrics across all label variants."""
    parsed: dict[str, float] = {}
    for raw_line in metrics_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE.match(line)
        if not match:
            continue
        name = match.group("name")
        if name not in WATCHED_METRICS:
            continue
        parsed[name] = parsed.get(name, 0.0) + float(match.group("value"))
    return parsed


def diff_metric_snapshots(
    before: dict[str, float],
    after: dict[str, float],
) -> dict[str, float]:
    """Return after-before deltas for all metrics seen in either snapshot."""
    return {
        name: after.get(name, 0.0) - before.get(name, 0.0)
        for name in sorted(set(before) | set(after))
    }
