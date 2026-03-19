import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
import text_analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_tokenize(text: str) -> list[str]:
    """Simple whitespace tokenizer used as monkeypatch replacement."""
    return text.split()


# ---------------------------------------------------------------------------
# extract_themes
# ---------------------------------------------------------------------------

@pytest.mark.skipif(text_analysis.is_degraded(), reason="fugashi not available")
def test_extract_themes_returns_content_words():
    texts = [
        "このサービスはとても便利です",
        "利用して安心しました",
        "便利で安心できるサービスです",
    ]
    themes = text_analysis.extract_themes(texts, top_n=10)
    assert "便利" in themes, f"Expected '便利' in themes, got: {themes}"
    assert "安心" in themes, f"Expected '安心' in themes, got: {themes}"


@pytest.mark.skipif(text_analysis.is_degraded(), reason="fugashi not available")
def test_extract_themes_excludes_stopwords():
    texts = [
        "このことがとても大切なことです",
        "そのことについてのことです",
        "ものごとのことです",
    ]
    themes = text_analysis.extract_themes(texts, top_n=10)
    assert "こと" not in themes, f"Stopword 'こと' should not appear in themes: {themes}"
    assert "もの" not in themes, f"Stopword 'もの' should not appear in themes: {themes}"


# ---------------------------------------------------------------------------
# learn_token_polarities
# ---------------------------------------------------------------------------

def test_learn_token_polarities_positive_words_get_positive_polarity(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    # 3 personas all using "便利", all with high scores (4, 5, 4)
    all_texts = [["便利 サービス"], ["便利 機能"], ["便利 システム"]]
    q1_scores = [4, 5, 4]

    polarities, _ = text_analysis.learn_token_polarities(all_texts, q1_scores)

    assert "便利" in polarities, f"'便利' should be in polarities: {polarities}"
    assert polarities["便利"] > 0, f"'便利' should have positive polarity, got {polarities['便利']}"


def test_learn_token_polarities_negative_words_get_negative_polarity(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    # 3 personas all using "不安", all with low scores (1, 2, 1)
    all_texts = [["不安 要素"], ["不安 感じる"], ["不安 リスク"]]
    q1_scores = [1, 2, 1]

    polarities, _ = text_analysis.learn_token_polarities(all_texts, q1_scores)

    assert "不安" in polarities, f"'不安' should be in polarities: {polarities}"
    assert polarities["不安"] < 0, f"'不安' should have negative polarity, got {polarities['不安']}"


def test_learn_token_polarities_min_frequency_threshold(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    # "rare" used by only 1 persona — should NOT appear
    # "common" used by 2 personas — SHOULD appear
    all_texts = [["rare common"], ["common only2"]]
    q1_scores = [3, 3]

    polarities, _ = text_analysis.learn_token_polarities(all_texts, q1_scores)

    assert "rare" not in polarities, f"'rare' (1 persona) should not appear: {polarities}"
    assert "common" in polarities, f"'common' (2 personas) should appear: {polarities}"


def test_learn_token_polarities_too_few_personas(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    all_texts = [["便利 サービス"]]  # only 1 persona
    q1_scores = [5]

    polarities, counts = text_analysis.learn_token_polarities(all_texts, q1_scores)

    assert polarities == {}, f"Expected empty dict, got {polarities}"
    assert counts == {}, f"Expected empty dict, got {counts}"


# ---------------------------------------------------------------------------
# save_polarities / load_polarities round-trip
# ---------------------------------------------------------------------------

def test_save_load_round_trip(tmp_path, monkeypatch):
    # Ensure not degraded for this test; if degraded, save is a no-op
    if text_analysis.is_degraded():
        monkeypatch.setattr(text_analysis, "_HAS_FUGASHI", True)

    db_path = str(tmp_path / "test.db")
    polarities = {"便利": 1.0, "不安": -1.0, "安心": 0.7}
    counts = {"便利": 3, "不安": 2, "安心": 4}

    text_analysis.save_polarities(db_path, polarities, counts)
    loaded = text_analysis.load_polarities(db_path)

    for lemma, expected in polarities.items():
        assert lemma in loaded, f"'{lemma}' missing from loaded polarities"
        assert abs(loaded[lemma] - expected) < 1e-9, (
            f"Polarity mismatch for '{lemma}': expected {expected}, got {loaded[lemma]}"
        )


def test_save_upsert_increments_sample_count(tmp_path, monkeypatch):
    if text_analysis.is_degraded():
        monkeypatch.setattr(text_analysis, "_HAS_FUGASHI", True)

    db_path = str(tmp_path / "test.db")
    lemma = "便利"

    # First save: polarity=1.0, count=2
    text_analysis.save_polarities(db_path, {lemma: 1.0}, {lemma: 2})
    # Second save: same lemma, polarity=0.0, count=2
    text_analysis.save_polarities(db_path, {lemma: 0.0}, {lemma: 2})

    import sqlite3
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT polarity, sample_count FROM token_polarities WHERE lemma = ?", (lemma,)
    ).fetchone()
    conn.close()

    assert row is not None
    polarity, sample_count = row
    # sample_count should be 4 (2 + 2)
    assert sample_count == 4, f"Expected sample_count=4, got {sample_count}"
    # weighted average: (2*1.0 + 2*0.0) / 4 = 0.5
    assert abs(polarity - 0.5) < 1e-9, f"Expected polarity=0.5, got {polarity}"


# ---------------------------------------------------------------------------
# load_polarities cold start
# ---------------------------------------------------------------------------

def test_load_polarities_cold_start(tmp_path):
    # Path exists but no DB file — should return seed polarities
    db_path = str(tmp_path / "nonexistent.db")
    result = text_analysis.load_polarities(db_path)

    assert len(result) > 0, "Cold start should return non-empty seed dict"
    assert "便利" in result, f"Seed should contain '便利', got keys: {list(result.keys())}"
    assert result["便利"] > 0, f"'便利' should have positive polarity in seed, got {result['便利']}"


# ---------------------------------------------------------------------------
# merge_polarities
# ---------------------------------------------------------------------------

def test_merge_polarities_small_fresh_count_favors_historical():
    # historical: +1.0 with count=50 (capped at 50), fresh: -1.0 with count=1
    lemma = "テスト"
    historical = {lemma: 1.0}
    historical_counts = {lemma: 50}
    fresh = {lemma: -1.0}
    fresh_counts = {lemma: 1}

    merged = text_analysis.merge_polarities(fresh, fresh_counts, historical, historical_counts)

    assert lemma in merged
    # prior_weight = min(50, 50) = 50; n = 1; merged = (50*1.0 + 1*(-1.0)) / 51 ≈ 0.941
    # Should be much closer to +1.0 than to -1.0
    assert merged[lemma] > 0.0, (
        f"Merged should be closer to historical (+1.0) but got {merged[lemma]}"
    )
    assert abs(merged[lemma] - 1.0) < abs(merged[lemma] - (-1.0)), (
        f"Merged {merged[lemma]} should be closer to +1.0 than to -1.0"
    )


def test_merge_polarities_large_fresh_count_favors_fresh():
    # historical: +1.0 with count=1, fresh: -1.0 with count=50
    lemma = "テスト"
    historical = {lemma: 1.0}
    historical_counts = {lemma: 1}
    fresh = {lemma: -1.0}
    fresh_counts = {lemma: 50}

    merged = text_analysis.merge_polarities(fresh, fresh_counts, historical, historical_counts)

    assert lemma in merged
    # prior_weight = min(1, 50) = 1; n = 50; merged = (1*1.0 + 50*(-1.0)) / 51 ≈ -0.961
    # Should be much closer to -1.0 than to +1.0
    assert merged[lemma] < 0.0, (
        f"Merged should be closer to fresh (-1.0) but got {merged[lemma]}"
    )
    assert abs(merged[lemma] - (-1.0)) < abs(merged[lemma] - 1.0), (
        f"Merged {merged[lemma]} should be closer to -1.0 than to +1.0"
    )


def test_merge_polarities_lemma_only_in_fresh():
    fresh = {"新規": 0.5}
    fresh_counts = {"新規": 3}
    historical = {}
    historical_counts = {}

    merged = text_analysis.merge_polarities(fresh, fresh_counts, historical, historical_counts)

    assert "新規" in merged
    assert merged["新規"] == 0.5


def test_merge_polarities_lemma_only_in_historical():
    fresh = {}
    fresh_counts = {}
    historical = {"古い": -0.3}
    historical_counts = {"古い": 5}

    merged = text_analysis.merge_polarities(fresh, fresh_counts, historical, historical_counts)

    assert "古い" in merged
    assert merged["古い"] == -0.3


# ---------------------------------------------------------------------------
# sentiment_score
# ---------------------------------------------------------------------------

def test_sentiment_score_higher_for_positive_words(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    polarity_dict = {"便利": 1.0, "安心": 0.7, "不安": -1.0, "懸念": -0.8}

    positive_texts = ["便利 安心"]
    negative_texts = ["不安 懸念"]

    pos_score = text_analysis.sentiment_score(positive_texts, polarity_dict)
    neg_score = text_analysis.sentiment_score(negative_texts, polarity_dict)

    assert pos_score > neg_score, (
        f"Positive persona score ({pos_score}) should be higher than negative ({neg_score})"
    )


# ---------------------------------------------------------------------------
# concern_score
# ---------------------------------------------------------------------------

def test_concern_score_counts_negative_polarity_lemmas(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    polarity_dict = {"危険": -0.8, "安全": 0.9}

    texts_with_concern = ["危険 要因"]
    texts_without_concern = ["安全 環境"]

    score_with = text_analysis.concern_score(texts_with_concern, polarity_dict)
    score_without = text_analysis.concern_score(texts_without_concern, polarity_dict)

    assert score_with > 0, f"Should count concern lemma, got {score_with}"
    assert score_without == 0, f"No concern lemmas, expected 0, got {score_without}"


# ---------------------------------------------------------------------------
# uniqueness_score
# ---------------------------------------------------------------------------

def test_uniqueness_score_rare_vocab_scores_higher(monkeypatch):
    monkeypatch.setattr(text_analysis, "tokenize", _split_tokenize)

    # rare_lemma appears 0 times in all_persona_lemmas (< 2)
    # common_lemma appears 5 times (>= 2)
    all_persona_lemmas = {"common_lemma": 5, "another_common": 3}

    rare_texts = ["rare_lemma unique_word"]
    common_texts = ["common_lemma another_common"]

    rare_score = text_analysis.uniqueness_score(rare_texts, all_persona_lemmas)
    common_score = text_analysis.uniqueness_score(common_texts, all_persona_lemmas)

    assert rare_score > common_score, (
        f"Rare vocab score ({rare_score}) should be higher than common vocab score ({common_score})"
    )


# ---------------------------------------------------------------------------
# degraded mode: save_polarities skips write
# ---------------------------------------------------------------------------

def test_degraded_mode_save_skips_write(tmp_path, monkeypatch):
    monkeypatch.setattr(text_analysis, "_HAS_FUGASHI", False)

    db_path = str(tmp_path / "degraded.db")
    # Should not raise, should not create the table
    text_analysis.save_polarities(db_path, {"便利": 1.0}, {"便利": 1})

    import sqlite3
    conn = sqlite3.connect(db_path)
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='token_polarities'"
    ).fetchone()
    conn.close()

    assert table_exists is None, "Table should NOT exist when in degraded mode"

    # Restore (monkeypatch auto-restores, but be explicit for clarity)
    # monkeypatch fixture handles teardown automatically
