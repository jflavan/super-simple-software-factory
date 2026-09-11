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


def _is_binary_mode(call: ast.Call) -> bool:
    """A binary-mode open needs no codec, and must not be given one."""
    mode = None
    if call.args and len(call.args) >= 1:
        first = call.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            mode = first.value
    keyword = _keywords(call).get("mode")
    if isinstance(keyword, ast.Constant) and isinstance(keyword.value, str):
        mode = keyword.value
    return mode is not None and "b" in mode


def _offenders(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = _keywords(node)
        func = node.func
        name = getattr(func, "attr", None) or getattr(func, "id", None)

        if name in FILE_CALLS and isinstance(func, ast.Attribute):
            if name == "open" and _is_binary_mode(node):
                continue
            if "encoding" not in keywords:
                found.append(f"{path.name}:{node.lineno} {name}() has no encoding=")

        elif name in SPAWNERS and isinstance(func, ast.Attribute):
            module = getattr(func.value, "id", None)
            if module != "subprocess":
                continue
            in_text_mode = any(
                isinstance(keywords.get(flag), ast.Constant)
                and keywords[flag].value is True
                for flag in TEXT_MODE)
            if in_text_mode and "encoding" not in keywords:
                found.append(f"{path.name}:{node.lineno} "
                             f"subprocess text mode has no encoding=")
    return found


def test_the_scanner_finds_a_deliberately_unpinned_call(tmp_path):
    """The guard below is worthless if the scanner cannot see a violation."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import subprocess\n"
        "from pathlib import Path\n"
        "def f(p):\n"
        "    a = Path(p).read_text()\n"
        "    Path(p).write_text('x')\n"
        "    Path(p).open('a')\n"
        "    subprocess.run(['git'], text=True)\n"
        "    Path(p).read_bytes()\n"                      # not a text call
        "    Path(p).open('rb')\n"                        # binary, exempt
        "    subprocess.run(['git'])\n"                   # bytes, exempt
        "    Path(p).read_text(encoding='utf-8')\n"       # correct, exempt
        "    return a\n", encoding="utf-8")
    found = _offenders(probe)
    assert len(found) == 4, found


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
