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


def test_tools_map_to_claude_code_names():
    assert agent_cc.allowed_tools(["read", "write", "grep"]) == ["Read", "Write", "Grep"]


def test_find_maps_to_glob():
    assert agent_cc.allowed_tools(["find"]) == ["Glob"]


def test_ls_and_bash_collapse_without_duplicating():
    # Both map to Bash; the allowlist must not repeat it.
    assert agent_cc.allowed_tools(["bash", "ls"]) == ["Bash"]


def test_none_means_every_tool():
    assert agent_cc.allowed_tools(None) is None


def test_a_pi_extension_tool_is_rejected_by_name():
    with pytest.raises(ValueError, match="subagent_create"):
        agent_cc.allowed_tools(["read", "subagent_create"])


def test_resolve_model_splits_provider_and_id():
    assert agent_cc.resolve_model("anthropic/claude-opus-5") == ("anthropic", "claude-opus-5")


def test_a_bare_pattern_is_rejected():
    with pytest.raises(ValueError, match="provider/model-id"):
        agent_cc.resolve_model("claude-opus-5")


def test_a_foreign_provider_is_rejected():
    with pytest.raises(ValueError, match="not served by"):
        agent_cc.resolve_model("openai/gpt-5.6-terra")


def test_a_missing_model_id_is_rejected():
    with pytest.raises(ValueError, match="no model-id after the slash"):
        agent_cc.resolve_model("anthropic/")


def test_a_whitespace_only_model_id_is_rejected():
    # Would otherwise reach the CLI as --model " " and fail with no mention
    # of which agent's config was wrong.
    with pytest.raises(ValueError, match="no model-id after the slash"):
        agent_cc.resolve_model("anthropic/ ")


def test_a_padded_model_id_is_stripped():
    assert agent_cc.resolve_model("anthropic/ claude-opus-5 ") == (
        "anthropic", "claude-opus-5")


def test_context_window_is_known_for_a_listed_model():
    assert agent_cc.context_window("anthropic", "claude-opus-5") == 1_000_000


def test_context_window_falls_back_for_an_unlisted_model():
    assert agent_cc.context_window("anthropic", "claude-future-9") == 200_000
