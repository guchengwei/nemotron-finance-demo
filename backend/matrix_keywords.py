"""Deterministic keyword aggregation — no LLM calls."""

from collections import Counter
from matrix_models import ScoredPersona, AggregatedKeyword, KeywordSummary


def aggregate_keywords(
    personas: list[ScoredPersona],
    top_k: int = 6,
) -> KeywordSummary:
    """Group keywords by polarity, count frequency, return top-K per group."""
    strength_counts: Counter = Counter()
    weakness_counts: Counter = Counter()
    strength_names: dict[str, list[str]] = {}
    weakness_names: dict[str, list[str]] = {}

    for p in personas:
        for kw in p.keywords:
            if kw.polarity == "strength":
                strength_counts[kw.text] += 1
                strength_names.setdefault(kw.text, []).append(p.name)
            elif kw.polarity == "weakness":
                weakness_counts[kw.text] += 1
                weakness_names.setdefault(kw.text, []).append(p.name)

    def _build(counts: Counter, names: dict[str, list[str]], polarity: str) -> list[AggregatedKeyword]:
        return [
            AggregatedKeyword(text=text, polarity=polarity, count=count, persona_names=names.get(text, []))
            for text, count in counts.most_common(top_k)
        ]

    return KeywordSummary(
        strengths=_build(strength_counts, strength_names, "strength"),
        weaknesses=_build(weakness_counts, weakness_names, "weakness"),
    )
