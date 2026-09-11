"""Validation gates: verify the envelope's CLAIMS, never guesses.

A gate is `gate(envelope, run) -> GateReport` — one check per item it looked at.
Violations are derived from the failed checks and sent back to the SAME agent
session as a correction. Every check is recorded either way, so a green gate
says WHAT it verified instead of only that it passed.

Gates check what is mechanically checkable; plan quality is a reviewer's job.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from .data_types import EnvelopeBase, GateReport
from .utils import claimed_files, path_matches

TAIL_CHARS = 1000        # command output kept as evidence on a failure


def _size(path: Path) -> str:
    n = path.stat().st_size
    return f"{n}B" if n < 1024 else f"{n / 1024:.1f}KB"


def artifacts_exist(envelope: EnvelopeBase, run) -> GateReport:
    report = GateReport()
    for a in envelope.artifacts:
        p = Path(a)
        report.check(a, p.exists(),
                     f"exists, {_size(p)}" if p.exists() else "declared artifact does not exist")
    return report


def files_non_empty(envelope: EnvelopeBase, run) -> GateReport:
    report = GateReport()
    for a in envelope.artifacts:
        p = Path(a)
        if not (p.exists() and p.is_file()):
            continue                       # existence is artifacts_exist's job
        empty = p.stat().st_size == 0
        report.check(a, not empty, "declared artifact is empty" if empty else _size(p))
    return report


def json_parses(envelope: EnvelopeBase, run) -> GateReport:
    report = GateReport()
    for a in envelope.artifacts:
        p = Path(a)
        if p.suffix != ".json" or not p.exists():
            continue
        try:
            parsed = json.loads(p.read_text(encoding="utf-8"))
            report.check(a, True, f"parses, {type(parsed).__name__}")
        except json.JSONDecodeError as e:
            report.check(a, False, f"declared JSON artifact does not parse: {e}")
    return report


def diff_matches_claims(envelope: EnvelopeBase, run) -> GateReport:
    """Every file claimed changed must exist on disk."""
    report = GateReport()
    for f in getattr(envelope, "changed_files", []):
        p = Path(f)
        report.check(f, p.exists(),
                     f"exists, {_size(p)}" if p.exists() else "claimed changed file does not exist")
    return report


def verdict_consistent(envelope: EnvelopeBase, run) -> GateReport:
    """A review's verdict must agree with the findings it just wrote down.

    Nothing here judges the code — that is the reviewer's job. This checks the
    envelope against itself: an approval that ships blocking items, or a
    rejection that names no problem, is a claim the harness can refute without
    reading a line of the diff.
    """
    report = GateReport()
    approved = bool(getattr(envelope, "approved", False))
    blocking = list(getattr(envelope, "blocking", []))
    unmet = [f.requirement for f in getattr(envelope, "findings", []) if not f.met]

    report.check("approved vs blocking", not (approved and blocking),
                 "no blocking items" if not blocking
                 else f"{len(blocking)} blocking item(s) while approved=true"
                 if approved else f"{len(blocking)} blocking item(s), not approved")
    report.check("approved vs findings", not (approved and unmet),
                 "every requirement met" if not unmet
                 else f"{len(unmet)} unmet requirement(s) while approved=true"
                 if approved else f"{len(unmet)} unmet requirement(s), not approved")
    report.check("rejection names a problem", approved or bool(blocking or unmet),
                 "verdict is supported" if approved or blocking or unmet
                 else "approved=false but no blocking item or unmet requirement was given")
    return report


def tests_pass(command: str):
    """Gate factory: the given shell command must exit 0."""
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        result = subprocess.run(command, shell=True, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        ok = result.returncode == 0
        note = f"exit {result.returncode}"
        if not ok:
            note += "\n" + (result.stdout + result.stderr)[-TAIL_CHARS:]
        return GateReport().check(command, ok, note)
    gate.__name__ = f"tests_pass({command})"
    return gate


def doc_policy(envelope: EnvelopeBase, run) -> GateReport:
    """The repo's documentation contract, as declared in sssf.config.yaml.

    Config-driven on purpose: every repository's contract is different, and a
    contract written as code is a contract only a programmer may change. This
    gate reads YAML and compares paths — the policy itself never becomes code.

    Silent when no rule triggers. A gate that records a check per rule per run
    would bury the one violation that matters under a hundred green lines.

    Judges the envelope's CLAIMS, like every gate here. An agent that omits a
    file from `changed_files` is not caught by this — `permissions.enforce`
    sees the real diff, but it runs after the gates and only checks what an
    agent may WRITE, not what it admitted to. A documentation contract is a
    prompt-level nudge with a mechanical check behind it, not a proof.
    """
    report = GateReport()
    changed = claimed_files(envelope, run)
    for rule in getattr(run.cfg, "doc_policy", []) or []:
        triggers = [f for f in changed if path_matches(f, rule.when)]
        if not triggers:
            continue
        trigger = (f"{triggers[0]} (+{len(triggers) - 1} more)" if len(triggers) > 1
                   else triggers[0])
        for required in rule.require:
            present = any(path_matches(f, required) for f in changed)
            report.check(
                f"{required} (required by {rule.when})",
                present,
                f"required by {rule.when}, and in the change" if present
                else f"{trigger} matches {rule.when}, which requires "
                     f"{required} — not in the change")
    return report


def _import_profile_gates() -> list | None:
    """The generated gate list, or None when no profile ever wrote one.

    Mirrors `quality._import_generated_blocks`: existence is decided by
    `find_spec`, BEFORE importing, so that every error raised *by* the
    generated file stays fatal regardless of what it names. An earlier draft
    of this function matched on `ModuleNotFoundError.name` instead, which
    could not tell "profile_gates is absent" from "profile_gates imports
    something else that is absent and happens to share its name" - and the
    second case would silently fall back to an empty gate list. An empty gate
    list is exactly as dangerous as quality.py's echo placeholders: it is a
    definition of done that quietly stopped being enforced, only quieter,
    because nothing here even admits it is fake.
    """
    if importlib.util.find_spec(f"{__package__}.profile_gates") is None:
        return None
    from .profile_gates import PROFILE_GATES
    return list(PROFILE_GATES)


def profile_gates() -> list:
    """The stack gates a profile wired for this repo. Empty without one.

    Spread into a phase's gate list: `gates=[gates.diff_matches_claims,
    *gates.profile_gates()]`. An un-profiled repo gets an empty list and
    behaves exactly as it did before profiles existed.
    """
    wired = _import_profile_gates()
    return list(wired) if wired is not None else []
