"""The Claude Code backend: pure mappings first, subprocess wiring last."""

import json
import pytest
import uuid as uuid_module

from adw_modules import agent_cc
from adw_modules.data_types import AgentRequest


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


def test_apply_thinking_leaves_the_env_alone_when_the_level_is_bad():
    env = {"MAX_THINKING_TOKENS": "31337"}

    with pytest.raises(ValueError, match="unknown thinking level"):
        agent_cc.apply_thinking(env, "ludicrous")

    assert env["MAX_THINKING_TOKENS"] == "31337", "a failed call must not mutate"


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


def _request(**overrides) -> AgentRequest:
    defaults = dict(
        prompt="do the thing",
        system_prompt="you are a builder",
        model="anthropic/claude-opus-5",
        thinking="medium",
        session_id="sssf-abcd1234-builder-9f2a",
        session_dir="/tmp/sessions",
        raw_output_path="/tmp/raw.jsonl",
        tools=["read", "bash"],
        extensions=[],
        cwd="/repo",
    )
    defaults.update(overrides)
    return AgentRequest(**defaults)


def test_command_creates_a_session_on_the_first_send():
    cmd = agent_cc.build_command(_request(), "11111111-2222-3333-4444-555555555555",
                                 resume=False)

    assert "--session-id" in cmd
    assert "--resume" not in cmd
    assert cmd[cmd.index("--session-id") + 1] == "11111111-2222-3333-4444-555555555555"


def test_command_resumes_on_a_later_send():
    cmd = agent_cc.build_command(_request(), "11111111-2222-3333-4444-555555555555",
                                 resume=True)

    assert "--resume" in cmd
    assert "--session-id" not in cmd


def test_command_carries_model_tools_and_prompt():
    cmd = agent_cc.build_command(_request(), "11111111-2222-3333-4444-555555555555",
                                 resume=False)

    assert cmd[cmd.index("--model") + 1] == "claude-opus-5"
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Bash"
    assert cmd[-1] == "do the thing", "the prompt is the final positional argument"
    assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "stream-json"


def test_no_tools_key_means_no_allowlist_flag():
    cmd = agent_cc.build_command(_request(tools=None),
                                 "11111111-2222-3333-4444-555555555555", resume=False)

    assert "--allowedTools" not in cmd


def test_an_empty_tool_list_is_not_the_same_as_no_tools_key():
    """`None` means every tool; `[]` means none. They must not collapse.

    config.md states an empty list "is not 'all tools' — it is a tool-less
    agent". A truthiness test would silently grant the full set instead.
    """
    every = agent_cc.build_command(_request(tools=None),
                                   "11111111-2222-3333-4444-555555555555", resume=False)
    none_at_all = agent_cc.build_command(_request(tools=[]),
                                         "11111111-2222-3333-4444-555555555555", resume=False)

    assert "--allowedTools" not in every
    assert "--allowedTools" in none_at_all


class FakeProcess:
    """Stands in for a Popen handle: an iterable stdout and a return code."""

    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.stderr = _FakeStderr()
        self.pid = 4242
        self._returncode = returncode
        self.killed = False

    def wait(self):
        return self._returncode

    def kill(self):
        self.killed = True


class _FakeStderr:
    @staticmethod
    def read():
        return ""


def _stream(*events):
    return [json.dumps(event) + "\n" for event in events]


def test_run_collects_text_cost_and_tokens(tmp_path, monkeypatch):
    events = _stream(
        {"type": "system", "subtype": "init", "session_id": "x"},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "working"}],
            "usage": {"input_tokens": 100, "output_tokens": 20}}},
        {"type": "result", "subtype": "success", "result": '{"status": "success"}',
         "total_cost_usd": 0.0123, "usage": {"input_tokens": 100, "output_tokens": 20}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))

    result = agent_cc.run(_request(session_dir=str(tmp_path),
                                   raw_output_path=str(tmp_path / "raw.jsonl")))

    assert result.text == '{"status": "success"}'
    assert result.cost == pytest.approx(0.0123)
    assert result.tokens == 120
    assert result.returncode == 0


def test_run_writes_the_raw_stream_to_disk(tmp_path, monkeypatch):
    events = _stream({"type": "result", "subtype": "success", "result": "done",
                      "total_cost_usd": 0.0, "usage": {}})
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))
    raw = tmp_path / "raw.jsonl"

    agent_cc.run(_request(session_dir=str(tmp_path), raw_output_path=str(raw)))

    assert raw.exists()
    assert "result" in raw.read_text()


def test_run_forwards_events_to_the_callback(tmp_path, monkeypatch):
    events = _stream(
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_path": "a.cs"}}]}},
        {"type": "result", "subtype": "success", "result": "ok",
         "total_cost_usd": 0.0, "usage": {}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))
    seen = []

    agent_cc.run(_request(session_dir=str(tmp_path),
                          raw_output_path=str(tmp_path / "raw.jsonl")),
                 on_event=seen.append)

    assert [event["type"] for event in seen] == ["assistant", "result"]


def test_run_reports_spawn_and_exit(tmp_path, monkeypatch):
    events = _stream({"type": "result", "subtype": "success", "result": "ok",
                      "total_cost_usd": 0.0, "usage": {}})
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))
    spawned, exited = [], []

    agent_cc.run(_request(session_dir=str(tmp_path),
                          raw_output_path=str(tmp_path / "raw.jsonl")),
                 on_spawn=spawned.append, on_exit=exited.append)

    assert spawned == [4242]
    assert exited == [4242]


def test_run_raises_when_the_agent_fails_with_no_output(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess([], returncode=1))

    with pytest.raises(RuntimeError, match="claude exited 1"):
        agent_cc.run(_request(session_dir=str(tmp_path),
                              raw_output_path=str(tmp_path / "raw.jsonl")))


def test_run_fills_the_usage_breakdown(tmp_path, monkeypatch):
    # agents.execute reports the PHASE total from result.usage, not from
    # result.tokens. An empty breakdown would log 0 tokens for the phase while
    # the run banner showed the right number — two numbers disagreeing in the
    # same trace.
    events = _stream(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}],
         "usage": {"input_tokens": 100, "output_tokens": 20,
                   "cache_read_input_tokens": 7, "cache_creation_input_tokens": 3}}},
        {"type": "result", "subtype": "success", "result": "done",
         "total_cost_usd": 0.5, "usage": {}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))

    result = agent_cc.run(_request(session_dir=str(tmp_path),
                                   raw_output_path=str(tmp_path / "raw.jsonl")))

    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.usage.cache_read_tokens == 7
    assert result.usage.cache_write_tokens == 3
    assert result.usage.total_tokens == 120
    assert result.usage.total_cost == pytest.approx(0.5)


def test_run_rejects_a_non_success_terminal_subtype(tmp_path, monkeypatch):
    """A max-turns exhaustion must not be reported as a JSON problem."""
    events = _stream(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "..."}],
         "usage": {"input_tokens": 10, "output_tokens": 1}}},
        {"type": "result", "subtype": "error_max_turns", "total_cost_usd": 0.02,
         "usage": {}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))

    with pytest.raises(RuntimeError, match="error_max_turns"):
        agent_cc.run(_request(session_dir=str(tmp_path),
                              raw_output_path=str(tmp_path / "raw.jsonl")))


def test_run_accepts_an_explicit_success_subtype(tmp_path, monkeypatch):
    events = _stream({"type": "result", "subtype": "success", "result": "done",
                      "total_cost_usd": 0.0, "usage": {}})
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))

    assert agent_cc.run(_request(session_dir=str(tmp_path),
                                 raw_output_path=str(tmp_path / "raw.jsonl"))).text == "done"


def test_run_reaps_the_child_when_a_callback_raises(tmp_path, monkeypatch):
    """An exception mid-stream must not leave the child alive and untracked."""
    events = _stream({"type": "assistant", "message": {"content": []}},
                     {"type": "result", "subtype": "success", "result": "ok",
                      "total_cost_usd": 0.0, "usage": {}})
    process = FakeProcess(events)
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: process)
    exited = []

    def boom(event):
        raise ValueError("callback failed")

    with pytest.raises(ValueError, match="callback failed"):
        agent_cc.run(_request(session_dir=str(tmp_path),
                              raw_output_path=str(tmp_path / "raw.jsonl")),
                     on_event=boom, on_exit=exited.append)

    assert process.killed is True, "the child must be killed, not left to the collector"
    assert exited == [4242], "the tracer must learn the pid is gone"
