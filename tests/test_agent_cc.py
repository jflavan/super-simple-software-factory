"""The Claude Code backend: pure mappings first, subprocess wiring last."""

import pytest

from adw_modules import agent_cc


def test_thinking_off_sets_no_budget():
    assert agent_cc.thinking_env("off") == {}


def test_thinking_medium_sets_a_budget():
    assert agent_cc.thinking_env("medium") == {"MAX_THINKING_TOKENS": "10000"}


def test_thinking_max_sets_the_largest_budget():
    assert agent_cc.thinking_env("max") == {"MAX_THINKING_TOKENS": "64000"}


def test_unknown_thinking_level_is_rejected():
    with pytest.raises(ValueError, match="unknown thinking level"):
        agent_cc.thinking_env("ludicrous")


def test_apply_thinking_removes_an_inherited_budget_when_off():
    # The child env starts as a copy of the operator's, which may already
    # carry a budget. `off` must mean off regardless.
    env = {"PATH": "/usr/bin", "MAX_THINKING_TOKENS": "31337"}

    result = agent_cc.apply_thinking(env, "off")

    assert "MAX_THINKING_TOKENS" not in result
    assert result["PATH"] == "/usr/bin"


def test_apply_thinking_overrides_an_inherited_budget():
    env = {"MAX_THINKING_TOKENS": "31337"}

    result = agent_cc.apply_thinking(env, "high")

    assert result["MAX_THINKING_TOKENS"] == "24000"


def test_apply_thinking_sets_a_budget_on_a_clean_env():
    assert agent_cc.apply_thinking({}, "low") == {"MAX_THINKING_TOKENS": "4000"}


def test_apply_thinking_rejects_an_unknown_level():
    with pytest.raises(ValueError, match="unknown thinking level"):
        agent_cc.apply_thinking({}, "ludicrous")
