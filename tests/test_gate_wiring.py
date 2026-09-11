"""Every code-changing phase runs the repo's own gates.

A structural test over the shipped ADW scripts, not a behavioural one. It
exists because the failure it catches is invisible at runtime: a build phase
with a short gate list does not error, it just checks less than the operator
thinks it does.
"""

import ast
from pathlib import Path

ADWS = (Path(__file__).resolve().parent.parent
        / ".claude" / "skills" / "sssf" / "templates" / "adws")


def _agent_calls(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "AgentCall":
            yield node


def _keyword(call, name):
    return next((k.value for k in call.keywords if k.arg == name), None)


def _build_calls():
    """Every AgentCall in every shipped ADW whose output_type is BuildOutput."""
    for script in sorted(ADWS.glob("adw_*.py")):
        tree = ast.parse(script.read_text())
        for call in _agent_calls(tree):
            output_type = _keyword(call, "output_type")
            if isinstance(output_type, ast.Name) and output_type.id == "BuildOutput":
                yield script.name, call


def _gate_source(call) -> str:
    gates = _keyword(call, "gates")
    return ast.unparse(gates) if gates is not None else ""


def test_there_are_build_phases_to_check():
    """Guard the guard: an empty iterator would make every assertion below vacuous."""
    assert len(list(_build_calls())) >= 13


def test_every_build_phase_runs_the_profile_gates():
    missing = [name for name, call in _build_calls()
               if "gates.profile_gates()" not in _gate_source(call)]
    assert missing == [], f"build phases without profile gates: {sorted(set(missing))}"


def test_every_build_phase_runs_doc_policy():
    missing = [name for name, call in _build_calls()
               if "gates.doc_policy" not in _gate_source(call)]
    assert missing == [], f"build phases without doc_policy: {sorted(set(missing))}"


def test_the_profile_gates_are_spread_not_nested():
    """`gates.profile_gates()` unspread would pass a LIST where a gate belongs."""
    for name, call in _build_calls():
        assert "*gates.profile_gates()" in _gate_source(call), name


def test_non_build_phases_are_left_alone():
    """A planner writing a spec has not changed code, and a reviewer must not be
    asked to update a document it is not allowed to write."""
    for script in sorted(ADWS.glob("adw_*.py")):
        tree = ast.parse(script.read_text())
        for call in _agent_calls(tree):
            output_type = _keyword(call, "output_type")
            name = getattr(output_type, "id", "")
            if name in ("PlanOutput", "ReviewOutput", "ScoutOutput"):
                assert "profile_gates" not in _gate_source(call), script.name


def test_no_adw_runs_the_full_tier_inside_a_bounded_loop():
    """`run_quality` runs both tiers, and a full block needs Docker up.

    Three shipped documents state this invariant, including the docstring
    written verbatim into every generated quality_blocks.py. Asserted here
    because the tier mechanism exists to make it true, and nothing else in the
    suite executes an ADW's phase sequence.
    """
    offenders = []
    for script in sorted(ADWS.glob("adw_*.py")):
        tree = ast.parse(script.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.While)):
                continue
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr == "run_quality"):
                    offenders.append(script.name)
    assert offenders == [], f"run_quality inside a loop in: {sorted(set(offenders))}"
