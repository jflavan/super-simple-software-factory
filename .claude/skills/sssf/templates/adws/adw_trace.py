#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""Read the run trace without the sqlite3 CLI.

The CLI binary is not installed everywhere — it is absent on stock Windows —
so every cookbook line that shelled out to it failed on those machines. The
stdlib sqlite3 module always exists, and the db is WAL, so reads never block a
running ADW.

Long cell values (a traceback, a JSON blob) are flattened to one line and
truncated past CELL_CHARS so the table stays aligned; pass --full to disable
truncation and see the whole value.

Usage:
    uv run adws/adw_trace.py sessions [--limit 20]
    uv run adws/adw_trace.py phases <adw_id>
    uv run adws/adw_trace.py events <adw_id> [--type tool_call]
    uv run adws/adw_trace.py gates <adw_id>
    uv run adws/adw_trace.py processes
    uv run adws/adw_trace.py <command> --full   # do not truncate long cells
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "adws/adw_data/sssf.db"


def _make_stdout_unable_to_kill_a_report() -> None:
    """Deliberately a copy of `console.make_stdout_unable_to_kill_a_run`.

    Everything this prints is agent-authored free text - a phase description, a
    gate violation, an error - and agents write arrow and check glyphs
    constantly. Redirected to a cp1252 stream (a pipe, a CI log, `> file`) an
    unencodable one raised UnicodeEncodeError and took the whole report down,
    which is the worst possible moment: this is the tool an operator reaches
    for AFTER something has already gone wrong.

    Not imported from adw_modules because this file declares
    `dependencies = []` and means it - it is the one tool that has to work on a
    machine where nothing else does, including one with no sqlite3 CLI and no
    third-party packages installed. `adw_modules.utils` pulls in dotenv. Four
    duplicated lines are the cheaper of the two prices, and a test pins the two
    copies to the same behaviour.
    """
    try:
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass


class TraceUnreadable(RuntimeError):
    """The file is there but cannot be read as a trace."""


def _rows(db: str, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    # as_uri() rather than an f-string: a filesystem path is not a URI, and a
    # `#` in it starts a fragment — which silently opens a DIFFERENT, empty
    # database and surfaces later as "no such table" rather than as an error.
    uri = Path(db).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchall()
    except sqlite3.OperationalError as error:
        raise TraceUnreadable(
            f"{db} is a database, but not an SSSF trace ({error}) — check the "
            f"path, or run an ADW to create one") from error
    except sqlite3.DatabaseError as error:
        raise TraceUnreadable(f"{db} is not a readable SQLite database ({error})") from error
    finally:
        connection.close()


CELL_CHARS = 400        # enough for a flattened traceback to keep its exception
                        # type and message; --full disables truncation entirely


def _cell(value, limit: int) -> str:
    """One row value, flattened to a single line so the table stays a table.

    Flattening is not optional: ljust() pads by character count while print
    emits a real newline, so one multiline value corrupts its row and every row
    after it. Truncation IS optional, and off with --full — a phase's `error`
    is usually the whole reason someone is reading this, and cutting it mid
    exception-type answers nothing.
    """
    if value is None:
        return ""
    text = " ".join(str(value).split())
    if limit and len(text) > limit:
        return text[:limit - 1] + "…"
    return text


def _print(rows: list[sqlite3.Row], limit: int) -> None:
    if not rows:
        print("(no rows)")
        return
    columns = rows[0].keys()
    widths = [max(len(c), max(len(_cell(r[c], limit)) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(_cell(row[c], limit).ljust(w) for c, w in zip(columns, widths)))


def main(argv: list[str] | None = None) -> int:
    _make_stdout_unable_to_kill_a_report()
    # --db lives on a shared parent so it works after the subcommand (as every
    # caller here writes it, e.g. "sessions --db path") — argparse hands
    # anything after the subcommand token to that subparser, not the root one.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=DEFAULT_DB)
    common.add_argument("--full", action="store_true",
                        help="do not truncate long cell values")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sessions = sub.add_parser("sessions", parents=[common])
    sessions.add_argument("--limit", type=int, default=20)
    for name in ("phases", "gates"):
        p = sub.add_parser(name, parents=[common])
        p.add_argument("adw_id")
    events = sub.add_parser("events", parents=[common])
    events.add_argument("adw_id")
    events.add_argument("--type", dest="event_type", default=None)
    sub.add_parser("processes", parents=[common])

    args = parser.parse_args(argv)
    if not Path(args.db).exists():
        print(f"no trace database at {args.db} — has an ADW run yet?")
        return 1

    cell_limit = 0 if args.full else CELL_CHARS
    try:
        if args.command == "sessions":
            _print(_rows(args.db,
                         "SELECT adw_id, adw_name, status, engineer, started_at, "
                         "total_tokens, total_cost FROM sessions "
                         "ORDER BY started_at DESC LIMIT ?", (args.limit,)), cell_limit)
        elif args.command == "phases":
            _print(_rows(args.db,
                         "SELECT seq, name, kind, owner, status, attempt, description, error "
                         "FROM phases WHERE adw_id = ? ORDER BY seq", (args.adw_id,)), cell_limit)
        elif args.command == "events":
            if args.event_type:
                _print(_rows(args.db,
                             "SELECT type, name, tokens, started_at FROM events "
                             "WHERE adw_id = ? AND type = ? ORDER BY rowid",
                             (args.adw_id, args.event_type)), cell_limit)
            else:
                _print(_rows(args.db,
                             "SELECT type, name, tokens, started_at FROM events "
                             "WHERE adw_id = ? ORDER BY rowid", (args.adw_id,)), cell_limit)
        elif args.command == "gates":
            _print(_rows(args.db,
                         "SELECT gate, passed, attempt, violations_json FROM gate_results "
                         "WHERE adw_id = ? ORDER BY id", (args.adw_id,)), cell_limit)
        elif args.command == "processes":
            _print(_rows(args.db,
                         "SELECT adw_id, kind, name, pid, command, started_at, ended_at "
                         "FROM processes WHERE ended_at IS NULL ORDER BY started_at DESC"),
                   cell_limit)
    except TraceUnreadable as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
