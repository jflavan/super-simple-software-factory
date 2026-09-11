#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""Read the run trace without the sqlite3 CLI.

The CLI binary is not installed everywhere — it is absent on stock Windows —
so every cookbook line that shelled out to it failed on those machines. The
stdlib sqlite3 module always exists, and the db is WAL, so reads never block a
running ADW.

Usage:
    uv run adws/adw_trace.py sessions
    uv run adws/adw_trace.py phases <adw_id>
    uv run adws/adw_trace.py events <adw_id> [--type tool_call]
    uv run adws/adw_trace.py gates <adw_id>
    uv run adws/adw_trace.py processes
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = "adws/adw_data/sssf.db"


def _rows(db: str, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    # as_uri() rather than an f-string: a filesystem path is not a URI, and a
    # `#` in it starts a fragment — which silently opens a DIFFERENT, empty
    # database and surfaces later as "no such table" rather than as an error.
    uri = Path(db).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


CELL_CHARS = 160        # a scanning view; the full value is in the db and the artifacts


def _cell(value) -> str:
    """One row value, flattened to a single line so the table stays a table.

    A phase's `error` is routinely a traceback and `violations_json` is JSON —
    both carry newlines, and ljust() pads by character count while print emits
    the real break, so one multiline value corrupts the alignment of its row
    and every row after it.
    """
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text if len(text) <= CELL_CHARS else text[:CELL_CHARS - 1] + "…"


def _print(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("(no rows)")
        return
    columns = rows[0].keys()
    widths = [max(len(c), max(len(_cell(r[c])) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(_cell(row[c]).ljust(w) for c, w in zip(columns, widths)))


def main(argv: list[str] | None = None) -> int:
    # --db lives on a shared parent so it works after the subcommand (as every
    # caller here writes it, e.g. "sessions --db path") — argparse hands
    # anything after the subcommand token to that subparser, not the root one.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=DEFAULT_DB)

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sessions", parents=[common])
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

    if args.command == "sessions":
        _print(_rows(args.db,
                     "SELECT adw_id, adw_name, status, engineer, started_at, "
                     "total_tokens, total_cost FROM sessions "
                     "ORDER BY started_at DESC LIMIT 20"))
    elif args.command == "phases":
        _print(_rows(args.db,
                     "SELECT seq, name, kind, owner, status, attempt, description, error "
                     "FROM phases WHERE adw_id = ? ORDER BY seq", (args.adw_id,)))
    elif args.command == "events":
        if args.event_type:
            _print(_rows(args.db,
                         "SELECT type, name, tokens, started_at FROM events "
                         "WHERE adw_id = ? AND type = ? ORDER BY rowid",
                         (args.adw_id, args.event_type)))
        else:
            _print(_rows(args.db,
                         "SELECT type, name, tokens, started_at FROM events "
                         "WHERE adw_id = ? ORDER BY rowid", (args.adw_id,)))
    elif args.command == "gates":
        _print(_rows(args.db,
                     "SELECT gate, passed, attempt, violations_json FROM gate_results "
                     "WHERE adw_id = ? ORDER BY id", (args.adw_id,)))
    elif args.command == "processes":
        _print(_rows(args.db,
                     "SELECT adw_id, kind, name, pid, command, started_at, ended_at "
                     "FROM processes WHERE ended_at IS NULL ORDER BY started_at DESC"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
