"""The Claude Code backend: pure mappings first, subprocess wiring last."""

import json
import pytest
import uuid as uuid_module

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


def test_first_send_mints_a_uuid_and_does_not_resume(tmp_path):
    minted, resume = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    assert resume is False
    uuid_module.UUID(minted)  # raises if it is not a real UUID


def test_a_later_send_reuses_the_same_uuid_and_resumes(tmp_path):
    first, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    second, resume = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    assert second == first
    assert resume is True


def test_two_agents_get_different_uuids(tmp_path):
    builder, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")
    planner, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-planner-1b3c")

    assert builder != planner


def test_a_corrupt_session_map_names_the_file(tmp_path):
    (tmp_path / "cc_sessions.json").write_text("{not json")

    with pytest.raises(RuntimeError, match="not valid JSON"):
        agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")


def test_a_corrupt_entry_fails_rather_than_silently_reissuing(tmp_path):
    # Minting a replacement here would start a new context window without
    # telling anyone — the precise failure this map exists to prevent.
    (tmp_path / "cc_sessions.json").write_text('{"sssf-abcd1234-builder-9f2a": ""}')

    with pytest.raises(RuntimeError, match="not a session id"):
        agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")


def test_a_null_entry_fails_too(tmp_path):
    (tmp_path / "cc_sessions.json").write_text('{"sssf-abcd1234-builder-9f2a": null}')

    with pytest.raises(RuntimeError, match="not a session id"):
        agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")


def test_the_write_leaves_no_temp_file_behind(tmp_path):
    agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    assert [p.name for p in tmp_path.iterdir()] == ["cc_sessions.json"]


def test_the_map_is_readable_by_a_later_call_from_the_file_alone(tmp_path):
    """The persistence claim, checked against the file rather than memory."""
    minted, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    on_disk = json.loads((tmp_path / "cc_sessions.json").read_text())

    assert on_disk == {"sssf-abcd1234-builder-9f2a": minted}
