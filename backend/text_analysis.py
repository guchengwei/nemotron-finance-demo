import logging
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

TOKENIZER_VERSION = "fugashi-unidic-lite"

try:
    import fugashi
    _HAS_FUGASHI = True
except ImportError:
    _HAS_FUGASHI = False
    logger.warning("fugashi not available — falling back to whitespace tokenizer. Polarity learning disabled.")

_tagger = None

_STOPWORDS: set[str] = {
    "こと", "もの", "ため", "よう", "それ", "これ", "ところ", "ほう",
    "とき", "こちら", "どこ", "なに", "なぜ", "どう", "よく", "また",
    "ただ", "しかし",
}

_SEED_POLARITIES: dict[str, float] = {
    "便利": 1.0, "簡単": 0.8, "安心": 0.7, "期待": 0.6, "魅力": 0.8,
    "不安": -1.0, "懸念": -0.8, "難しい": -0.7, "複雑": -0.6, "リスク": -0.5,
}
# Sample count of 1 per seed entry — diluted quickly as real data accumulates
SEED_COUNTS: dict[str, int] = {lemma: 1 for lemma in _SEED_POLARITIES}


def _fallback_tokenize(text: str) -> list[str]:
    return text.split()


def tokenize(text: str) -> list[str]:
    if not _HAS_FUGASHI:
        return _fallback_tokenize(text)

    global _tagger
    if _tagger is None:
        _tagger = fugashi.Tagger()  # type: ignore[attr-defined]

    results = []
    for word in _tagger(text):
        pos1 = word.feature.pos1
        if pos1 not in {"名詞", "形容詞", "形状詞"}:
            continue
        if pos1 == "名詞":
            pos2 = word.feature.pos2
            if pos2 in {"代名詞", "接尾辞", "数詞"}:
                continue

        lemma = word.feature.lemma
        if not lemma:
            lemma = word.surface

        if len(lemma) <= 1:
            continue
        if lemma.isnumeric():
            continue
        if lemma in _STOPWORDS:
            continue

        results.append(lemma)

    return results


def is_degraded() -> bool:
    return not _HAS_FUGASHI


def extract_themes(texts: list[str], top_n: int = 5) -> list[str]:
    doc_freq: defaultdict[str, int] = defaultdict(int)
    for text in texts:
        lemmas = set(tokenize(text))
        for lemma in lemmas:
            doc_freq[lemma] += 1

    sorted_lemmas = sorted(doc_freq.items(), key=lambda x: x[1], reverse=True)
    return [lemma for lemma, _ in sorted_lemmas[:top_n]]


def extract_motifs(texts: list[str], scores: list[int | None]) -> tuple[str, str]:
    # Filter out pairs where score is None
    paired = [(text, score) for text, score in zip(texts, scores) if score is not None]

    if len(paired) < 2:
        return "利便性への期待", "導入時の不安"

    valid_texts = [p[0] for p in paired]
    valid_scores = [p[1] for p in paired]

    # Wrap each text as a single-text persona group
    texts_as_persona_groups = [[t] for t in valid_texts]
    polarities, _ = learn_token_polarities(texts_as_persona_groups, valid_scores)

    if not polarities:
        return "利便性への期待", "導入時の不安"

    # Count lemma frequencies across all texts
    lemma_freq: defaultdict[str, int] = defaultdict(int)
    for text in valid_texts:
        for lemma in tokenize(text):
            lemma_freq[lemma] += 1

    positive_motif = None
    positive_freq = -1
    negative_motif = None
    negative_freq = -1

    for lemma, polarity in polarities.items():
        freq = lemma_freq.get(lemma, 0)
        if polarity > 0.3 and freq > positive_freq:
            positive_motif = lemma
            positive_freq = freq
        elif polarity < -0.3 and freq > negative_freq:
            negative_motif = lemma
            negative_freq = freq

    pos_result = f"{positive_motif}への期待" if positive_motif else "利便性への期待"
    neg_result = f"{negative_motif}への懸念" if negative_motif else "導入時の不安"

    return pos_result, neg_result


def sentiment_score(persona_texts: list[str], token_polarities: dict[str, float]) -> int:
    all_text = " ".join(persona_texts)
    lemmas = tokenize(all_text)
    total = sum(token_polarities.get(lemma, 0.0) for lemma in lemmas)
    return int(round(total))


def concern_score(persona_texts: list[str], token_polarities: dict[str, float]) -> int:
    count = 0
    for text in persona_texts:
        for lemma in tokenize(text):
            if token_polarities.get(lemma, 0.0) < -0.5:
                count += 1
    return count


def uniqueness_score(persona_texts: list[str], all_persona_lemmas: dict[str, int]) -> int:
    lemma_set: set[str] = set()
    for text in persona_texts:
        lemma_set.update(tokenize(text))

    rare_count = sum(1 for lemma in lemma_set if all_persona_lemmas.get(lemma, 0) < 2)
    total_text_length = sum(len(t) for t in persona_texts)

    return rare_count * 20 + total_text_length // 10


def learn_token_polarities(
    all_texts_by_persona: list[list[str]],
    q1_scores: list[int],
) -> tuple[dict[str, float], dict[str, int]]:
    if len(all_texts_by_persona) < 2:
        return {}, {}

    # For each persona, get unique lemmas used
    persona_lemma_sets: list[set[str]] = []
    for persona_texts in all_texts_by_persona:
        lemmas: set[str] = set()
        for text in persona_texts:
            if text:
                lemmas.update(tokenize(text))
        persona_lemma_sets.append(lemmas)

    # For each lemma, collect scores of personas who used it
    lemma_scores: defaultdict[str, list[int]] = defaultdict(list)
    for persona_idx, lemma_set in enumerate(persona_lemma_sets):
        if persona_idx >= len(q1_scores):
            break
        score = q1_scores[persona_idx]
        for lemma in lemma_set:
            lemma_scores[lemma].append(score)

    polarities: dict[str, float] = {}
    sample_counts: dict[str, int] = {}

    for lemma, s_list in lemma_scores.items():
        if len(s_list) < 2:
            continue
        polarity = (sum(s_list) / len(s_list)) - 3.0
        polarities[lemma] = polarity
        sample_counts[lemma] = len(s_list)

    return polarities, sample_counts


def save_polarities(
    db_path: str,
    polarities: dict[str, float],
    sample_counts: dict[str, int],
) -> None:
    if is_degraded():
        logger.warning("Polarity saving skipped: tokenizer is in degraded mode.")
        return

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_polarities (
                lemma TEXT PRIMARY KEY,
                polarity REAL NOT NULL,
                sample_count INTEGER NOT NULL DEFAULT 0,
                tokenizer_version TEXT NOT NULL DEFAULT 'fugashi-unidic-lite',
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

        updated_at = datetime.now(timezone.utc).isoformat()

        for lemma, fresh_polarity in polarities.items():
            n = sample_counts.get(lemma, 1)
            row = conn.execute(
                "SELECT polarity, sample_count FROM token_polarities WHERE lemma = ?",
                (lemma,),
            ).fetchone()

            if row is not None:
                existing_polarity, existing_count = row
                new_count = existing_count + n
                new_polarity = (existing_count * existing_polarity + n * fresh_polarity) / new_count
            else:
                new_polarity = fresh_polarity
                new_count = n

            conn.execute(
                """
                INSERT INTO token_polarities (lemma, polarity, sample_count, tokenizer_version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lemma) DO UPDATE SET
                    polarity = excluded.polarity,
                    sample_count = excluded.sample_count,
                    tokenizer_version = excluded.tokenizer_version,
                    updated_at = excluded.updated_at
                """,
                (lemma, new_polarity, new_count, TOKENIZER_VERSION, updated_at),
            )

        conn.commit()
    finally:
        conn.close()


def load_polarities(db_path: str) -> dict[str, float]:
    conn = sqlite3.connect(db_path)
    try:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='token_polarities'"
        ).fetchone()
        if not table_exists:
            # Cold start: seed lexicon acts as the initial prior (sample_count=1 each)
            return dict(_SEED_POLARITIES)

        rows = conn.execute(
            "SELECT lemma, polarity FROM token_polarities WHERE tokenizer_version = ?",
            (TOKENIZER_VERSION,),
        ).fetchall()
        if not rows:
            return dict(_SEED_POLARITIES)
        return {lemma: polarity for lemma, polarity in rows}
    finally:
        conn.close()


def merge_polarities(
    fresh: dict[str, float],
    fresh_counts: dict[str, int],
    historical: dict[str, float],
    historical_counts: dict[str, int],
) -> dict[str, float]:
    all_lemmas = set(fresh.keys()) | set(historical.keys())
    merged: dict[str, float] = {}

    for lemma in all_lemmas:
        in_fresh = lemma in fresh
        in_historical = lemma in historical

        if in_fresh and in_historical:
            prior_weight = min(historical_counts.get(lemma, 0), 50)
            n = fresh_counts.get(lemma, 0)
            denominator = prior_weight + n
            if denominator > 0:
                merged[lemma] = (prior_weight * historical[lemma] + n * fresh[lemma]) / denominator
            else:
                merged[lemma] = fresh[lemma]
        elif in_fresh:
            merged[lemma] = fresh[lemma]
        else:
            merged[lemma] = historical[lemma]

    return merged
