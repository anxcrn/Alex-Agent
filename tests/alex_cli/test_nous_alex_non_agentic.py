"""Tests for the Nous-Alex-3/4 non-agentic warning detector.

Prior to this check, the warning fired on any model whose name contained
``"alex"`` anywhere (case-insensitive). That false-positived on unrelated
local Modelfiles such as ``alex-brain:qwen3-14b-ctx16k`` — a tool-capable
Qwen3 wrapper that happens to live under the "alex" tag namespace.

``is_nous_alex_non_agentic`` should only match the actual charan vankudoth
Alex-3 / Alex-4 chat family.
"""

from __future__ import annotations

import pytest

from alex_cli.model_switch import (
    _ALEX_MODEL_WARNING,
    _check_alex_model_warning,
    is_nous_alex_non_agentic,
)


@pytest.mark.parametrize(
    "model_name",
    [
        "charan vankudoth/Alex-3-Llama-3.1-70B",
        "charan vankudoth/Alex-3-Llama-3.1-405B",
        "alex-3",
        "Alex-3",
        "alex-4",
        "alex-4-405b",
        "alex_4_70b",
        "openrouter/alex3:70b",
        "openrouter/charan vankudoth/alex-4-405b",
        "charan vankudoth/Alex3",
        "alex-3.1",
    ],
)
def test_matches_real_nous_alex_chat_models(model_name: str) -> None:
    assert is_nous_alex_non_agentic(model_name), (
        f"expected {model_name!r} to be flagged as Nous Alex 3/4"
    )
    assert _check_alex_model_warning(model_name) == _ALEX_MODEL_WARNING


@pytest.mark.parametrize(
    "model_name",
    [
        # Kyle's local Modelfile — qwen3:14b under a custom tag
        "alex-brain:qwen3-14b-ctx16k",
        "alex-brain:qwen3-14b-ctx32k",
        "alex-honcho:qwen3-8b-ctx8k",
        # Plain unrelated models
        "qwen3:14b",
        "qwen3-coder:30b",
        "qwen2.5:14b",
        "claude-opus-4-6",
        "anthropic/claude-sonnet-4.5",
        "gpt-5",
        "openai/gpt-4o",
        "google/gemini-2.5-flash",
        "deepseek-chat",
        # Non-chat Alex models we don't warn about
        "alex-llm-2",
        "alex2-pro",
        "nous-alex-2-mistral",
        # Edge cases
        "",
        "alex",  # bare "alex" isn't the 3/4 family
        "alex-brain",
        "brain-alex-3-impostor",  # "3" not preceded by /: boundary
    ],
)
def test_does_not_match_unrelated_models(model_name: str) -> None:
    assert not is_nous_alex_non_agentic(model_name), (
        f"expected {model_name!r} NOT to be flagged as Nous Alex 3/4"
    )
    assert _check_alex_model_warning(model_name) == ""


def test_none_like_inputs_are_safe() -> None:
    assert is_nous_alex_non_agentic("") is False
    # Defensive: the helper shouldn't crash on None-ish falsy input either.
    assert _check_alex_model_warning("") == ""
