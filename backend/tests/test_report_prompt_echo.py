# backend/tests/test_report_prompt_echo.py
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_mock_response(content: str):
    """Build a mock OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.reasoning_content = None
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


def test_group_tendency_returns_empty_on_echo():
    from prompts import REPORT_GROUP_TENDENCY_USER

    echoed = f"NISAの概要です。{REPORT_GROUP_TENDENCY_USER}"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"
        mock_settings.report_temperature = 0.1
        mock_settings.report_repetition_penalty = 1.15
        mock_settings.report_frequency_penalty = 0.3

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(echoed)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_group_tendency("shared system prompt")
            )

    assert result == "", f"Expected empty string for echoed response, got: {result!r}"


def test_conclusion_returns_empty_on_echo():
    from prompts import REPORT_CONCLUSION_INSTRUCTION

    tendency = "全体的に前向きです。"
    echoed = f"結論としては…{REPORT_CONCLUSION_INSTRUCTION}"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"
        mock_settings.report_temperature = 0.1
        mock_settings.report_repetition_penalty = 1.15
        mock_settings.report_frequency_penalty = 0.3

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(echoed)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_conclusion("shared system prompt", tendency)
            )

    assert result == "", f"Expected empty string for echoed response, got: {result!r}"


def test_group_tendency_passes_through_normal_response():
    """A legitimate analytical response should be returned as-is, not rejected."""
    normal = "全体として、NISA制度に対する関心は高く、特に非課税期間の無期限化が支持されています。一方、制度の複雑さに対する不安も見られます。"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"
        mock_settings.report_temperature = 0.1
        mock_settings.report_repetition_penalty = 1.15
        mock_settings.report_frequency_penalty = 0.3

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(normal)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_group_tendency("shared system prompt")
            )

    assert result == normal, f"Expected normal response to pass through, got: {result!r}"


def test_conclusion_passes_through_normal_response():
    """A legitimate conclusion should be returned as-is."""
    tendency = "全体的に前向きです。"
    normal = "総合すると、NISA制度の改正は概ね好意的に受け止められており、金融機関は制度周知の強化と個別相談の充実が求められます。"

    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"
        mock_settings.report_temperature = 0.1
        mock_settings.report_repetition_penalty = 1.15
        mock_settings.report_frequency_penalty = 0.3

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(normal)
        )

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_conclusion("shared system prompt", tendency)
            )

    assert result == normal, f"Expected normal response to pass through, got: {result!r}"


def test_group_tendency_returns_empty_on_null_content():
    """When reasoning parser misroutes content to reasoning_content,
    message.content is None. Should return empty string for fallback."""
    with patch("llm.settings") as mock_settings:
        mock_settings.mock_llm = False
        mock_settings.vllm_model = "test-model"
        mock_settings.report_temperature = 0.1
        mock_settings.report_repetition_penalty = 1.15
        mock_settings.report_frequency_penalty = 0.3

        msg = MagicMock()
        msg.content = None
        msg.reasoning_content = "実際の分析結果がここに入る"
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = None

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=resp)

        with patch("llm.get_client", return_value=mock_client):
            import llm
            result = asyncio.run(
                llm.generate_report_group_tendency("shared system prompt")
            )

    assert result == "", f"Expected empty string when content is None, got: {result!r}"
