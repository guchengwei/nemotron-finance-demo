# backend/tests/test_echo_detection.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import detect_prompt_echo
from prompts import REPORT_CONCLUSION_INSTRUCTION


SAMPLE_PROMPT = "集計結果を踏まえ、グループ全体の傾向を簡潔に述べてください。テキストのみ。JSONや説明文は不要です。"

CONCLUSION_PROMPT = "上記を踏まえ、総合結論・金融機関が取るべき推奨アクションを詳しく述べてください。テキストのみ。JSONや説明文は不要です。"


def test_detects_exact_echo():
    """Response that IS the prompt verbatim."""
    assert detect_prompt_echo(SAMPLE_PROMPT, SAMPLE_PROMPT) is True


def test_detects_echo_embedded_in_response():
    """Response contains the prompt text within other content."""
    response = f"NISA制度は好評です。ただし、…\n\n{CONCLUSION_PROMPT}"
    assert detect_prompt_echo(CONCLUSION_PROMPT, response) is True


def test_allows_legitimate_response():
    """Normal analytical response should NOT be flagged."""
    response = "全体として、NISA制度に対する関心は高く、特に非課税期間の無期限化が支持されています。一方、制度の複雑さに対する不安も見られます。"
    assert detect_prompt_echo(SAMPLE_PROMPT, response) is False


def test_allows_short_overlap():
    """Small keyword overlap (e.g. 'テキスト') is not an echo."""
    response = "テキストマイニングの結果、前向きな意見が多数を占めています。"
    assert detect_prompt_echo(SAMPLE_PROMPT, response) is False


def test_handles_empty_strings():
    assert detect_prompt_echo("", "") is False
    assert detect_prompt_echo(SAMPLE_PROMPT, "") is False
    assert detect_prompt_echo("", "some response") is False


def test_detects_partial_prompt_echo():
    """Response contains a large contiguous chunk of the prompt."""
    # Take 80% of the prompt as a chunk
    chunk = CONCLUSION_PROMPT[:int(len(CONCLUSION_PROMPT) * 0.8)]
    response = f"NISA制度は…{chunk}"
    assert detect_prompt_echo(CONCLUSION_PROMPT, response) is True


def test_prompt_shorter_than_min_chunk_returns_false():
    """Prompt shorter than min_chunk cannot produce a valid match window."""
    short_prompt = "短い"  # 2 chars, well below default min_chunk=20
    response = "短い短い短い短い短い分析結果です。"
    assert detect_prompt_echo(short_prompt, response) is False


def test_conclusion_reusing_tendency_is_not_echo():
    """A conclusion that legitimately references the group tendency should NOT be flagged.
    Echo detection for conclusion uses REPORT_CONCLUSION_INSTRUCTION (static only),
    not the full user_content which includes the dynamic group_tendency."""
    # Conclusion legitimately reuses words from the tendency
    response = "全体的にNISA制度への関心は高く、非課税期間の無期限化が支持されています。金融機関は制度周知の強化が求められます。"
    assert detect_prompt_echo(REPORT_CONCLUSION_INSTRUCTION, response) is False
