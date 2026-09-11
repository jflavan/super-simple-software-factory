# SSSF Portability Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SSSF run on Claude Code and on Windows, so the factory can execute against a real ASP.NET Core + SvelteKit repo.

**Architecture:** `agents.py` currently imports `agent_pi` directly and rejects every other backend. We introduce a backend-dispatch seam, implement `agent_cc.py` against the same four-name interface `agent_pi` exposes, and fix two platform bugs that make subprocess launches misreport on Windows. Everything that can be tested without a live agent is a pure function tested offline; the one subprocess integration point is tested through an injectable `_popen` seam.

**Tech Stack:** Python 3.11+, pydantic, pytest, uv. Target modules live in `.claude/skills/sssf/templates/adws/adw_modules/`.

**Spec:** `docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md` (Part A). Parts B and C get their own plans after this one is proven.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` (create, repo root) | Dev dependencies so `uv run pytest` works |
| `tests/conftest.py` (create) | Put `templates/adws` on `sys.path` so `adw_modules` imports |
| `tests/test_utils.py` (create) | `resolve_argv`, `venv_bin_dir`, `operator_env` |
| `tests/test_agent_cc.py` (create) | Thinking map, tool map, model resolution, command build, session map, `run` |
| `tests/test_tool_tracker.py` (create) | Both trackers against synthetic streams |
| `tests/test_agents_dispatch.py` (create) | `backend_for`, `validate` |
| `tests/test_adw_trace.py` (create) | Trace reader against a temp db |
| `templates/adws/adw_modules/utils.py` (modify) | Add `resolve_argv`, `venv_bin_dir`; fix `operator_env` |
| `templates/adws/adw_modules/data_types.py` (modify) | Rename `PiRequest`/`PiResult` → `AgentRequest`/`AgentResult` |
| `templates/adws/adw_modules/agent_cc.py` (rewrite) | The Claude Code backend |
| `templates/adws/adw_modules/agent_pi.py` (modify) | Rename; widen tracker contract; add `validate_agent` |
| `templates/adws/adw_modules/agents.py` (modify) | Backend dispatch; drop the pi-only rejection |
| `templates/adws/adw_modules/quality.py` (modify) | Launch through `resolve_argv` |
| `templates/adws/adw_trace.py` (create) | stdlib-sqlite3 trace reader |

All paths below are relative to the repo root `C:\Source\Repos\super-simple-software-factory`. The skill templates live under `.claude/skills/sssf/`, abbreviated `<SKILL>` in prose but written in full in every command.

---

### Task 1: Test harness

**Files:**
- Create: `pyproject.toml`
- Create: `tests/conftest.py`
- Create: `tests/test_harness.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_harness.py`:

```python
"""The harness itself: adw_modules must be importable from the skill templates."""


def test_adw_modules_is_importable():
    from adw_modules import utils

    assert callable(utils.now_iso)


def test_data_types_is_importable():
    from adw_modules import data_types

    assert data_types.EnvelopeBase is not None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_harness.py -v`
Expected: FAIL — no `pyproject.toml`, so uv errors, or `ModuleNotFoundError: No module named 'adw_modules'`.

- [ ] **Step 3: Create the project file and conftest**

Create `pyproject.toml`:

```toml
[project]
name = "super-simple-software-factory"
version = "0.1.0"
description = "SSSF skill development workspace"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
dev = [
    "pytest>=8",
    "pydantic>=2",
    "pyyaml>=6",
    "python-dotenv>=1",
    "rich>=13",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `tests/conftest.py`:

```python
"""Make the stamped module tree importable without stamping it.

The modules under test ship as skill templates, not as an installed package.
Putting `templates/adws` on sys.path lets the tests import `adw_modules.*`
exactly as a stamped repo would, so what we test is what gets shipped.
"""

import sys
from pathlib import Path

TEMPLATES_ADWS = (Path(__file__).resolve().parent.parent
                  / ".claude" / "skills" / "sssf" / "templates" / "adws")

if str(TEMPLATES_ADWS) not in sys.path:
    sys.path.insert(0, str(TEMPLATES_ADWS))
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_harness.py -v`
Expected: PASS, 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/conftest.py tests/test_harness.py
git commit -m "test: add pytest harness for the stamped adw_modules tree"
```

---

### Task 2: `utils.resolve_argv`

Closes spec finding 2. A bare-name argv raises `WinError 2` on Windows for `.cmd` shims like `npm`; `quality.py` catches that `OSError` and reports exit 127, so a PATH problem is indistinguishable from a real command failure.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_utils.py`:

```python
"""utils: argv resolution and the operator environment."""

from pathlib import Path

from adw_modules import utils


def test_resolve_argv_finds_a_real_binary():
    resolved = utils.resolve_argv(["git", "status"])

    assert Path(resolved[0]).is_absolute()
    assert Path(resolved[0]).stem == "git"
    assert resolved[1:] == ["status"]


def test_resolve_argv_passes_a_missing_binary_through_unchanged():
    # Unresolvable argv must survive intact so the caller's existing exit-127
    # path still reports a genuinely missing binary.
    argv = ["sssf-definitely-not-a-real-binary", "--version"]

    assert utils.resolve_argv(argv) == argv


def test_resolve_argv_handles_an_empty_argv():
    assert utils.resolve_argv([]) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_utils.py -v`
Expected: FAIL with `AttributeError: module 'adw_modules.utils' has no attribute 'resolve_argv'`.

- [ ] **Step 3: Implement**

In `.claude/skills/sssf/templates/adws/adw_modules/utils.py`, add `import shutil` to the imports, then add this function directly after `operator_env`:

```python
def resolve_argv(argv: list[str]) -> list[str]:
    """Resolve argv[0] to an absolute executable path.

    On Windows `npm` is `npm.cmd`, and a bare-name argv raises WinError 2 in
    subprocess.run — which quality.py catches as an OSError and reports as
    exit 127, making a PATH problem indistinguishable from a command that ran
    and failed. shutil.which honours PATHEXT, so it finds the shim.

    When nothing resolves, the argv is returned unchanged: that failure is a
    genuinely missing binary, and the existing exit-127 path reports it
    correctly with the real message.
    """
    if not argv:
        return list(argv)
    found = shutil.which(argv[0])
    return [found, *argv[1:]] if found else list(argv)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_utils.py -v`
Expected: PASS, 3 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/utils.py tests/test_utils.py
git commit -m "fix: resolve argv[0] through shutil.which so .cmd shims launch on Windows"
```

---

### Task 3: `utils.venv_bin_dir` and the `operator_env` fix

Closes spec finding 3. `operator_env` strips `Path(venv) / "bin"`; uv on Windows uses `Scripts`, so it strips nothing and the venv-shadowing hazard it documents is unmitigated.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/utils.py`
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_utils.py`:

```python
import os


def test_venv_bin_dir_uses_scripts_on_windows():
    assert utils.venv_bin_dir(r"C:\tmp\.venv", windows=True).endswith("Scripts")


def test_venv_bin_dir_uses_bin_elsewhere():
    assert utils.venv_bin_dir("/tmp/.venv", windows=False).endswith("bin")


def test_operator_env_strips_the_venv_bin_dir(monkeypatch):
    venv = str(Path.cwd() / "sssf-test-venv")
    venv_bin = utils.venv_bin_dir(venv)
    other = str(Path.cwd() / "real-tools")
    monkeypatch.setenv("VIRTUAL_ENV", venv)
    monkeypatch.setenv("PATH", os.pathsep.join([venv_bin, other]))

    env = utils.operator_env()

    assert "VIRTUAL_ENV" not in env
    assert venv_bin not in env["PATH"].split(os.pathsep)
    assert other in env["PATH"].split(os.pathsep)


def test_operator_env_is_a_passthrough_without_a_venv(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin")

    assert utils.operator_env()["PATH"] == "/usr/bin"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_utils.py -v`
Expected: FAIL with `AttributeError: module 'adw_modules.utils' has no attribute 'venv_bin_dir'`.

- [ ] **Step 3: Implement**

In `utils.py`, add this function immediately **before** `operator_env`:

```python
def venv_bin_dir(venv: str, windows: bool | None = None) -> str:
    """The directory a virtualenv puts executables in.

    Split out, with an explicit `windows` flag, so both branches are testable
    on either platform. uv writes to `Scripts` on Windows and `bin` elsewhere;
    operator_env previously stripped only `bin`, so on Windows it stripped
    nothing and the shadowing hazard it documents went unmitigated.
    """
    if windows is None:
        windows = os.name == "nt"
    return str(Path(venv) / ("Scripts" if windows else "bin"))
```

Then replace the body of `operator_env` after the `if not venv: return env` line with:

```python
    venv_bin = os.path.normcase(venv_bin_dir(venv).rstrip("\\/"))
    parts = [p for p in env.get("PATH", "").split(os.pathsep)
             if p and os.path.normcase(p.rstrip("\\/")) != venv_bin]
    env["PATH"] = os.pathsep.join(parts)
    return env
```

`normcase` matters: Windows paths compare case-insensitively, so an exact string match would miss `C:\Tmp\.venv\Scripts` vs `c:\tmp\.venv\scripts`.

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_utils.py -v`
Expected: PASS, 7 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/utils.py tests/test_utils.py
git commit -m "fix: strip the venv Scripts dir on Windows in operator_env"
```

---

### Task 4: Route quality blocks through `resolve_argv`

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/quality.py:74-96`
- Test: `tests/test_quality_launch.py`

The trace must keep recording the **bare** command, not the resolved absolute path — `quality.py`'s own banner says an absolute path "bakes your machine into the trace." So we resolve for execution and record the original.

- [ ] **Step 1: Write the failing test**

Create `tests/test_quality_launch.py`:

```python
"""A quality block launches a resolved argv but records the bare one."""

from pathlib import Path
from types import SimpleNamespace

from adw_modules import quality
from adw_modules.data_types import QualityCheckSpec


def _fake_run(tmp_path):
    """The smallest stand-in quality._run actually touches.

    It reads run.adw_id, run.repo_root, run.context_handoff_dir,
    run.phases[-1], run.tracer.event and run.console.note — and nothing else.
    """
    return SimpleNamespace(
        adw_id="testadw",
        repo_root=tmp_path,
        context_handoff_dir=tmp_path,
        phases=[SimpleNamespace(seq=1, phase_id="testadw_01_probe")],
        tracer=SimpleNamespace(event=lambda record: None),
        console=SimpleNamespace(note=lambda message: None),
    )


def test_run_resolves_argv_but_records_the_bare_command(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)

    result = quality._run(QualityCheckSpec(
        name="probe", area="backend", operation="lint", argv=["git", "status"],
    ), _fake_run(tmp_path))

    # Executed with a resolved absolute path...
    assert captured["argv"][0] != "git"
    assert Path(captured["argv"][0]).is_absolute()
    # ...but the trace keeps the machine-independent form.
    assert result.command == "git status"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_quality_launch.py -v`
Expected: FAIL — `captured["argv"][0]` is still `"git"`.

- [ ] **Step 3: Implement**

In `quality.py`, add `resolve_argv` to the `.utils` import line so it reads:

```python
from .utils import now_iso, operator_env, resolve_argv
```

In `_run`, leave `command = shlex.join(spec.argv)` exactly as it is, and change the `subprocess.run` call's first argument from `spec.argv` to:

```python
            resolve_argv(spec.argv),
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_quality_launch.py -v`
Expected: PASS, 1 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/quality.py tests/test_quality_launch.py
git commit -m "fix: launch quality blocks through resolve_argv, keep the bare command in the trace"
```

---

### Task 5: Rename `PiRequest`/`PiResult` to `AgentRequest`/`AgentResult`

Two backends sharing a type named for one of them is a lie in the type system. Mechanical, but it must be one atomic change — the synced-triad discipline in hard rule 2 applies.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/data_types.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_pi.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agents.py`
- Modify: `.claude/skills/sssf/cookbooks/update_modules.md`
- Test: `tests/test_harness.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_harness.py`:

```python
def test_agent_types_are_backend_neutral():
    from adw_modules import data_types

    assert hasattr(data_types, "AgentRequest")
    assert hasattr(data_types, "AgentResult")
    assert not hasattr(data_types, "PiRequest"), "the pi-named alias must be gone"
    assert not hasattr(data_types, "PiResult"), "the pi-named alias must be gone"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_harness.py -v`
Expected: FAIL on the first assertion — `AgentRequest` does not exist.

- [ ] **Step 3: Find every reference, then rename**

Run this first to see the full set:

```bash
grep -rn "PiRequest\|PiResult" .claude/skills/sssf/
```

Rename the two class definitions in `data_types.py`, then update every reference:
- `agent_pi.py` — the `from .data_types import` line, the `run()` signature and return annotation, and the `result = PiResult(...)` construction.
- `agents.py` — the `from .data_types import` line (line 20), and the three annotations at lines 109, 112 which read `agent_pi.PiResult`; these become `agent_pi.AgentResult`. Keep them qualified for now; Task 13 replaces the module reference.
- `cookbooks/update_modules.md` — the `data_types.py` row mentioning `PiRequest`/`PiResult`.

Re-run the grep; it must return nothing.

- [ ] **Step 4: Run the full suite to verify nothing broke**

Run: `uv run pytest tests/ -v`
Expected: PASS, 11 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/
git add tests/test_harness.py
git commit -m "refactor: rename PiRequest/PiResult to AgentRequest/AgentResult"
```

---

### Task 6: `agent_cc` thinking-level mapping

Claude Code has no `--thinking` flag; the budget travels in the environment.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_agent_cc.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agent_cc.py`:

```python
"""The Claude Code backend: pure mappings first, subprocess wiring last."""

import pytest

from adw_modules import agent_cc


def test_thinking_off_sets_no_budget():
    assert agent_cc.thinking_env("off") == {}


def test_thinking_medium_sets_a_budget():
    assert agent_cc.thinking_env("medium") == {"MAX_THINKING_TOKENS": "10000"}


def test_thinking_max_sets_the_largest_budget():
    assert agent_cc.thinking_env("max") == {"MAX_THINKING_TOKENS": "64000"}


def test_unknown_thinking_level_is_rejected():
    with pytest.raises(ValueError, match="unknown thinking level"):
        agent_cc.thinking_env("ludicrous")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: FAIL with `AttributeError: module 'adw_modules.agent_cc' has no attribute 'thinking_env'`.

- [ ] **Step 3: Implement**

Replace the entire contents of `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py` with:

```python
"""Claude Code interface — the second coding-agent backend.

Runs `claude -p --output-format stream-json` and tails its JSONL stdout line by
line, forwarding each event to a callback WHILE the agent works, exactly as
agent_pi does for pi. Exposes the same four names agent_pi does — `run`,
`resolve_model`, `context_window`, and a tool-call tracker — so agents.py can
dispatch between them without knowing which it holds.

Two things differ from pi and are handled here rather than leaking upward:
sessions (pi's --session-id is create-or-continue; Claude Code needs a UUID to
create and --resume to continue), and thinking (no flag; a token budget in the
environment).
"""

from __future__ import annotations

THINKING_TOKENS = {
    "off": 0,
    "minimal": 1024,
    "low": 4000,
    "medium": 10000,
    "high": 24000,
    "xhigh": 32000,
    "max": 64000,
}


def thinking_env(level: str) -> dict[str, str]:
    """SSSF's thinking level as Claude Code environment settings.

    Claude Code has no --thinking flag, so the level becomes a token budget the
    child process reads from its environment.
    """
    budget = THINKING_TOKENS.get(level)
    if budget is None:
        raise ValueError(f"unknown thinking level {level!r} — expected one of "
                         f"{', '.join(THINKING_TOKENS)}")
    return {} if budget == 0 else {"MAX_THINKING_TOKENS": str(budget)}
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: PASS, 4 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_agent_cc.py
git commit -m "feat: map SSSF thinking levels to a Claude Code token budget"
```

---

### Task 7: `agent_cc` tool-name mapping

An unmappable tool must fail loudly. The config file already warns that a filtered-out extension tool is silently invisible at runtime; that warning has to hold for both backends.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_agent_cc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_cc.py`:

```python
def test_tools_map_to_claude_code_names():
    assert agent_cc.allowed_tools(["read", "write", "grep"]) == ["Read", "Write", "Grep"]


def test_find_maps_to_glob():
    assert agent_cc.allowed_tools(["find"]) == ["Glob"]


def test_ls_and_bash_collapse_without_duplicating():
    # Both map to Bash; the allowlist must not repeat it.
    assert agent_cc.allowed_tools(["bash", "ls"]) == ["Bash"]


def test_none_means_every_tool():
    assert agent_cc.allowed_tools(None) is None


def test_a_pi_extension_tool_is_rejected_by_name():
    with pytest.raises(ValueError, match="subagent_create"):
        agent_cc.allowed_tools(["read", "subagent_create"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'allowed_tools'`.

- [ ] **Step 3: Implement**

Append to `agent_cc.py`:

```python
TOOL_NAMES = {
    "read": "Read",
    "bash": "Bash",
    "edit": "Edit",
    "write": "Write",
    "grep": "Grep",
    "find": "Glob",
    "ls": "Bash",
}


def allowed_tools(tools: list[str] | None) -> list[str] | None:
    """SSSF's tool names as a Claude Code --allowedTools list.

    None means every tool, matching the config's "no tools key" semantics.
    An unmappable name raises rather than being dropped: a silently filtered
    tool is invisible at runtime, which is precisely the failure the config
    file warns about for pi extensions.
    """
    if tools is None:
        return None
    mapped: list[str] = []
    unknown: list[str] = []
    for tool in tools:
        name = TOOL_NAMES.get(tool)
        if name is None:
            unknown.append(tool)
        elif name not in mapped:
            mapped.append(name)
    if unknown:
        raise ValueError(
            f"no Claude Code equivalent for tool(s): {', '.join(unknown)}. "
            f"pi extension tools (subagent_*) have no counterpart — remove them "
            f"from this agent, or run it on coding_agent: pi.")
    return mapped
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: PASS, 9 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_agent_cc.py
git commit -m "feat: map SSSF tool names to Claude Code, rejecting unmappable ones"
```

---

### Task 8: `agent_cc` model resolution and context window

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_agent_cc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_cc.py`:

```python
def test_resolve_model_splits_provider_and_id():
    assert agent_cc.resolve_model("anthropic/claude-opus-5") == ("anthropic", "claude-opus-5")


def test_a_bare_pattern_is_rejected():
    with pytest.raises(ValueError, match="provider/model-id"):
        agent_cc.resolve_model("claude-opus-5")


def test_a_foreign_provider_is_rejected():
    with pytest.raises(ValueError, match="not served by"):
        agent_cc.resolve_model("openai/gpt-5.6-terra")


def test_context_window_is_known_for_a_listed_model():
    assert agent_cc.context_window("anthropic", "claude-opus-5") == 1_000_000


def test_context_window_falls_back_for_an_unlisted_model():
    assert agent_cc.context_window("anthropic", "claude-future-9") == 200_000
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'resolve_model'`.

- [ ] **Step 3: Implement**

Append to `agent_cc.py`:

```python
PROVIDERS = {"anthropic"}

# Claude Code resolves model ids server-side, so there is no catalog to probe
# the way pi's --list-models provides one. These are the ceilings SSSF reports
# for context occupancy; an unlisted id gets a conservative floor rather than
# a guess that would overstate headroom.
CONTEXT_WINDOWS = {
    "claude-opus-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000


def resolve_model(pattern: str) -> tuple[str, str]:
    """Resolve a config model pattern to an explicit (provider, model_id) pair.

    Same contract as agent_pi.resolve_model, minus the catalog lookup: the
    shape is validated, the provider is checked, and the bare id goes to
    --model.
    """
    if "/" not in pattern:
        raise ValueError(f"model {pattern!r} must be written provider/model-id, "
                         f"e.g. anthropic/claude-opus-5")
    provider, model_id = pattern.split("/", 1)
    if provider not in PROVIDERS:
        raise ValueError(f"provider {provider!r} is not served by coding_agent "
                         f"claude_code — expected one of {', '.join(sorted(PROVIDERS))}")
    return provider, model_id


def context_window(provider: str, model_id: str) -> int:
    """The model's context ceiling. 0 is never returned; unknown ids get a floor."""
    return CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: PASS, 14 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_agent_cc.py
git commit -m "feat: add Claude Code model resolution and context windows"
```

---

### Task 9: `agent_cc` session-id mapping

`pi --session-id` is create-or-continue. Claude Code's `--session-id` requires a UUID and refuses one that already exists; continuing is `--resume`. SSSF mints `sssf-<adw>-<agent>-<hex>`, which is not a UUID.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_agent_cc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_cc.py`:

```python
import uuid as uuid_module


def test_first_send_mints_a_uuid_and_does_not_resume(tmp_path):
    minted, resume = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    assert resume is False
    uuid_module.UUID(minted)  # raises if it is not a real UUID


def test_a_later_send_reuses_the_same_uuid_and_resumes(tmp_path):
    first, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    second, resume = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")

    assert second == first
    assert resume is True


def test_two_agents_get_different_uuids(tmp_path):
    builder, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-builder-9f2a")
    planner, _ = agent_cc.session_uuid(str(tmp_path), "sssf-abcd1234-planner-1b3c")

    assert builder != planner
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'session_uuid'`.

- [ ] **Step 3: Implement**

Add `import json`, `import uuid`, and `from pathlib import Path` to `agent_cc.py`'s imports, then append:

```python
SESSION_MAP_NAME = "cc_sessions.json"


def session_uuid(session_dir: str, sssf_session_id: str) -> tuple[str, bool]:
    """Map an SSSF session id to a Claude Code UUID. Returns (uuid, resume).

    The mapping is persisted beside the agent's other session state, because it
    has to survive across sends within a phase AND across the ADW processes
    that join an existing --adw-id. A known id resumes; an unknown one mints.

    This is what preserves hard rule 2: a JSON-parse retry or a gate correction
    re-enters the SAME context window, exactly as it does under pi.
    """
    path = Path(session_dir) / SESSION_MAP_NAME
    mapping = json.loads(path.read_text()) if path.exists() else {}
    existing = mapping.get(sssf_session_id)
    if existing:
        return existing, True
    minted = str(uuid.uuid4())
    mapping[sssf_session_id] = minted
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2))
    return minted, False
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: PASS, 17 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_agent_cc.py
git commit -m "feat: persist an SSSF-to-Claude-Code session id map so corrections resume"
```

---

### Task 10: `agent_cc` command construction

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_agent_cc.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_cc.py`:

```python
from adw_modules.data_types import AgentRequest


def _request(**overrides) -> AgentRequest:
    defaults = dict(
        prompt="do the thing",
        system_prompt="you are a builder",
        model="anthropic/claude-opus-5",
        thinking="medium",
        session_id="sssf-abcd1234-builder-9f2a",
        session_dir="/tmp/sessions",
        raw_output_path="/tmp/raw.jsonl",
        tools=["read", "bash"],
        extensions=[],
        cwd="/repo",
    )
    defaults.update(overrides)
    return AgentRequest(**defaults)


def test_command_creates_a_session_on_the_first_send():
    cmd = agent_cc.build_command(_request(), "11111111-2222-3333-4444-555555555555",
                                 resume=False)

    assert "--session-id" in cmd
    assert "--resume" not in cmd
    assert cmd[cmd.index("--session-id") + 1] == "11111111-2222-3333-4444-555555555555"


def test_command_resumes_on_a_later_send():
    cmd = agent_cc.build_command(_request(), "11111111-2222-3333-4444-555555555555",
                                 resume=True)

    assert "--resume" in cmd
    assert "--session-id" not in cmd


def test_command_carries_model_tools_and_prompt():
    cmd = agent_cc.build_command(_request(), "11111111-2222-3333-4444-555555555555",
                                 resume=False)

    assert cmd[cmd.index("--model") + 1] == "claude-opus-5"
    assert cmd[cmd.index("--allowedTools") + 1] == "Read,Bash"
    assert cmd[-1] == "do the thing", "the prompt is the final positional argument"
    assert "--output-format" in cmd and cmd[cmd.index("--output-format") + 1] == "stream-json"


def test_no_tools_key_means_no_allowlist_flag():
    cmd = agent_cc.build_command(_request(tools=None),
                                 "11111111-2222-3333-4444-555555555555", resume=False)

    assert "--allowedTools" not in cmd
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'build_command'`.

- [ ] **Step 3: Implement**

Add `import os` to `agent_cc.py`'s imports and `from .data_types import AgentRequest, AgentResult`, `from .utils import now_iso, operator_env, resolve_argv`. Then append:

```python
CLAUDE_PATH = os.environ.get("CLAUDE_CODE_PATH", "claude")


def build_command(request: AgentRequest, session_uuid_value: str,
                  resume: bool) -> list[str]:
    """The full argv for one non-interactive Claude Code turn.

    Pure and separately testable: everything that decides WHAT runs lives here,
    so `run` is left with only the streaming.
    """
    _, model_id = resolve_model(request.model)
    cmd = [
        CLAUDE_PATH, "-p",
        "--output-format", "stream-json", "--verbose",
        "--model", model_id,
        "--append-system-prompt", request.system_prompt,
        "--permission-mode", "acceptEdits",
    ]
    cmd += ["--resume", session_uuid_value] if resume else ["--session-id", session_uuid_value]
    tools = allowed_tools(request.tools)
    # `is not None`, not a truthiness test: None means "every tool" and an empty
    # list means "no tools", and `if tools:` collapses those two opposites into
    # the same branch — handing a deliberately tool-less agent the full set.
    # Task 13's validate_agent rejects the empty list before it can reach here.
    if tools is not None:
        cmd += ["--allowedTools", ",".join(tools)]
    cmd.append(request.prompt)
    return resolve_argv(cmd)
```

Add a test pinning the distinction:

```python
def test_an_empty_tool_list_is_not_the_same_as_no_tools_key():
    """`None` means every tool; `[]` means none. They must not collapse.

    config.md states an empty list "is not 'all tools' — it is a tool-less
    agent". A truthiness test would silently grant the full set instead.
    """
    every = agent_cc.build_command(_request(tools=None),
                                   "11111111-2222-3333-4444-555555555555", resume=False)
    none_at_all = agent_cc.build_command(_request(tools=[]),
                                         "11111111-2222-3333-4444-555555555555", resume=False)

    assert "--allowedTools" not in every
    assert "--allowedTools" in none_at_all
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: PASS, 21 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_agent_cc.py
git commit -m "feat: build the Claude Code command line, create vs resume"
```

---

### Task 11: Widen the tool-tracker contract to a list

Claude Code can return several `tool_result` blocks in one user message, so a tracker that returns at most one record per event would silently drop calls. Both backends move to returning a list; `agent_pi` returns zero or one element, which is what it already meant.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_pi.py` (`ToolCallTracker.observe`)
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agents.py` (`_event_forwarder`, ~line 237)
- Test: `tests/test_tool_tracker.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tool_tracker.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_tool_tracker.py -v`
Expected: FAIL — `observe` returns a dict, not a list (`assert isinstance(records, list)`).

- [ ] **Step 3: Implement**

In `agent_pi.py`, change `ToolCallTracker.observe`'s signature and its three return points:

```python
    def observe(self, event: dict) -> list[dict]:
        """Returns the records for any tool calls that finished on this event.

        A list, not an optional single record: Claude Code can close several
        calls in one message, and both backends have to normalize to the same
        shape for agents._event_forwarder to stay backend-agnostic. pi closes
        at most one at a time, so this is [] or a single-element list.
        """
```

Replace each `return None` inside `observe` with `return []`, and the final `return record` with `return [record]`. Update the docstring line in the class docstring that says "one per completed call" to note the list return.

In `agents.py`, change `_event_forwarder`'s inner function from a single-record check to a loop:

```python
    def forward(event: dict) -> None:
        for record in tracker.observe(event):
            # The call's span rides the columns; duration_ms stays in the
            # payload as the backend's own authoritative number.
            run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                         type="tool_call", name=record.pop("label"),
                                         started_at=record.pop("started_at", None),
                                         ended_at=record.pop("ended_at", None),
                                         payload={**record, "agent": agent_name}))
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/ -v`
Expected: PASS, 34 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_pi.py
git add .claude/skills/sssf/templates/adws/adw_modules/agents.py tests/test_tool_tracker.py
git commit -m "refactor: tool trackers return a list so a backend can close several calls at once"
```

---

### Task 12: `CcToolCallTracker`

Claude Code announces a call as a `tool_use` block in an assistant message and returns it as a `tool_result` block in a later user message. This pairs them into the record shape `agent_pi` already emits, so `tracer.py`, `console.py`, and the visualizer need no changes.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_tool_tracker.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_tool_tracker.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_tool_tracker.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'CcToolCallTracker'`.

- [ ] **Step 3: Implement**

Add `import time` to `agent_cc.py`'s imports, then append:

```python
RESULT_SNIPPET_CHARS = 20_000
ARG_VALUE_CHARS = 20_000
LABEL_CHARS = 80

# The arg that identifies a call at a glance, in the order Claude Code's tools
# tend to use. Mirrors agent_pi.PRIMARY_ARGS so labels read the same in the
# trace regardless of which backend produced them.
PRIMARY_ARGS = ("command", "file_path", "path", "pattern", "query", "url")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _label(tool: str, args: dict) -> str:
    """One-line human name for a tool call: `Bash: dotnet build`."""
    value = next((args[key] for key in PRIMARY_ARGS
                  if isinstance(args.get(key), str) and args[key].strip()), "")
    if not value:
        value = next((v for v in args.values() if isinstance(v, str) and v.strip()), "")
    value = " ".join(str(value).split())
    return f"{tool}: {_clip(value, LABEL_CHARS)}" if value else tool


def _result_text(block: dict) -> str:
    """Claude Code's tool_result content is a string or a list of text blocks."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
    return ""


class CcToolCallTracker:
    """Folds Claude Code's tool stream into ONE normalized record per call.

    Claude Code announces a call as a `tool_use` block inside an assistant
    message and returns it as a `tool_result` block inside a later user
    message. Only the result knows the outcome, so that is where a record is
    emitted — and a single user message may close several calls at once, which
    is why observe() returns a list.

    The record shape is identical to agent_pi.ToolCallTracker's, so the tracer,
    the console and the UI never learn which backend produced a call.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict] = {}

    def observe(self, event: dict) -> list[dict]:
        etype = event.get("type", "")
        content = (event.get("message") or {}).get("content") or []
        if not isinstance(content, list):
            return []
        if etype == "assistant":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self._announce(block.get("id"), block.get("name"), block.get("input"))
            return []
        if etype != "user":
            return []
        return [self._close(block) for block in content
                if isinstance(block, dict) and block.get("type") == "tool_result"]

    def _announce(self, call_id, tool, args) -> None:
        if not call_id:
            return
        self._open[str(call_id)] = {
            "tool": tool or "",
            "args": args or {},
            "started_at": now_iso(),      # wall clock, for the row
            "clock": time.monotonic(),    # monotonic, for duration
        }

    def _close(self, block: dict) -> dict:
        call_id = str(block.get("tool_use_id") or "")
        opened = self._open.pop(call_id, {})
        tool = str(opened.get("tool") or "tool")
        args = opened.get("args") or {}
        record = {
            "tool": tool,
            "tool_call_id": call_id,
            "args": {key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                     for key, value in args.items()},
            "ok": not block.get("is_error", False),
            "label": _label(tool, args),
            "ended_at": now_iso(),
        }
        text = _result_text(block)
        if text:
            record["result_snippet"] = _clip(text, RESULT_SNIPPET_CHARS)
        if opened.get("started_at"):
            record["started_at"] = opened["started_at"]
        if opened.get("clock"):
            record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
        return record
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_tool_tracker.py -v`
Expected: PASS, 6 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_tool_tracker.py
git commit -m "feat: normalize Claude Code tool calls into the shared record shape"
```

---

### Task 13: `agent_cc.run`

The one subprocess integration point. `_popen` is a module-level seam so the streaming logic is testable without the binary.

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_cc.py`
- Test: `tests/test_agent_cc.py`

**Carried over from the Task 6 review — do this as part of this task.** `apply_thinking`
currently pops `MAX_THINKING_TOKENS` *before* `thinking_env` validates the level, so an
unknown level mutates the caller's dict and then raises. Harmless at the call site below
(the env is fresh and discarded on error), but it is a side effect on a failed call.
Restructure it to validate first, which also avoids looking the level up twice:

```python
def apply_thinking(env: dict[str, str], level: str) -> dict[str, str]:
    """Make `env` reflect `level`, and return it.

    A dict of things to SET cannot express "off": the child environment starts
    as a copy of the operator's, so leaving MAX_THINKING_TOKENS alone lets an
    inherited value through and an agent configured `off` thinks anyway. The
    variable is therefore removed first, then set only when the level asks for
    a budget — and the level is validated before anything is touched, so a bad
    level leaves the environment exactly as it found it.
    """
    budget = THINKING_TOKENS.get(level)
    if budget is None:
        raise ValueError(f"unknown thinking level {level!r} — expected one of "
                         f"{', '.join(THINKING_TOKENS)}")
    env.pop("MAX_THINKING_TOKENS", None)
    if budget:
        env["MAX_THINKING_TOKENS"] = str(budget)
    return env
```

Add a test pinning the new guarantee:

```python
def test_apply_thinking_leaves_the_env_alone_when_the_level_is_bad():
    env = {"MAX_THINKING_TOKENS": "31337"}

    with pytest.raises(ValueError, match="unknown thinking level"):
        agent_cc.apply_thinking(env, "ludicrous")

    assert env["MAX_THINKING_TOKENS"] == "31337", "a failed call must not mutate"
```

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent_cc.py`:

```python
import json as json_module


class FakeProcess:
    """Stands in for a Popen handle: an iterable stdout and a return code."""

    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.stderr = _FakeStderr()
        self.pid = 4242
        self._returncode = returncode

    def wait(self):
        return self._returncode


class _FakeStderr:
    @staticmethod
    def read():
        return ""


def _stream(*events):
    return [json_module.dumps(event) + "\n" for event in events]


def test_run_collects_text_cost_and_tokens(tmp_path, monkeypatch):
    events = _stream(
        {"type": "system", "subtype": "init", "session_id": "x"},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "working"}],
            "usage": {"input_tokens": 100, "output_tokens": 20}}},
        {"type": "result", "subtype": "success", "result": '{"status": "success"}',
         "total_cost_usd": 0.0123, "usage": {"input_tokens": 100, "output_tokens": 20}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))

    result = agent_cc.run(_request(session_dir=str(tmp_path),
                                   raw_output_path=str(tmp_path / "raw.jsonl")))

    assert result.text == '{"status": "success"}'
    assert result.cost == pytest.approx(0.0123)
    assert result.tokens == 120
    assert result.returncode == 0


def test_run_writes_the_raw_stream_to_disk(tmp_path, monkeypatch):
    events = _stream({"type": "result", "subtype": "success", "result": "done",
                      "total_cost_usd": 0.0, "usage": {}})
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))
    raw = tmp_path / "raw.jsonl"

    agent_cc.run(_request(session_dir=str(tmp_path), raw_output_path=str(raw)))

    assert raw.exists()
    assert "result" in raw.read_text()


def test_run_forwards_events_to_the_callback(tmp_path, monkeypatch):
    events = _stream(
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t", "name": "Read", "input": {"file_path": "a.cs"}}]}},
        {"type": "result", "subtype": "success", "result": "ok",
         "total_cost_usd": 0.0, "usage": {}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))
    seen = []

    agent_cc.run(_request(session_dir=str(tmp_path),
                          raw_output_path=str(tmp_path / "raw.jsonl")),
                 on_event=seen.append)

    assert [event["type"] for event in seen] == ["assistant", "result"]


def test_run_reports_spawn_and_exit(tmp_path, monkeypatch):
    events = _stream({"type": "result", "subtype": "success", "result": "ok",
                      "total_cost_usd": 0.0, "usage": {}})
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))
    spawned, exited = [], []

    agent_cc.run(_request(session_dir=str(tmp_path),
                          raw_output_path=str(tmp_path / "raw.jsonl")),
                 on_spawn=spawned.append, on_exit=exited.append)

    assert spawned == [4242]
    assert exited == [4242]


def test_run_raises_when_the_agent_fails_with_no_output(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess([], returncode=1))

    with pytest.raises(RuntimeError, match="claude exited 1"):
        agent_cc.run(_request(session_dir=str(tmp_path),
                              raw_output_path=str(tmp_path / "raw.jsonl")))


def test_run_fills_the_usage_breakdown(tmp_path, monkeypatch):
    # agents.execute reports the PHASE total from result.usage, not from
    # result.tokens. An empty breakdown would log 0 tokens for the phase while
    # the run banner showed the right number — two numbers disagreeing in the
    # same trace.
    events = _stream(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}],
         "usage": {"input_tokens": 100, "output_tokens": 20,
                   "cache_read_input_tokens": 7, "cache_creation_input_tokens": 3}}},
        {"type": "result", "subtype": "success", "result": "done",
         "total_cost_usd": 0.5, "usage": {}},
    )
    monkeypatch.setattr(agent_cc, "_popen", lambda *a, **k: FakeProcess(events))

    result = agent_cc.run(_request(session_dir=str(tmp_path),
                                   raw_output_path=str(tmp_path / "raw.jsonl")))

    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.usage.cache_read_tokens == 7
    assert result.usage.cache_write_tokens == 3
    assert result.usage.total_tokens == 120
    assert result.usage.total_cost == pytest.approx(0.5)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: FAIL with `AttributeError: ... has no attribute 'run'`.

- [ ] **Step 3: Implement**

Add `import subprocess` and `from typing import Callable, Optional` to `agent_cc.py`'s imports, then append:

```python
def _popen(cmd: list[str], env: dict[str, str], cwd: str):
    """Launch the agent. A seam: tests replace this to exercise the stream logic.

    stdin is DEVNULL, deliberately — the same hazard agent_pi documents. The
    prompt travels in argv, so the child never needs stdin, but inheriting the
    parent's means a non-TTY the child may block on forever. That failure is
    silent and total: no events, no bytes, an empty raw_output.jsonl.
    """
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1, cwd=cwd, env=env)


def validate_agent(agent) -> list[str]:
    """Config problems this backend can detect before anything spawns."""
    problems = []
    if agent.harness_engineering:
        problems.append(
            f"agent {agent.name!r}: harness_engineering is a pi extension mechanism "
            f"with no Claude Code equivalent ({', '.join(agent.harness_engineering)}) "
            f"— remove it, or run this agent on coding_agent: pi")
    # An agent allowed nothing cannot act. config.md already says an empty list
    # "is not 'all tools' — it is a tool-less agent, and it will stall", so say
    # so at validation rather than spawning something that cannot work. Omitting
    # the key entirely is how you ask for every tool.
    if agent.tools is not None and not agent.tools:
        problems.append(
            f"agent {agent.name!r}: `tools: []` allows nothing, so this agent "
            f"cannot act — name the tools it needs, or omit `tools` for all of them")
    try:
        allowed_tools(agent.tools)
    except ValueError as error:
        problems.append(f"agent {agent.name!r}: {error}")
    return problems


def run(request: AgentRequest, on_event: Optional[Callable[[dict], None]] = None,
        on_spawn: Optional[Callable[[int], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None) -> AgentResult:
    """Run one non-interactive Claude Code turn.

    Same contract as agent_pi.run: tail the JSONL stream, forward every event
    as it arrives, and return the turn's text, usage and cost.
    """
    provider, model_id = resolve_model(request.model)
    session_value, resume = session_uuid(request.session_dir, request.session_id)
    cmd = build_command(request, session_value, resume)

    # apply_thinking, not env.update(thinking_env(...)): the child env starts as
    # a copy of the operator's, so an inherited MAX_THINKING_TOKENS has to be
    # removed for `off` to mean off.
    env = apply_thinking(operator_env(), request.thinking)

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = AgentResult(session_id=request.session_id,
                         context_window=context_window(provider, model_id))
    process = _popen(cmd, env, request.cwd)
    if on_spawn:
        on_spawn(process.pid)

    with raw_path.open("a") as raw:
        for line in process.stdout:
            raw.write(line)
            raw.flush()                      # events land on disk as they happen
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            _absorb(result, event)
            if on_event:
                on_event(event)

    stderr = process.stderr.read() if process.stderr else ""
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)
    if result.returncode != 0 and not result.text:
        raise RuntimeError(f"claude exited {result.returncode}: {stderr.strip()[-800:]}")
    return result


def _absorb(result: AgentResult, event: dict) -> None:
    """Fold one stream event into the running result.

    Usage accrues per assistant turn; the terminal `result` event carries the
    authoritative cost and the final text. Occupancy is read off the last
    assistant turn, matching agent_pi's rule.

    UsageBreakdown.add_turn is NOT used here: it parses pi's usage shape
    (`input`, `output`, a nested `cost` dict). Claude Code sends `input_tokens`
    / `output_tokens` and reports cost only once, on the result event, so
    add_turn would fold in silent zeros — and agents.execute reports the
    phase's tokens from this breakdown, not from `tokens`.
    """
    etype = event.get("type")
    if etype == "assistant":
        usage = (event.get("message") or {}).get("usage") or {}
        inputs = int(usage.get("input_tokens") or 0)
        outputs = int(usage.get("output_tokens") or 0)
        turn = inputs + outputs
        if turn:
            result.tokens += turn
            result.context_tokens = turn
            result.usage.input_tokens += inputs
            result.usage.output_tokens += outputs
            result.usage.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)
            result.usage.cache_write_tokens += int(
                usage.get("cache_creation_input_tokens") or 0)
            result.usage.total_tokens += turn
    elif etype == "result":
        text = event.get("result")
        if isinstance(text, str) and text:
            result.text = text
        cost = float(event.get("total_cost_usd") or 0.0)
        result.cost += cost
        # Claude Code prices the turn as one number, so the per-component cost
        # fields stay zero and only the total is claimed. Reporting a made-up
        # split would be worse than reporting none.
        result.usage.total_cost += cost
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_agent_cc.py -v`
Expected: PASS, 27 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/agent_cc.py tests/test_agent_cc.py
git commit -m "feat: stream a Claude Code turn, collecting text, usage and cost"
```

---

### Task 14: Backend dispatch in `agents.py`

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agents.py:18,61-69,109,112,127,237`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agent_pi.py` (add `validate_agent`)
- Test: `tests/test_agents_dispatch.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_agents_dispatch.py`:

```python
"""Backend selection and config validation across two coding agents."""

import pytest

from adw_modules import agent_cc, agent_pi, agents
from adw_modules.data_types import AgentConfig, PromptEngineering


def _agent(**overrides) -> AgentConfig:
    defaults = dict(
        name="builder",
        coding_agent="claude_code",
        model="anthropic/claude-opus-5",
        thinking="medium",
        purpose="Implement the plan exactly.",
        prompt_engineering=PromptEngineering(system="system.md", user="user.md"),
        tools=["read", "bash"],
        harness_engineering=[],
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def test_claude_code_agents_dispatch_to_agent_cc():
    assert agents.backend_for(_agent()) is agent_cc


def test_pi_agents_dispatch_to_agent_pi():
    assert agents.backend_for(_agent(coding_agent="pi",
                                     model="google/gemini-3.6-flash")) is agent_pi


def test_an_unknown_backend_is_rejected():
    with pytest.raises(SystemExit, match="unknown coding_agent"):
        agents.backend_for(_agent(coding_agent="cursor"))


def test_harness_engineering_on_claude_code_is_a_config_error():
    problems = agent_cc.validate_agent(_agent(harness_engineering=["subagents.ts"]))

    assert problems
    assert "harness_engineering" in problems[0]


def test_a_pi_extension_tool_on_claude_code_is_a_config_error():
    problems = agent_cc.validate_agent(_agent(tools=["read", "subagent_create"]))

    assert problems
    assert "subagent_create" in problems[0]


def test_a_clean_claude_code_agent_has_no_problems():
    assert agent_cc.validate_agent(_agent()) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_agents_dispatch.py -v`
Expected: FAIL with `AttributeError: module 'adw_modules.agents' has no attribute 'backend_for'`.

- [ ] **Step 3: Implement**

In `agent_pi.py`, add a matching no-op hook so both backends satisfy the same interface:

```python
def validate_agent(agent) -> list[str]:
    """Config problems this backend can detect. pi accepts everything the
    schema allows; the model check lives in resolve_model."""
    return []
```

**Carried over from the Task 9 review — do this as part of this task.** `agents.py` hardcodes
the per-agent session directory as `agent_dir / "pi_sessions"`, so a Claude Code run writes
its session state into a directory named after the other backend. Rename it to `"sessions"`,
which is backend-neutral and matches what the directory actually holds. It is a runtime path
under `data_dir`, not a tracked artifact, so nothing depends on the old name.

**Also carried over from the Task 12 review — do this as part of this task.** `_event_forwarder`'s
`forward` callback runs inside the backend's stream loop with no `try/except` anywhere on the
path, so any exception a tracker raises while parsing a malformed event terminates the whole
agent run. Tracing is observability and must never be able to kill the work it observes. The
specific crashes found were fixed inside `agent_cc`'s tracker, but the systemic gap belongs
here — wrap the loop body so a bad event costs one trace row, not the run:

```python
    def forward(event: dict) -> None:
        try:
            records = tracker.observe(event)
        except Exception as error:                  # noqa: BLE001 — see below
            # A tracker parses a subprocess's stdout. Malformed JSON is the
            # subprocess's problem, not a reason to abort work that is otherwise
            # going fine — so the failure is recorded and the run continues.
            run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                         type="log", name="tool_trace_failed",
                                         payload={"agent": agent_name,
                                                  "error": str(error)[:500]}))
            return
        for record in records:
```

with the existing `EventRecord` emission as the loop body. The bare `except Exception` is
deliberate and is the one place in this codebase where it is right: the alternative is
enumerating every shape a backend's stream could take, which is exactly the guess that made
this fatal in the first place.

In `agents.py`, change the import on line 18 to:

```python
from . import agent_cc, agent_pi, permissions, prompts
```

and add `AgentResult` to the `.data_types` import on line 19-22, which after Task 5 must read:

```python
from .data_types import (AgentCall, AgentConfig, AgentRequest, AgentResult,
                         EnvelopeBase, EventRecord, GateCheck, GateReport, Phase,
                         SSSFConfig, UsageBreakdown)
```

Add, directly after the `GateFailure` class:

```python
BACKENDS = {"pi": agent_pi, "claude_code": agent_cc}


def backend_for(agent: AgentConfig):
    """The module that runs this agent. Both expose run/resolve_model/
    context_window/validate_agent, so callers never branch on the name."""
    backend = BACKENDS.get(agent.coding_agent)
    if backend is None:
        raise SystemExit(f"agent {agent.name!r}: unknown coding_agent "
                         f"{agent.coding_agent!r} — expected one of "
                         f"{', '.join(sorted(BACKENDS))}")
    return backend
```

In `validate()`, delete the three lines that reject a non-pi `coding_agent` and replace the `agent_pi.resolve_model(agent.model)` block with:

```python
        try:
            backend = backend_for(agent)
        except SystemExit as e:
            problems.append(str(e))
            continue
        problems.extend(backend.validate_agent(agent))
        try:
            backend.resolve_model(agent.model)
        except ValueError as e:
            problems.append(f"agent {name!r}: {e}")
```

In `execute()`, replace the three `agent_pi` references: the annotation `latest: agent_pi.AgentResult | None = None` and the `def send(...) -> agent_pi.AgentResult:` annotation become `AgentResult` (imported from `.data_types`), and `result = agent_pi.run(` becomes `result = backend_for(agent).run(`.

In `_event_forwarder`, the tracker choice becomes backend-aware. Change its signature to accept the agent and pick the tracker:

```python
def _event_forwarder(run, phase: Phase, agent_name: str, backend):
    """One tool_call event per real tool call, with its exact args and result."""
    tracker = backend.ToolCallTracker()
```

Add an alias at the bottom of `agent_cc.py` so both modules expose the same name:

```python
ToolCallTracker = CcToolCallTracker
```

Update the one call site in `execute()` to pass the backend:

```python
            on_event=_event_forwarder(run, phase, agent.name, backend_for(agent)),
```

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: PASS, 50 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_modules/ tests/test_agents_dispatch.py
git commit -m "feat: dispatch agents to a coding-agent backend instead of hard-coding pi"
```

---

### Task 15: `adw_trace.py` trace reader

The `sqlite3` CLI is not installed, so every observability instruction in the justfile, the cookbooks, and `references/observability.md` currently fails. Python's stdlib `sqlite3` module is always present.

**Files:**
- Create: `.claude/skills/sssf/templates/adws/adw_trace.py`
- Test: `tests/test_adw_trace.py`

The installer stamps `templates/adws/` recursively, so a new file here is picked up with no installer change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_adw_trace.py`:

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_adw_trace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adw_trace'`.

- [ ] **Step 3: Implement**

Create `.claude/skills/sssf/templates/adws/adw_trace.py`:

```python
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
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.close()


def _print(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("(no rows)")
        return
    columns = rows[0].keys()
    widths = [max(len(c), max(len(str(r[c] if r[c] is not None else "")) for r in rows))
              for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(row[c] if row[c] is not None else "").ljust(w)
                        for c, w in zip(columns, widths)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("sessions")
    for name in ("phases", "gates"):
        p = sub.add_parser(name)
        p.add_argument("adw_id")
    events = sub.add_parser("events")
    events.add_argument("adw_id")
    events.add_argument("--type", dest="event_type", default=None)
    sub.add_parser("processes")

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
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_adw_trace.py -v`
Expected: PASS, 5 passed.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/sssf/templates/adws/adw_trace.py tests/test_adw_trace.py
git commit -m "feat: add a stdlib trace reader so observability works without the sqlite3 CLI"
```

---

### Task 16: Documentation

Every doc that asserts "v1 is pi only" or shells out to `sqlite3` is now wrong. Stale docs are a correctness problem here: the SKILL.md startup section exists specifically to stop the orchestrator guessing, so it must not itself mislead.

**Files:**
- Modify: `.claude/skills/sssf/SKILL.md` (the "## v1 scope" section; hard rule 9)
- Modify: `.claude/skills/sssf/cookbooks/install.md` (post-install checklist)
- Modify: `.claude/skills/sssf/cookbooks/sssf_overview.md:26,40`
- Modify: `.claude/skills/sssf/cookbooks/create_config.md:21,33`
- Modify: `.claude/skills/sssf/references/config.md:45`
- Modify: `.claude/skills/sssf/references/observability.md`
- Modify: `.claude/skills/sssf/templates/justfile`
- Modify: `README.md` ("Where it can still fail")

- [ ] **Step 1: Find every stale claim**

```bash
grep -rn "v1\|claude_code\|sqlite3 " .claude/skills/sssf/ README.md | grep -v "^Binary"
```

- [ ] **Step 2: Rewrite the scope statement**

In `SKILL.md`, replace the `## v1 scope` section with:

```markdown
## Coding-agent backends

Two backends. `coding_agent: pi` (default) runs the Pi agent; `coding_agent: claude_code`
runs Claude Code. Both expose the same interface to `agents.py`, so an ADW never knows
which one ran a phase.

Two differences are real and enforced at validation, not discovered at runtime:

- `harness_engineering` is a pi extension mechanism. A `claude_code` agent that declares
  one fails validation.
- The `subagent_*` tools come from that extension, so they are pi-only too.

The visualizer app ships in a later pass — read the trace with `uv run adws/adw_trace.py`.
```

- [ ] **Step 3: Replace every `sqlite3` shell-out**

In `templates/justfile`, `references/observability.md`, and `cookbooks/install.md`, replace each `sqlite3 adws/adw_data/sssf.db "select ..."` with the matching `uv run adws/adw_trace.py <subcommand>`. The smoke-test line in `install.md` becomes:

```bash
uv run adws/adw_trace.py sessions
```

Add to the `install.md` post-install checklist, replacing the current item 2:

```markdown
2. **Your coding agent is installed and on PATH** — `pi --version` for `coding_agent: pi`,
   or `claude --version` for `coding_agent: claude_code`. Set `PI_PATH` or
   `CLAUDE_CODE_PATH` in `.env` if the binary is not on PATH.
```

- [ ] **Step 3a: Document the session-directory rename as a migration hazard**

Raised in the Task 14 review, and it corrects a claim made earlier in this plan. The rename
of the per-agent session directory from `pi_sessions` to `sessions` was described as safe
because "nothing depends on the old name". That is true for Claude Code agents, which never
had state under the old name — but **false for pi agents with existing session state**.
`agent_map.json` persists each agent's session id across runs, and pi's `--session-id` is
create-or-continue, so an ADW resumed with `--adw-id` from before this change hands pi an id
whose directory is now empty. pi does not error: it silently creates a fresh session under
that id, and the agent loses its conversation history. Silent context loss is the worst
failure mode to diagnose, so it has to be written down.

Also update `references/handoff.md`, which still documents the directory as `pi_sessions/`.

Add to `cookbooks/install.md` and `README.md`:

```markdown
**Upgrading an existing installation.** The per-agent session directory was renamed from
`pi_sessions/` to `sessions/`. A run resumed with `--adw-id` from before the rename will
find an empty directory — and pi's `--session-id` creates-or-continues, so it starts a
fresh session rather than failing, and that agent silently loses its history. Before
resuming an older run, rename the directory under each agent:

    adws/adw_data/sessions/<adw_id>/<agent>/pi_sessions  ->  .../sessions

Or simply start the run again. New installations are unaffected.
```

- [ ] **Step 3b: Document the tool-mapping capability widening**

Raised in the Task 7 review. `ls` maps to `Bash`, so an agent whose config asks only for
`ls` receives arbitrary shell execution on Claude Code. That is deliberate — Claude Code
has no dedicated listing tool — but it is invisible to whoever wrote the config, and this
system's whole premise is that `tools:` is a capability list the operator can reason about.

Add to `references/config.md`, in the section documenting `tools:`:

```markdown
**Tool names are per backend, and one mapping widens capability.** The names in `tools:`
are pi's. On `coding_agent: claude_code` they are translated (`read` → `Read`, `find` →
`Glob`, and so on). One translation is not one-for-one: **`ls` maps to `Bash`**, because
Claude Code has no dedicated listing tool. An agent granted only `ls` therefore gets
arbitrary shell execution on that backend. If that is not what you want, drop `ls` — and
remember that `tools:` was never a sandbox anyway: `writes:` and `protected_files` are
what actually bound an agent, enforced in `adw_modules/permissions.py` after every call.
```

- [ ] **Step 4: Correct the README failure table**

In `README.md`, replace the `coding_agent: claude_code` row with:

```markdown
| A `claude_code` agent declares `harness_engineering` | Rejected at validation, before anything spawns | Extensions are pi-only. Remove the key, or run that agent on `coding_agent: pi` |
```

- [ ] **Step 5: Verify no stale claim survives**

```bash
grep -rn "pi only\|Pi only\|stubbed until v2\|sqlite3 adws" .claude/skills/sssf/ README.md
```

Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/sssf/ README.md
git commit -m "docs: document two coding-agent backends and the stdlib trace reader"
```

---

### Task 17: Live verification against a real repo

Offline tests prove the parsing; only a live run proves the contract. Per the spec, `codec-chat` is not modified — we clone it to a scratch directory and stamp there.

**Files:** none modified. This task produces evidence.

- [ ] **Step 1: Clone codec-chat to scratch and stamp the factory**

```bash
SCRATCH="$LOCALAPPDATA/Temp/claude/sssf-verify"
rm -rf "$SCRATCH" && git clone --depth 1 "file:///C:/Source/Repos/codec-chat" "$SCRATCH"
cd "$SCRATCH" && uv run /c/Source/Repos/super-simple-software-factory/.claude/skills/sssf/scripts/install.py
```

Expected: `sssf installed into ...`, with `adws/adw_trace.py` among the stamped files and `justfile` reported as skipped (codec-chat already has one).

- [ ] **Step 2: Point the roster at Claude Code**

Edit `$SCRATCH/adws/adw_sssf_config/sssf.config.yaml`: set `defaults.coding_agent: claude_code`, `defaults.model: anthropic/claude-opus-5`, delete every per-agent `model:` line, and delete the `harness_engineering:` blocks and the four `subagent_*` tool entries from the `planner` and `scout` agents — both are pi-only and validation will now say so.

- [ ] **Step 3: Verify validation catches a bad config first**

Temporarily re-add `harness_engineering: [adws/adw_data/harness_engineering/subagents.ts]` to the scout agent, then run:

```bash
cd "$SCRATCH" && uv run adws/adw_prompt.py "say hello" --agent scout
```

Expected: exits non-zero with `config validation failed:` naming `harness_engineering` and the scout. Remove the key again before continuing.

- [ ] **Step 4: Run the smallest ADW end to end**

```bash
cd "$SCRATCH" && uv run adws/adw_prompt.py "reply with a one-line summary of this repo" --agent scout
```

Expected: the run completes green, printing a session banner with a non-zero token count and cost.

- [ ] **Step 5: Confirm the trace, rather than trusting the banner**

```bash
cd "$SCRATCH" && uv run adws/adw_trace.py sessions
```

Expected: one row, `status` = `success`, `total_tokens` > 0.

```bash
cd "$SCRATCH" && uv run adws/adw_trace.py events <adw_id> --type tool_call
```

Expected: at least one `tool_call` row, proving `CcToolCallTracker` paired a real call.

- [ ] **Step 6: Run the multi-tool recon ADW**

```bash
cd "$SCRATCH" && uv run adws/adw_scout.py "where is authentication handled in this repo?"
```

Expected: green run; `uv run adws/adw_trace.py phases <adw_id>` shows every phase `success`, and the `tool_call` events number in the several-to-dozens range.

- [ ] **Step 7: Record the evidence and commit**

Append a short "Verified" note to the spec recording the two `adw_id`s, their token/cost totals, and the tool-call counts. Then:

```bash
cd /c/Source/Repos/super-simple-software-factory
git add docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md
git commit -m "docs: record live verification of the Claude Code backend"
```

---

## Deferred improvements

Raised during review, deliberately out of scope for this plan. Recorded so they are not lost.

- **Prompts ride on argv, against a ~32KB Windows ceiling** (found during the Task 10 review).
  Both backends pass the rendered system prompt and the user prompt as argv elements —
  `agent_cc.build_command` via `--append-system-prompt`, and `agent_pi.run` via
  `--system-prompt`. Windows `CreateProcess` caps the whole command line near 32KB, and
  SSSF renders full Markdown templates into `system_prompt`. Typical sizes are safe
  (~7KB), but a large template plus a large prompt approaches the limit, and the failure
  is a Windows-only `OSError: [WinError 206] The filename or extension is too long` that
  would read as a mysterious spawn failure. Neither backend documents a bound. The fix —
  passing the system prompt by file or stdin — changes both backends' invocation shape, so
  it belongs with the profile work rather than here. Pre-existing, not introduced.

- **`agent_pi` collapses `tools: []` into "every tool"** (found during the Task 7 review).
  `agent_pi.run` builds its flag with `if request.tools: cmd += ["--tools", ...]`, so an
  agent configured `tools: []` gets no `--tools` flag at all and pi grants it everything —
  the exact inversion `references/config.md` warns against when it says an empty list "is
  not 'all tools' — it is a tool-less agent, and it will stall". This is **pre-existing**,
  not introduced here; the Claude Code backend fixes it on its own side (Tasks 10 and 13).
  Fixing pi is left out because pi is not installed on this machine, so the behaviour of
  `--tools ""` cannot be verified — and shipping an unverified change to the working
  backend to match a verified one is the wrong trade.

- **Record the resolved binary alongside the bare command** (from the Task 4 quality review).
  `_run` traces `command` as the bare `git status` while executing `C:\...\git.exe status`.
  Two machines that resolve the same bare name to different binaries therefore produce
  identical traces, hiding the one fact needed to diagnose the divergence. The fix is small —
  keep `command` bare for portability and add `resolved_command` to the tracer event payload
  only — but it changes the trace schema's payload shape, so it belongs with the Part B
  observability work rather than here.

## Done criteria

- [ ] `uv run pytest tests/ -v` passes, 55 tests.
- [ ] A `claude_code` roster validates, runs, and produces a green trace in a real repo.
- [ ] `uv run adws/adw_trace.py sessions` works with no `sqlite3` binary installed.
- [ ] `grep -rn "pi only\|sqlite3 adws" .claude/skills/sssf/ README.md` returns nothing.
- [ ] No file in `C:\Source\Repos\codec-chat` is modified (`git -C /c/Source/Repos/codec-chat status` is clean).
