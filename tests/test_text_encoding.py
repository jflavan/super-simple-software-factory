"""Every byte the factory reads or writes names its codec.

Python's `read_text()`, `write_text()`, `open()` and `subprocess(text=True)` all
default to `locale.getpreferredencoding()`. On a default Windows install that is
**cp1252**, and the factory's own files are UTF-8, so the default was wrong in
both directions:

- reading a starter prompt turned every em dash into three mojibake characters,
  silently, in the prompt the model was actually sent;
- decoding a coding agent's stdout hit `UnicodeDecodeError` on any emoji or
  zero-width joiner, killing the run mid-stream.

cp1252 maps most bytes to *something*, so the common case is silent corruption
rather than a crash — which is why this went unnoticed. The rule is therefore
absolute and mechanical: name the codec at every site, including the ones that
only look at a return code, because "every call names it" is checkable and
"every call that matters names it" is an argument.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "sssf"
PROMPTS = SKILL / "templates" / "prompt_engineering"

FILE_CALLS = {"read_text", "write_text", "open"}
SPAWNERS = {"run", "Popen", "check_output", "call", "check_call"}
# Passing any of these puts a subprocess in text mode, where stdout is decoded.
TEXT_MODE = {"text", "universal_newlines"}


def _python_files() -> list[Path]:
    return [p for p in sorted(SKILL.rglob("*.py"))
            if "__pycache__" not in p.parts]


def _keywords(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


def _splats(call: ast.Call) -> bool:
    """`f(**kwargs)` hides every keyword from static inspection."""
    return any(kw.arg is None for kw in call.keywords)


def _is_binary_mode(call: ast.Call, mode_index: int) -> bool:
    """A binary-mode open needs no codec, and must not be given one.

    `mode_index` differs by call shape: `Path.open(mode)` puts it first,
    builtin `open(path, mode)` second. Reading the wrong position would exempt
    a text-mode call whose *path* happened to contain a "b".
    """
    mode = None
    if len(call.args) > mode_index:
        positional = call.args[mode_index]
        if isinstance(positional, ast.Constant) and isinstance(positional.value, str):
            mode = positional.value
    keyword = _keywords(call).get("mode")
    if isinstance(keyword, ast.Constant) and isinstance(keyword.value, str):
        mode = keyword.value
    return mode is not None and "b" in mode


def _names_a_codec(call: ast.Call) -> bool:
    """`encoding=` present AND not literally None.

    `encoding=None` is spelled differently from omitting it and means exactly
    the same thing — fall back to the locale codec — so a scanner that only
    checks for the keyword's presence can be silenced by typing it.
    """
    keywords = _keywords(call)
    if "encoding" not in keywords:
        return False
    value = keywords["encoding"]
    return not (isinstance(value, ast.Constant) and value.value is None)


def _subprocess_aliases(tree: ast.Module) -> tuple[set[str], set[str]]:
    """(module aliases, names imported directly) for `subprocess`.

    `import subprocess as sp` and `from subprocess import run` are both
    invisible to a scanner that only recognises the literal name.
    """
    modules, direct = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "subprocess":
                    modules.add(alias.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for alias in node.names:
                if alias.name in SPAWNERS:
                    direct.add(alias.asname or alias.name)
    return modules, direct


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules, direct = _subprocess_aliases(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = _keywords(node)
        func = node.func
        attribute = isinstance(func, ast.Attribute)
        name = func.attr if attribute else getattr(func, "id", None)

        is_file_call = (attribute and name in FILE_CALLS) or (
            not attribute and name == "open")            # the builtin
        is_spawn = ((attribute and name in SPAWNERS
                     and getattr(func.value, "id", None) in modules)
                    or (not attribute and name in direct))

        if is_file_call:
            if name == "open" and _is_binary_mode(node, 0 if attribute else 1):
                continue
            if not _names_a_codec(node):
                found.append(f"{path.name}:{node.lineno} {name}() has no encoding=")

        elif is_spawn:
            if _splats(node):
                # **kwargs could carry anything, including text=True with no
                # codec. Refuse to certify what cannot be read.
                found.append(f"{path.name}:{node.lineno} "
                             f"subprocess call splats **kwargs — unreadable")
                continue
            in_text_mode = any(
                isinstance(keywords.get(flag), ast.Constant)
                and keywords[flag].value is True
                for flag in TEXT_MODE)
            unreadable_flag = any(
                flag in keywords and not isinstance(keywords[flag], ast.Constant)
                for flag in TEXT_MODE)
            if (in_text_mode or unreadable_flag) and not _names_a_codec(node):
                found.append(f"{path.name}:{node.lineno} "
                             f"subprocess text mode has no encoding=")
    return found


def test_the_scanner_finds_a_deliberately_unpinned_call(tmp_path):
    """The guard below is worthless if the scanner cannot see a violation.

    Every evasion listed here was a real false negative in the first draft,
    found by reviewing the scanner rather than trusting it. `encoding=None` is
    the nastiest: it reads as compliance and means the locale codec.
    """
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import subprocess\n"
        "import subprocess as sp\n"
        "from subprocess import run\n"
        "from pathlib import Path\n"
        "def f(p, q):\n"
        "    a = Path(p).read_text()\n"                   # 1 the plain case
        "    Path(p).write_text('x')\n"                   # 2
        "    Path(p).open('a')\n"                         # 3
        "    subprocess.run(['git'], text=True)\n"        # 4
        "    Path(p).read_text(encoding=None)\n"          # 5 looks compliant
        "    open(p)\n"                                   # 6 builtin, not Path
        "    sp.run(['git'], text=True)\n"                # 7 aliased module
        "    run(['git'], text=True)\n"                   # 8 imported directly
        "    subprocess.run(['git'], **q)\n"              # 9 unreadable
        "    subprocess.run(['git'], text=q)\n"           # 10 unreadable
        "    Path(p).read_bytes()\n"                      # not a text call
        "    Path(p).open('rb')\n"                        # binary, exempt
        "    open(p, 'rb')\n"                             # binary builtin
        "    subprocess.run(['git'])\n"                   # bytes, exempt
        "    Path(p).read_text(encoding='utf-8')\n"       # correct, exempt
        "    run(['git'], text=True, encoding='utf-8')\n" # correct, exempt
        "    return a\n", encoding="utf-8")
    found = _offenders(probe)
    assert len(found) == 10, found


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: p.name)
def test_every_text_io_call_names_its_codec(path):
    assert _offenders(path) == []


def test_the_starter_prompts_survive_a_render_on_this_machine():
    """The bug, reproduced against the real files rather than a fixture.

    `prompts.render` is what every agent call goes through. Before the fix it
    used the locale codec, so on cp1252 each `—` (U+2014) in a shipped prompt
    arrived at the model as `â€"`. This asserts the rendered text is byte-for-
    byte what UTF-8 says the file holds, whatever the machine's locale is.
    """
    from adw_modules import prompts

    checked = 0
    for path in sorted(PROMPTS.rglob("*.md")):
        expected = path.read_text(encoding="utf-8")
        rendered = prompts.render(path, {})
        assert rendered == expected, f"{path.name} was corrupted by render()"
        if any(ord(c) > 127 for c in expected):
            checked += 1
    assert checked >= 5, (
        f"only {checked} starter prompts contain non-ASCII text — this test "
        f"proves nothing unless some of them do")


def test_a_round_trip_through_save_preserves_what_render_read(tmp_path):
    """`prompts.save` writes the audit copy — "exactly what was sent".

    It was unpinned too, so on cp1252 the saved copy could differ from the
    string actually handed to the agent, or raise outright on an emoji.
    """
    from adw_modules import prompts

    source = tmp_path / "user.md"
    # An em dash (silently corrupted by cp1252) and an emoji (hard crash).
    body = "Follow the plan — exactly. Ship it \U0001F680 {{prompt}}\n"
    source.write_text(body, encoding="utf-8")

    rendered = prompts.render(source, {"prompt": "do the thing"})
    assert "—" in rendered and "\U0001F680" in rendered

    saved = prompts.save(tmp_path / "out", "user.md", rendered)
    assert saved.read_text(encoding="utf-8") == rendered
    assert saved.read_bytes().decode("utf-8") == rendered


def test_the_banner_cannot_kill_a_run_on_a_cp1252_console():
    """The documented Windows footgun, reproduced and then closed.

    The banner prints `▶`, `─` and `│`; a default Windows console is cp1252 and
    has none of them. `rich` raised UnicodeEncodeError mid-phase, the process
    died before anything finalized, and that session's row stayed `running` in
    the trace forever. The documented answer was "go set PYTHONIOENCODING",
    which only helps an operator who already knows.

    Run in a subprocess with PYTHONIOENCODING=cp1252 because the error handler
    is process-global — asserting it in-process would change this interpreter
    for every test that follows.
    """
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent("""
        import sys
        sys.path.insert(0, sys.argv[1])
        from adw_modules import console
        from adw_modules.data_types import Phase, PhaseParams

        class FakeTracer:
            def event(self, record): pass

        phase = Phase(phase_id="ph_1", adw_id="probe123", seq=1, status="success",
                      params=PhaseParams(
                          name="build", kind="agent", owner="builder",
                          description="Exercise the glyphs a cp1252 console cannot encode"))

        c = console.Console(FakeTracer(), "probe123")
        c.session_started("probe123", "tester")
        c.phase_started(phase)          # prints U+25B6
        c.agent_started("builder", "google/gemini-3.6-flash", "sess_1")
        c.retry("builder", 1, 2, "envelope did not parse")
        c.phase_ended(phase, 1.5)       # prints U+2713
        c.session_finished(True, 1234, 0.01, "adws/adw_data/sssf.db")  # box-drawing panel
        print("SURVIVED")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(SKILL / "templates" / "adws")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**__import__("os").environ, "PYTHONIOENCODING": "cp1252"})

    assert result.returncode == 0, (
        f"the run died on a cp1252 console:\n{result.stderr}")
    assert "SURVIVED" in result.stdout
    assert "UnicodeEncodeError" not in result.stderr


def _write_trace_fixture(tmp_path) -> Path:
    """A trace db whose phase description carries glyphs cp1252 cannot encode."""
    import sqlite3

    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE phases (phase_id TEXT, adw_id TEXT, seq INT,"
                 " name TEXT, kind TEXT, owner TEXT, description TEXT,"
                 " status TEXT, attempt INT, error TEXT, started_at TEXT,"
                 " ended_at TEXT)")
    conn.execute("INSERT INTO phases VALUES ('p1','abc',1,'build','agent',"
                 "'builder',?,'success',0,NULL,'t','t')",
                 ("Implement the \u2713 checkout flow \U0001F680",))
    conn.commit()
    conn.close()
    return db


def test_adw_trace_survives_a_cp1252_stream():
    """The tool you reach for AFTER a run has already gone wrong.

    `adw_trace.py` prints agent-authored free text — phase descriptions, gate
    violations, errors — and agents write `✓` and `→` constantly. It imports no
    `adw_modules`, so the console's guard never reached it: piped to a cp1252
    stream it died with UnicodeEncodeError and printed no report at all.

    This is the finding that mattered most, because the same change had already
    rewritten three documents to say the failure mode was closed.
    """
    import os
    import subprocess
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as work:
        db = _write_trace_fixture(Path(work))
        result = subprocess.run(
            [sys.executable, str(SKILL / "templates" / "adws" / "adw_trace.py"),
             "phases", "abc", "--db", str(db)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "cp1252"})

    assert result.returncode == 0, f"adw_trace died:\n{result.stderr}"
    assert "UnicodeEncodeError" not in result.stderr
    assert "build" in result.stdout, result.stdout


def test_every_script_that_prints_protects_stdout_first():
    """Structural, because the AST codec scan cannot see this class at all.

    `print()` is not a read, a write, or a subprocess, so the guard above is
    blind to it. Any entry script that prints has to make stdout unable to
    raise before it does — either by going through `console.Console`, or by
    calling its own copy of the guard.
    """
    unprotected = []
    for path in sorted((SKILL / "templates" / "adws").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        prints = [n for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name) and n.func.id == "print"]
        if not prints:
            continue
        goes_through_console = "console" in source and "run.console" in source
        has_own_guard = "reconfigure(errors=" in source
        if not (goes_through_console or has_own_guard):
            unprotected.append(f"{path.name}: {len(prints)} print() call(s)")
    assert unprotected == [], unprotected


def test_both_copies_of_the_stdout_guard_do_the_same_thing():
    """`adw_trace.py` duplicates the guard because it declares dependencies=[].

    A deliberate duplicate is fine; a duplicate that drifts is not. Both must
    change only the error handler, on stdout alone — setting `replace` on
    stderr would downgrade CPython's `backslashreplace` default, which is
    lossless and already cannot raise.
    """
    console = (SKILL / "templates" / "adws" / "adw_modules"
               / "console.py").read_text(encoding="utf-8")
    trace = (SKILL / "templates" / "adws" / "adw_trace.py").read_text(encoding="utf-8")

    for name, source in (("console.py", console), ("adw_trace.py", trace)):
        assert 'sys.stdout.reconfigure(errors="replace")' in source, name
        assert "sys.stderr.reconfigure" not in source, (
            f"{name} downgrades stderr's lossless backslashreplace default")
        assert "encoding=" not in source.split("reconfigure(")[1].split(")")[0], (
            f"{name} changes the encoding, not just the error handler")
