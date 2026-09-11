"""The trace reader, against a database built from the real schema."""

import sqlite3
import sys
from pathlib import Path

import pytest

TRACE_DIR = (Path(__file__).resolve().parent.parent
             / ".claude" / "skills" / "sssf" / "templates" / "adws")
sys.path.insert(0, str(TRACE_DIR))

import adw_trace  # noqa: E402
from adw_modules.tracer import SCHEMA  # noqa: E402


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "sssf.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO sessions (adw_id, adw_name, request, status, engineer, "
        "started_at, total_tokens, total_cost) VALUES (?,?,?,?,?,?,?,?)",
        ("a1b2c3d4", "adw_scout", "find the auth code", "success", "john",
         "2026-09-10T10:00:00Z", 1234, 0.05))
    conn.execute(
        "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, "
        "description, status) VALUES (?,?,?,?,?,?,?,?)",
        ("a1b2c3d4_01_scout", "a1b2c3d4", 1, "scout", "agent", "scout",
         "Find where things live", "success"))
    conn.execute(
        "INSERT INTO events (event_id, adw_id, phase_id, type, name, payload_json) "
        "VALUES (?,?,?,?,?,?)",
        ("e1", "a1b2c3d4", "a1b2c3d4_01_scout", "tool_call", "Read: x.cs", "{}"))
    conn.commit()
    conn.close()
    return path


def test_sessions_lists_the_run(db, capsys):
    adw_trace.main(["sessions", "--db", str(db)])

    out = capsys.readouterr().out
    assert "a1b2c3d4" in out
    assert "success" in out


def test_phases_lists_phases_for_one_run(db, capsys):
    adw_trace.main(["phases", "a1b2c3d4", "--db", str(db)])

    out = capsys.readouterr().out
    assert "scout" in out
    assert "Find where things live" in out


def test_events_can_filter_by_type(db, capsys):
    adw_trace.main(["events", "a1b2c3d4", "--type", "tool_call", "--db", str(db)])

    out = capsys.readouterr().out
    assert "Read: x.cs" in out


def test_events_filtering_an_absent_type_prints_nothing_of_substance(db, capsys):
    adw_trace.main(["events", "a1b2c3d4", "--type", "gate_fail", "--db", str(db)])

    assert "Read: x.cs" not in capsys.readouterr().out


def test_a_missing_database_is_reported_not_crashed(tmp_path, capsys):
    code = adw_trace.main(["sessions", "--db", str(tmp_path / "nope.db")])

    assert code == 1
    assert "no trace database" in capsys.readouterr().out


def test_a_multiline_error_does_not_break_the_table(tmp_path, capsys):
    """A traceback in `error` is the normal content of a failed phase."""
    path = tmp_path / "sssf.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, "
        "description, status, error) VALUES (?,?,?,?,?,?,?,?,?)",
        ("p1", "a1", 1, "build", "agent", "builder", "Implement it", "fail",
         "Traceback (most recent call last):\n  File x\n    boom\nValueError: bad"))
    conn.commit()
    conn.close()

    adw_trace.main(["phases", "a1", "--db", str(path)])

    out = capsys.readouterr().out
    body = [line for line in out.splitlines() if line.strip()]
    # header + dashes + exactly one data row — a raw newline would make more.
    assert len(body) == 3, f"the table gained rows from an embedded newline: {body}"
    assert "ValueError: bad" in out


def test_a_path_containing_a_hash_is_read_correctly(tmp_path, capsys):
    """A filesystem path is not a URI: `#` would start a fragment."""
    awkward = tmp_path / "trace#1"
    awkward.mkdir()
    path = awkward / "sssf.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO sessions (adw_id, status) VALUES (?,?)", ("hashy", "success"))
    conn.commit()
    conn.close()

    assert adw_trace.main(["sessions", "--db", str(path)]) == 0
    assert "hashy" in capsys.readouterr().out
