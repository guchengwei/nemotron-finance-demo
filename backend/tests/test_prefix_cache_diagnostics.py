import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prefix_cache_diagnostics import diff_metric_snapshots, parse_metric_snapshot


def test_parse_metric_snapshot_sums_selected_metrics():
    metrics_text = """
    # HELP vllm:prefix_cache_queries_total Cumulative number of prefix cache queries
    vllm:prefix_cache_queries_total{model_name="demo",engine="0"} 4
    vllm:prefix_cache_queries_total{model_name="demo",engine="1"} 6
    vllm:prefix_cache_hits_total{model_name="demo",engine="0"} 2
    vllm:prompt_tokens_total{model_name="demo"} 99
    vllm:kv_cache_usage_perc{model_name="demo",engine="0"} 0.25
    """

    parsed = parse_metric_snapshot(metrics_text)

    assert parsed == {
        "vllm:prefix_cache_queries_total": 10.0,
        "vllm:prefix_cache_hits_total": 2.0,
        "vllm:prompt_tokens_total": 99.0,
        "vllm:kv_cache_usage_perc": 0.25,
    }


def test_diff_metric_snapshots_defaults_missing_values_to_zero():
    before = {
        "vllm:prefix_cache_queries_total": 10.0,
        "vllm:prefix_cache_hits_total": 2.0,
    }
    after = {
        "vllm:prefix_cache_queries_total": 14.0,
        "vllm:prompt_tokens_total": 120.0,
    }

    assert diff_metric_snapshots(before, after) == {
        "vllm:prefix_cache_queries_total": 4.0,
        "vllm:prefix_cache_hits_total": -2.0,
        "vllm:prompt_tokens_total": 120.0,
    }
