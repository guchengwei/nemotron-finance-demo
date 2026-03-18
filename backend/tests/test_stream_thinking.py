import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import _stream_split_thinking


async def _collect(source):
    results = []
    async for item in _stream_split_thinking(source):
        results.append(item)
    return results


async def _async_iter(chunks):
    for c in chunks:
        yield c


def collect(chunks):
    return asyncio.run(_collect(_async_iter(chunks)))


def test_plain_answer_no_thinking():
    chunks = ["Hello", " world"]
    result = collect(chunks)
    assert result == [("answer", "Hello"), ("answer", " world")]


def test_complete_think_then_answer():
    chunks = ["<think>", "reasoning", "</think>", "answer text"]
    result = collect(chunks)
    think_items = [(k, v) for k, v in result if k == "think"]
    answer_items = [(k, v) for k, v in result if k == "answer"]
    assert len(think_items) == 1
    assert "reasoning" in think_items[0][1]
    assert len(answer_items) >= 1


def test_unclosed_think_emits_thinking_content():
    """Stream ends inside <think> — content must NOT be silently dropped."""
    chunks = ["<think>", "partial thinking content"]
    # Stream ends without </think>
    result = collect(chunks)
    think_items = [v for k, v in result if k == "think"]
    assert len(think_items) == 1, "unclosed think block must emit a think event"
    assert "partial thinking content" in think_items[0]


def test_answer_after_think():
    chunks = ["<think>", "reason", "</think>", "final", " answer"]
    result = collect(chunks)
    answer_text = "".join(v for k, v in result if k == "answer")
    assert "final answer" in answer_text
