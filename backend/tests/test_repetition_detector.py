"""Unit tests for RepetitionDetector."""
import pytest
from repetition_detector import RepetitionDetector


def test_no_detection_on_normal_japanese_text():
    det = RepetitionDetector(ngram_size=8, threshold=4, window_chars=300)
    sentences = [
        "今日は天気が良くて、散歩に行きました。",
        "投資信託は長期的な資産形成に向いています。",
        "日本の株式市場は複雑な要因によって変動します。",
        "老後の資金準備は早めに始めることが重要です。",
        "分散投資によってリスクを低減することができます。",
    ]
    for s in sentences:
        result = det.feed(s)
    assert result is False


def test_detects_obvious_repetition_loop():
    det = RepetitionDetector(ngram_size=8, threshold=4, window_chars=300)
    chunk = "と思います。" * 20
    result = det.feed(chunk)
    assert result is True


def test_detects_gradual_repetition():
    det = RepetitionDetector(ngram_size=8, threshold=4, window_chars=300)
    varied = [
        "投資を始めるには証券口座の開設が必要です。",
        "リスク許容度に応じた商品選びが大切です。",
        "定期的な積立投資は時間分散効果があります。",
    ]
    fired = False
    for s in varied:
        if det.feed(s):
            fired = True
    assert not fired, "should not fire on varied text"

    # Now feed repetitive suffix
    repetitive = "なのでお勧めします。" * 10
    result = det.feed(repetitive)
    assert result is True


def test_no_false_positive_on_short_text():
    det = RepetitionDetector(ngram_size=8, threshold=4, window_chars=300)
    # Even with repeated phrase, if total < window_chars no detection
    result = det.feed("はい。はい。")
    assert result is False


def test_reset_clears_state():
    det = RepetitionDetector(ngram_size=8, threshold=4, window_chars=300)
    repetitive = "と思います。" * 20
    det.feed(repetitive)  # fills buffer
    det.reset()
    # After reset, same text should not immediately trigger (buffer is clear)
    result = det.feed("はい、わかりました。")
    assert result is False
