"""Both backends normalize their tool streams to the same record shape."""

from adw_modules import agent_pi


def test_pi_tracker_returns_a_list_with_one_finished_call():
    tracker = agent_pi.ToolCallTracker()

    tracker.observe({"type": "tool_execution_start", "toolCallId": "t1",
                     "toolName": "bash", "args": {"command": "ls -la"}})
    records = tracker.observe({
        "type": "tool_execution_end", "toolCallId": "t1", "toolName": "bash",
        "args": {"command": "ls -la"}, "isError": False,
        "result": {"content": [{"type": "text", "text": "total 0"}]},
    })

    assert isinstance(records, list)
    assert len(records) == 1
    assert records[0]["tool"] == "bash"
    assert records[0]["ok"] is True
    assert records[0]["label"] == "bash: ls -la"


def test_pi_tracker_returns_an_empty_list_for_an_unrelated_event():
    tracker = agent_pi.ToolCallTracker()

    assert tracker.observe({"type": "message_start"}) == []


def test_pi_tracker_returns_a_list_for_a_message_end_event():
    """The one branch of pi's observe() that its own tests never reach.

    It announces toolCall blocks and returns nothing — but it must return an
    empty LIST, because agents._event_forwarder now iterates the result.
    """
    tracker = agent_pi.ToolCallTracker()

    result = tracker.observe({"type": "message_end", "message": {"content": [
        {"type": "toolCall", "id": "t1", "name": "bash", "arguments": {"command": "ls"}},
    ]}})

    assert result == []


from adw_modules import agent_cc


def test_cc_tracker_pairs_a_tool_use_with_its_result():
    tracker = agent_cc.CcToolCallTracker()

    opened = tracker.observe({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": "toolu_1", "name": "Bash",
         "input": {"command": "dotnet build"}},
    ]}})
    closed = tracker.observe({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "toolu_1", "is_error": False,
         "content": [{"type": "text", "text": "Build succeeded."}]},
    ]}})

    assert opened == []
    assert len(closed) == 1
    record = closed[0]
    assert record["tool"] == "Bash"
    assert record["tool_call_id"] == "toolu_1"
    assert record["ok"] is True
    assert record["label"] == "Bash: dotnet build"
    assert record["result_snippet"] == "Build succeeded."
    assert record["args"] == {"command": "dotnet build"}
    assert "started_at" in record and "ended_at" in record


def test_cc_tracker_closes_several_results_in_one_message():
    tracker = agent_cc.CcToolCallTracker()

    tracker.observe({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "a", "name": "Read", "input": {"file_path": "x.cs"}},
        {"type": "tool_use", "id": "b", "name": "Read", "input": {"file_path": "y.cs"}},
    ]}})
    closed = tracker.observe({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "a", "content": "x"},
        {"type": "tool_result", "tool_use_id": "b", "content": "y"},
    ]}})

    assert [r["tool_call_id"] for r in closed] == ["a", "b"]


def test_cc_tracker_marks_an_error_result():
    tracker = agent_cc.CcToolCallTracker()

    tracker.observe({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "false"}},
    ]}})
    closed = tracker.observe({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "t", "is_error": True, "content": "boom"},
    ]}})

    assert closed[0]["ok"] is False


def test_cc_tracker_ignores_unrelated_events():
    tracker = agent_cc.CcToolCallTracker()

    assert tracker.observe({"type": "system", "subtype": "init"}) == []


def test_cc_tracker_keeps_the_first_sighting_of_a_call(monkeypatch):
    """A second announcement must not restart the clock.

    Overwriting would reset started_at and understate duration_ms. pi's
    tracker merges for the same reason.

    now_iso() has millisecond precision, so two calls in quick succession can
    return the same string by chance and let an unconditional-overwrite bug
    pass undetected. now_iso is monkeypatched to return successive distinct
    values so the assertion is deterministic rather than a sleep-based timing
    check.
    """
    values = iter(["2020-01-01T00:00:00.000Z", "2020-01-01T00:00:00.999Z"])
    monkeypatch.setattr(agent_cc, "now_iso", lambda: next(values))
    tracker = agent_cc.CcToolCallTracker()

    tracker.observe({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "sleep"}},
    ]}})
    first_seen = tracker._open["t"]["started_at"]
    tracker.observe({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "sleep"}},
    ]}})

    assert tracker._open["t"]["started_at"] == first_seen
