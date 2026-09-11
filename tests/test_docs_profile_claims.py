"""Documentation claims that went stale when the profile mechanism landed.

`test_docs_accurate.py` holds the claims that predate profiles. This file holds
the ones the profile merge invalidated and a documentation pass corrected.

Every test here pins a sentence that was WRONG in shipped documentation, and
each derives its expectation from the code rather than restating the sentence,
so it fails when either side moves.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "sssf"
ADWS = SKILL / "templates" / "adws"
MODULES = ADWS / "adw_modules"
JUSTFILE = SKILL / "templates" / "justfile"

RECIPE = re.compile(r"^([a-z][a-z0-9-]*)(?:\s+[*A-Za-z_][A-Za-z0-9_]*)*\s*:(?!=)")
FENCE = re.compile(r"```[^\n]*\n([\s\S]*?)```")
# A command line, tolerating a shell prompt and leading VAR=value assignments.
RUNS_JUST = re.compile(r"^\s*(?:\$\s*)?(?:[A-Z_]+=\S+\s+)*just\s+(--list|[a-z][a-z0-9-]+)")


def _text(*parts) -> str:
    return SKILL.joinpath(*parts).read_text(encoding="utf-8")


def _readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _markdown() -> list[Path]:
    return [ROOT / "README.md"] + sorted(SKILL.rglob("*.md"))


def _recipes() -> set[str]:
    lines = JUSTFILE.read_text(encoding="utf-8").split("\n")
    return {m.group(1) for m in (RECIPE.match(line) for line in lines) if m}


def _generate_adw(tmp_path, monkeypatch, agents: str) -> Path:
    import subprocess
    import sys

    monkeypatch.chdir(tmp_path)
    subprocess.run([sys.executable, str(SKILL / "scripts" / "make_adw.py"),
                    "--name", "probe", "--agents", agents],
                   check=True, capture_output=True)
    return tmp_path / "adws" / "adw_probe.py"


def test_no_document_tells_an_operator_to_run_a_recipe_the_justfile_lacks():
    """`just rosters` and `just kill <adw_id>` were both documented as the way.

    Neither is a recipe in the stamped justfile — its own header says both live
    on the `example` branch — so both fail in a freshly stamped repo, and the
    second fails exactly when a run is stuck and someone is under pressure.

    Only fenced blocks are scanned. A document telling you to RUN something puts
    it in one, while prose may legitimately name a recipe that does not exist in
    order to say that it does not exist.
    """
    known = _recipes() | {"--list"}
    assert "sessions" in known, "the justfile stopped parsing; fix this test"

    offenders = []
    for path in _markdown():
        for block in FENCE.findall(path.read_text(encoding="utf-8")):
            for line in block.split("\n"):
                found = RUNS_JUST.match(line)
                if found and found.group(1) not in known:
                    offenders.append(f"{path.name}: just {found.group(1)}")
    assert offenders == [], f"{offenders} — recipes that exist: {sorted(known)}"


def test_make_adw_generates_a_script_that_actually_runs(tmp_path, monkeypatch):
    """The generator emitted `run.succeeded`, which no longer exists.

    Every ADW it wrote would have raised AttributeError on its last line. It
    also wrote the file in the locale codec, so on a Windows console the em dash
    in its own TODO comment landed as cp1252 in a .py file with no encoding
    declaration — a SyntaxError the first time anyone ran the result.
    """
    import ast

    path = _generate_adw(tmp_path, monkeypatch, "scout,builder")
    raw = path.read_bytes()
    text = raw.decode("utf-8")          # raises on a locale-encoded em dash
    tree = ast.parse(text)              # raises on anything unparseable

    assert "run.succeeded" not in text
    assert "return run.finish()" in text
    assert b"\r\n" not in raw
    assert any(isinstance(node, ast.FunctionDef) and node.name == "main"
               for node in tree.body)


def test_make_adw_gates_a_build_phase_the_way_the_shipped_adws_do(tmp_path,
                                                                  monkeypatch):
    """Generated phases were all gated `[gates.artifacts_exist]`.

    A builder envelope declares `changed_files`, not artifacts, so that gate
    passes on an empty list — and doc_policy and the stack gates were absent
    entirely. An ADW built by following the cookbook ran quietly weaker than the
    twelve shipping beside it.
    """
    text = _generate_adw(tmp_path, monkeypatch, "builder").read_text(encoding="utf-8")
    for gate in ("gates.diff_matches_claims", "gates.doc_policy",
                 "*gates.profile_gates()"):
        assert gate in text, gate
    assert "gates=[gates.artifacts_exist]" not in text


def test_make_adw_still_gates_an_unknown_agent_conservatively(tmp_path, monkeypatch):
    """Nothing can be assumed about what a GenericOutput agent claims, so it
    must NOT inherit the builder's gate set — diff_matches_claims over an
    envelope with no declared changes is a gate that cannot fail."""
    text = _generate_adw(tmp_path, monkeypatch, "nobody").read_text(encoding="utf-8")
    assert "GenericOutput" in text
    assert "gates.doc_policy" not in text
    assert "gates=[gates.artifacts_exist]" in text


def test_every_shipped_build_phase_carries_the_full_gate_set():
    """The invariant README.md and SKILL.md now both state out loud.

    adw_plan_build_test.py gated its two BuildOutput phases on artifacts_exist
    while its six siblings used diff_matches_claims.
    """
    call = re.compile(r"output_type=BuildOutput[\s\S]{0,400}?\)\)")
    seen = 0
    offenders = []
    for path in sorted(ADWS.glob("adw_*.py")):
        for match in call.finditer(path.read_text(encoding="utf-8")):
            seen += 1
            body = match.group(0)
            missing = [name for name in ("gates.diff_matches_claims",
                                         "gates.doc_policy",
                                         "*gates.profile_gates()")
                       if name not in body]
            if missing:
                offenders.append(f"{path.name}: missing {missing}")
    assert seen >= 8, f"only {seen} BuildOutput calls matched; the regex drifted"
    assert offenders == [], offenders


def test_the_handoff_reference_lists_every_placeholder_the_code_renders():
    """handoff.md is the canonical spec and listed three of the four.

    A prompt author reading it would never learn that {{profile_overlay}}
    exists — and a template that does not name it silently does not receive it.
    """
    source = (MODULES / "agents.py").read_text(encoding="utf-8")
    block = re.search(r"variables = \{([\s\S]*?)\n    \}", source)
    assert block, "the variables dict in agents.execute moved"
    rendered = re.findall(r'"(\w+)":', block.group(1))
    assert len(rendered) >= 4, rendered

    text = _text("references", "handoff.md")
    for name in rendered:
        assert "{{" + name + "}}" in text, name


def test_the_gates_that_run_on_every_build_are_documented():
    """README.md and SKILL.md both enumerate gates, and both lists were stale.

    doc_policy in particular runs in every BuildOutput phase of every shipped
    ADW and is the one gate an operator configures rather than codes.
    """
    defined = set(re.findall(r"^def (\w+)", (MODULES / "gates.py").read_text(
        encoding="utf-8"), re.MULTILINE))
    for required in ("diff_matches_claims", "doc_policy", "profile_gates"):
        assert required in defined, f"{required} is no longer exported by gates.py"
        for name, text in (("README.md", _readme()), ("SKILL.md", _text("SKILL.md"))):
            assert required in text, f"{name} never mentions {required}"


def test_the_upgrade_docs_name_the_symbols_the_installer_checks_for():
    """Both README.md and install.md describe the stale-tree refusal. If
    GENERATED_DEPENDENCIES grows a fourth entry, they have to grow with it."""
    source = (SKILL / "scripts" / "install.py").read_text(encoding="utf-8")
    block = re.search(r"GENERATED_DEPENDENCIES = \(([\s\S]*?)\n\)", source)
    assert block, "GENERATED_DEPENDENCIES moved"
    symbols = re.findall(r'"(?:def )?(\w+)",', block.group(1))
    assert len(symbols) >= 3, symbols

    readme, install = _readme(), _text("cookbooks", "install.md")
    for symbol in symbols:
        assert symbol in readme, f"README.md does not name {symbol}"
        assert symbol in install, f"install.md does not name {symbol}"


def test_no_document_still_promises_that_a_reinstall_skips_every_file():
    """`emit.write_file` overwrites the three generated files unconditionally,
    and `stale_modules` can refuse the install outright. "It skips every file
    that already exists" was true before profiles and is not true now."""
    pattern = re.compile(r"skips\s+\**every\**\s+file", re.IGNORECASE)
    offenders = [path.name for path in _markdown()
                 if pattern.search(path.read_text(encoding="utf-8"))]
    assert offenders == [], offenders


def test_the_readme_documents_every_install_flag():
    """The flags appeared only in a failure table and a customization table,
    never in the Install section a first-time reader actually follows."""
    source = (SKILL / "scripts" / "install.py").read_text(encoding="utf-8")
    flags = re.findall(r'add_argument\("(--[a-z-]+)"', source)
    assert len(flags) >= 4, flags
    readme = _readme()
    for flag in flags:
        assert flag in readme, flag


def test_the_readme_and_skill_explain_the_two_quality_tiers():
    """`tier` decides what runs inside a bounded fix loop and what runs once
    after it. The word appeared nowhere in the README's 443 lines."""
    import sys

    sys.path.insert(0, str(ADWS))
    from adw_modules.data_types import QualityTier

    tiers = list(QualityTier.__args__)
    assert set(tiers) == {"fast", "full"}, tiers
    for name, text in (("README.md", _readme()), ("SKILL.md", _text("SKILL.md"))):
        for tier in tiers:
            assert f"`{tier}`" in text, f"{name} never mentions the {tier} tier"


def test_the_quality_artifact_path_is_documented_where_a_failure_is_read():
    """A failing block's real output is at
    `context_handoff/quality/<seq>_<name>/command.log`. The string `command.log`
    appeared in no document at all, so there was nowhere to learn that."""
    source = (MODULES / "quality.py").read_text(encoding="utf-8")
    assert '"command.log"' in source, "the artifact filename changed"
    for where in (_readme(), _text("cookbooks", "run_adw.md"),
                  _text("references", "handoff.md")):
        assert "command.log" in where


def test_the_quality_tool_call_payload_is_documented_with_its_real_keys():
    """`tool_call` has two producers and two payloads. observability.md is the
    contract a consumer is written from, and it documented only the agent one,
    so a reader hits quality rows with none of the documented keys."""
    source = (MODULES / "quality.py").read_text(encoding="utf-8")
    block = re.search(r'type="tool_call",[\s\S]*?payload=\{([\s\S]*?)\n        \},',
                      source)
    assert block, "the quality tool_call event moved"
    keys = re.findall(r'"(\w+)":', block.group(1))
    assert "tier" in keys and "output_artifact" in keys, keys

    text = _text("references", "observability.md")
    for key in keys:
        assert key in text, f"observability.md never mentions the {key} key"


def test_the_cost_of_a_third_framework_is_stated_accurately():
    """README.md and install.md both quote a line count for the worked example.

    It is the most concrete claim the profile design makes, which is exactly why
    it rots: the number is in prose and the file is in the test suite.
    """
    lines = len((ROOT / "tests" / "fake_framework.py")
                .read_text(encoding="utf-8").rstrip("\n").split("\n"))
    for name, text in (("README.md", _readme()),
                       ("install.md", _text("cookbooks", "install.md"))):
        quoted = re.findall(r"(\d+)-line module", text)
        assert quoted, f"{name} no longer quotes a line count"
        assert all(int(n) == lines for n in quoted), \
            f"{name} says {quoted}, fake_framework.py is {lines} lines"
