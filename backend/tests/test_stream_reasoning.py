"""Tests for _stream_split_reasoning — vLLM reasoning-parser-based splitter.

With --reasoning-parser active, delta.reasoning holds thinking content and
delta.content holds the clean answer. This test module exercises all edge
cases described in the implementation plan.
"""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm import _stream_split_reasoning


def _make_chunk(reasoning=None, content=None):
    """Build a fake vLLM streaming chunk with the given delta fields."""
    delta = SimpleNamespace(reasoning=reasoning, reasoning_content=None, content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


def _make_chunk_compat(reasoning_content=None, content=None):
    """Build a chunk that uses reasoning_content (compat alias) instead of reasoning."""
    delta = SimpleNamespace(reasoning=None, reasoning_content=reasoning_content, content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


def _make_empty_chunk():
    """Final usage-only chunk with no choices."""
    return SimpleNamespace(choices=[])


async def _collect(chunks):
    results = []
    async def _raw():
        for c in chunks:
            yield c
    async for item in _stream_split_reasoning(_raw()):
        results.append(item)
    return results


def collect(chunks):
    return asyncio.run(_collect(chunks))


# ---------------------------------------------------------------------------
# Normal case: reasoning chunks followed by content chunks
# ---------------------------------------------------------------------------

def test_reasoning_then_content():
    chunks = [
        _make_chunk(reasoning="I should think about this."),
        _make_chunk(reasoning=" More reasoning."),
        _make_chunk(content="Final answer."),
    ]
    result = collect(chunks)
    think_items = [(k, v) for k, v in result if k == "think"]
    answer_items = [(k, v) for k, v in result if k == "answer"]

    assert len(think_items) == 1
    assert think_items[0][1] == "I should think about this. More reasoning."
    assert len(answer_items) == 1
    assert answer_items[0][1] == "Final answer."


# ---------------------------------------------------------------------------
# Transition chunk: reasoning and content appear in the same delta
# ---------------------------------------------------------------------------

def test_transition_chunk_both_fields():
    chunks = [
        _make_chunk(reasoning="reasoning part"),
        _make_chunk(reasoning="last thought", content="first answer token"),
        _make_chunk(content=" more answer"),
    ]
    result = collect(chunks)
    think_items = [(k, v) for k, v in result if k == "think"]
    answer_items = [(k, v) for k, v in result if k == "answer"]

    assert len(think_items) == 1
    assert "reasoning part" in think_items[0][1]
    assert "last thought" in think_items[0][1]
    answer_text = "".join(v for _, v in answer_items)
    assert "first answer token" in answer_text
    assert "more answer" in answer_text


# ---------------------------------------------------------------------------
# Partial transition boundary: first visible answer token must survive
# ---------------------------------------------------------------------------

def test_partial_transition_keeps_first_visible_answer_token():
    chunks = [
        _make_chunk(reasoning="still thinking"),
        _make_chunk(reasoning="final thought", content="Fi"),
        _make_chunk(content="rst answer token"),
    ]
    result = collect(chunks)
    answer_text = "".join(v for k, v in result if k == "answer")

    assert answer_text == "First answer token"


# ---------------------------------------------------------------------------
# Malformed parser transition must not leak reasoning markup into answer
# ---------------------------------------------------------------------------

def test_malformed_transition_strips_think_markup_from_answer():
    chunks = [
        _make_chunk(reasoning="internal reasoning"),
        _make_chunk(reasoning="more internal reasoning", content="</think>Visible answer"),
        _make_chunk(content=" continues cleanly"),
    ]
    result = collect(chunks)
    think_text = "".join(v for k, v in result if k == "think")
    answer_text = "".join(v for k, v in result if k == "answer")

    assert think_text == "internal reasoningmore internal reasoning"
    assert answer_text == "Visible answer continues cleanly"


# ---------------------------------------------------------------------------
# No reasoning at all (thinking disabled via enable_thinking=False)
# ---------------------------------------------------------------------------

def test_no_reasoning_only_content():
    chunks = [
        _make_chunk(content="Hello"),
        _make_chunk(content=" world"),
    ]
    result = collect(chunks)
    think_items = [(k, v) for k, v in result if k == "think"]
    answer_items = [(k, v) for k, v in result if k == "answer"]

    assert think_items == []
    assert len(answer_items) == 2
    assert answer_items[0] == ("answer", "Hello")
    assert answer_items[1] == ("answer", " world")


# ---------------------------------------------------------------------------
# Reasoning with no answer (generation truncated before answer)
# ---------------------------------------------------------------------------

def test_reasoning_no_answer():
    chunks = [
        _make_chunk(reasoning="thinking..."),
        _make_chunk(reasoning=" still thinking"),
    ]
    result = collect(chunks)
    think_items = [(k, v) for k, v in result if k == "think"]
    answer_items = [(k, v) for k, v in result if k == "answer"]

    assert len(think_items) == 1
    assert "thinking..." in think_items[0][1]
    assert answer_items == []


# ---------------------------------------------------------------------------
# Empty choices chunk (final usage-only chunk must not crash)
# ---------------------------------------------------------------------------

def test_empty_choices_chunk_ignored():
    chunks = [
        _make_chunk(reasoning="think"),
        _make_chunk(content="answer"),
        _make_empty_chunk(),  # must not raise
    ]
    result = collect(chunks)
    assert any(k == "think" for k, _ in result)
    assert any(k == "answer" for k, _ in result)


# ---------------------------------------------------------------------------
# reasoning_content field (compat alias) works when reasoning is absent
# ---------------------------------------------------------------------------

def test_reasoning_content_compat_field():
    chunks = [
        _make_chunk_compat(reasoning_content="compat reasoning"),
        _make_chunk_compat(content="compat answer"),
    ]
    result = collect(chunks)
    think_items = [(k, v) for k, v in result if k == "think"]
    answer_items = [(k, v) for k, v in result if k == "answer"]

    assert len(think_items) == 1
    assert think_items[0][1] == "compat reasoning"
    assert len(answer_items) == 1
    assert answer_items[0][1] == "compat answer"


# ---------------------------------------------------------------------------
# reasoning field preferred over reasoning_content when both are set
# ---------------------------------------------------------------------------

def test_reasoning_preferred_over_reasoning_content():
    """If both fields are set, reasoning (preferred) wins via 'or' short-circuit."""
    delta = SimpleNamespace(reasoning="preferred", reasoning_content="compat", content=None)
    choice = SimpleNamespace(delta=delta)
    chunk = SimpleNamespace(choices=[choice])

    result = collect([chunk, _make_chunk(content="ans")])
    think_text = "".join(v for k, v in result if k == "think")
    assert think_text == "preferred"
