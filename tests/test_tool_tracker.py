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
