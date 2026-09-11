# SSSF Profile Mechanism + `dotnet-svelte` Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `install.py` probe a repository, discover its real build and test commands, and stamp a factory wired to them — so a fresh install of SSSF into any ASP.NET Core + EF Core + SvelteKit repo runs real checks instead of `echo` placeholders.

**Architecture:** A profile is a directory under `templates/profiles/<name>/` with three installer-side pieces (`profile.yaml`, `detect.py`, `generate.py`) and one stamped piece (`gates/`). Detection produces a typed `ProfileFacts`; generation turns those facts into three plain generated files in the target repo (`quality_blocks.py`, `profile_gates.py`, `profile_overlay.md`). Core modules learn to load those files when present and fall back to shipped defaults when absent, so an un-profiled install behaves exactly as it does today.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, pytest. Target stack under test: ASP.NET Core / EF Core (`.sln`, `.csproj`, xunit, Testcontainers) and SvelteKit 5 (`package.json`, `@sveltejs/kit`), optionally driven by a `justfile`.

**Spec:** `docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md` §5 (Part B), plus the §7 items Part B introduces.

---

## Ground rules for every task

**1. Check your branch before you touch anything.** Run `git rev-parse --abbrev-ref HEAD` first. If it prints `HEAD`, you are detached and MUST stop and report it — a previous run of this workflow lost three commits that way.

**2. The design rule, restated because it is the whole point.** Nothing you write in `templates/profiles/` may name a path specific to one repository. `apps/web`, `Codec.sln`, and `test-api` are values DETECTION produces at install time; they must never appear as literals in profile source. The only places such strings may appear are: generated files inside a target repo, test fixtures, and documentation examples. A reviewer will grep for them.

**3. Every commit ends with this trailer block**, separated from the message body by a blank line:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019yQfXSXQtrrHu6ooNpecG6
```

**4. Do not modify anything under `C:\Source\Repos\codec-chat`.** It is a read-only reference repository. Task 19 probes it; nothing writes to it.

**5. Run tests with `uv run pytest`** from the repo root (`C:\Source\Repos\super-simple-software-factory`). The suite currently passes 85 tests; each task states how many its own file adds.

---

## Deliberate deviations from the spec

Four, each a refinement rather than a reduction. Recorded here so a spec reviewer does not flag them as drift.

1. **§B2 says "writes a concrete `quality.py`". This plan generates `quality_blocks.py` instead.** `quality.py` holds the engine — `_run`, `as_envelope`, artifact capture, tracer events. Generating the whole file would copy that engine into the generator and fork it on the first change. Instead the engine stays hand-written and generic, the generated file holds nothing but data (`BLOCKS: list[QualityCheckSpec]`), and regeneration overwrites a file containing zero hand-written code. Hard rule 8 still holds: the command is code, written down, in the repo.

2. **§B4 lists `doc_policy` among the profile's gates. This plan puts it in core `gates.py`.** The gate contains no .NET and no Svelte: it reads a YAML block and compares changed paths. By the design rule in spec §3, a gate with no stack facts in it is not a stack profile's property. Any repo on any stack can declare a `doc_policy:` block.

3. **§B1 says "enumerate solution projects via `dotnet sln list`". This plan parses the solution file directly.** `dotnet sln list` prints what the file already says, but requires the .NET SDK on PATH during install and costs a subprocess per probe. Parsing `.sln` (a documented line format) and `.slnx` (XML) works offline, is deterministic, and is testable against fixture trees with no toolchain installed.

4. **`QualityCheckSpec` gains a `cwd` field rather than the spec's `npm --prefix <dir>` form.** A `--prefix`-style flag needs a different spelling per package manager (npm `--prefix`, pnpm `--dir`, yarn `--cwd`, bun none), so that table grows a row per manager and is wrong for the next one. A working directory is what every one of them actually means, and it costs one line in `_run`.

---

## File structure

**New, installer-side (read and executed by `install.py`; never stamped into a target repo):**

| File | Responsibility |
|---|---|
| `.claude/skills/sssf/templates/profiles/__init__.py` | Makes `profiles` a package. Empty. |
| `.claude/skills/sssf/templates/profiles/facts.py` | The typed vocabulary every profile shares: `DotnetProject`, `Frontend`, `ProfileFacts`, `QualityBlock`, `GenerationReport`. |
| `.claude/skills/sssf/templates/profiles/registry.py` | Profile lookup by name, and auto-detection across all profiles. |
| `.claude/skills/sssf/templates/profiles/dotnet_svelte/__init__.py` | Re-exports `NAME`, `matches`, `detect`, `generate` so the registry needs one import. |
| `.claude/skills/sssf/templates/profiles/dotnet_svelte/profile.yaml` | Declarative half: display name, detection markers, candidate task-runner recipe names per block role, env prefixes. |
| `.claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py` | Repo probe → `ProfileFacts`. Reads files; spawns only the task runner's summary command. |
| `.claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py` | `ProfileFacts` → the three generated files + a `GenerationReport`. |

**New, stamped into the target repo by the installer:**

| Source | Stamped to | Responsibility |
|---|---|---|
| `templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py` | `adws/adw_modules/gates_dotnet_svelte.py` | The three stack gates: `ef_migration_triad`, `env_example_sync`, `sveltekit_csp`. |

**New, generated into the target repo (plain, editable, overwritten on regeneration):**

| File | Responsibility |
|---|---|
| `adws/adw_modules/quality_blocks.py` | `BLOCKS: list[QualityCheckSpec]` — this repo's real commands, with tiers. |
| `adws/adw_modules/profile_gates.py` | `PROFILE_GATES: list[Callable]` — the stack gates, parameterized with discovered facts. |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | Stack guidance + the list of convention files that were actually found. |

**Modified, core (shipped templates):**

| File | Change |
|---|---|
| `templates/adws/adw_modules/data_types.py` | `QualityCheckSpec` gains `tier` + `cwd`; new `DocPolicyRule`; `SSSFConfig` gains `doc_policy`. |
| `templates/adws/adw_modules/utils.py` | `glob_to_regex` + `path_matches` extracted from `permissions.py`, with `**/` fixed to match zero directories. |
| `templates/adws/adw_modules/permissions.py` | Uses `utils.path_matches`; its private `_glob`/`_matches` are removed. |
| `templates/adws/adw_modules/quality.py` | Blocks become data; `blocks()` loader; `run_tests` = fast tier, `run_quality` = all tiers; `_run` honours `spec.cwd`. |
| `templates/adws/adw_modules/gates.py` | New `doc_policy` gate and `profile_gates()` loader. |
| `templates/adws/adw_modules/agents.py` | `execute()` adds the `profile_overlay` prompt variable. |
| `templates/adws/adw_*.py` (7 files) | Build-phase gate lists gain `*gates.profile_gates()`. |
| `templates/prompt_engineering/builder/system.md` | Toolchain-agnostic wording + `{{profile_overlay}}` placeholder. |
| `templates/sssf.config.yaml` | Commented `doc_policy:` block. |
| `scripts/install.py` | `--profile`, `--no-profile`, `--doctor`; profile application; the report. |
| `references/config.md`, `cookbooks/install.md`, `SKILL.md`, `README.md` | Documentation for all of the above. |

**New tests:** `tests/profile_fixtures.py` plus ten `tests/test_*.py` files named per task.

---

## Task 1: `QualityCheckSpec` learns tiers and a working directory

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/data_types.py` (the `QualityCheckSpec` class)
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/quality.py` (`_run`)
- Test: `tests/test_quality_blocks.py` (new file)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_quality_blocks.py`:

```python
"""Quality blocks are data: a tier, a working directory, and an argv."""

from pathlib import Path
from types import SimpleNamespace

from adw_modules import quality
from adw_modules.data_types import QualityCheckSpec


def _fake_run(tmp_path):
    """The smallest stand-in quality._run actually touches.

    Mirrors the helper in tests/test_quality_launch.py — it reads run.adw_id,
    run.repo_root, run.context_handoff_dir, run.phases[-1], run.tracer.event
    and run.console.note, and nothing else.
    """
    return SimpleNamespace(
        adw_id="testadw",
        repo_root=tmp_path,
        context_handoff_dir=tmp_path,
        phases=[SimpleNamespace(seq=1, phase_id="testadw_01_probe")],
        tracer=SimpleNamespace(event=lambda record: None),
        console=SimpleNamespace(note=lambda message: None),
    )


def test_spec_defaults_to_the_fast_tier_at_the_repo_root():
    spec = QualityCheckSpec(name="x", area="backend", operation="build", argv=["true"])
    assert spec.tier == "fast"
    assert spec.cwd == "."


def test_spec_rejects_an_unknown_tier():
    import pytest
    with pytest.raises(Exception):
        QualityCheckSpec(name="x", area="backend", operation="build",
                         argv=["true"], tier="someday")


def test_run_launches_the_block_in_its_own_cwd(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)
    (tmp_path / "apps" / "web").mkdir(parents=True)

    quality._run(QualityCheckSpec(
        name="check-web", area="frontend", operation="typecheck",
        argv=["git", "status"], cwd="apps/web",
    ), _fake_run(tmp_path))

    assert Path(captured["cwd"]) == tmp_path / "apps" / "web"


def test_run_at_the_repo_root_does_not_append_a_dot_segment(tmp_path, monkeypatch):
    """`cwd="."` must resolve to the repo root itself, not `<root>/.`."""
    captured = {}

    def fake_run(argv, **kwargs):
        captured["cwd"] = kwargs["cwd"]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(quality.subprocess, "run", fake_run)

    quality._run(QualityCheckSpec(
        name="probe", area="backend", operation="lint", argv=["git", "status"],
    ), _fake_run(tmp_path))

    assert Path(captured["cwd"]) == tmp_path
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_quality_blocks.py -v`
Expected: FAIL — `QualityCheckSpec` has no `tier`/`cwd`, so the first test errors on the missing attribute and the cwd tests see `tmp_path` for both.

- [ ] **Step 3: Add the fields**

In `data_types.py`, immediately above `class QualityCheckSpec`, add the tier alias beside the existing `QualityArea` / `QualityOperation` aliases:

```python
QualityArea = Literal["frontend", "backend"]
QualityOperation = Literal["lint", "typecheck", "build"]
# Which pass a block belongs to. `fast` runs inside bounded fix loops, where a
# slow block would multiply its cost by the retry count; `full` adds the blocks
# that need a service to be up (a Testcontainers suite needs Docker) and runs
# only in final verification.
QualityTier = Literal["fast", "full"]
```

Then replace the `QualityCheckSpec` class body with:

```python
class QualityCheckSpec(BaseModel):
    """One deterministic quality command."""

    name: str
    area: QualityArea
    operation: QualityOperation
    argv: list[str]
    timeout_seconds: int = 120
    tier: QualityTier = "fast"
    # Where the command runs, relative to the repo root. A monorepo runs the
    # same command in several frontends, and every package manager spells its
    # "somewhere else" flag differently (npm --prefix, pnpm --dir, yarn --cwd,
    # bun not at all). A working directory is what all of them mean.
    cwd: str = "."
```

- [ ] **Step 4: Honour `cwd` in `_run`**

In `quality.py`, inside `_run`, replace the `cwd=run.repo_root,` argument of `subprocess.run` with:

```python
            cwd=Path(run.repo_root) / spec.cwd,
```

`pathlib` collapses a lone `.` segment on join, so the default keeps launching at the repo root exactly as before.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_quality_blocks.py tests/test_quality_launch.py -v`
Expected: PASS — 5 passed (4 new, 1 pre-existing).

- [ ] **Step 6: Commit**

```bash
git add tests/test_quality_blocks.py .claude/skills/sssf/templates/adws/adw_modules/data_types.py .claude/skills/sssf/templates/adws/adw_modules/quality.py
git commit -m "feat(quality): give a check spec a tier and a working directory"
```

---

## Task 2: Quality blocks become data, and the tiers drive the two entry points

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/quality.py` (the whole "Blocks" section, `run_tests`, `run_quality`, and the banner)
- Test: `tests/test_quality_blocks.py` (append)

**Scene:** today `quality.py` defines four zero-argument functions (`test`, `lint`, `typecheck`, `build`) that each construct a spec and call `_run`. Nothing outside `quality.py` calls them — the ADWs only call `run_tests`, `run_quality` and `as_envelope` (verified with `grep -rn "quality\." adws/adw_*.py`). That makes them safe to replace with a list of specs, which is what a generator can write and a human can read.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_quality_blocks.py`:

```python
def test_placeholder_blocks_are_used_when_nothing_was_generated(monkeypatch):
    """An un-profiled install must still announce that it is fake."""
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: None)
    names = [b.name for b in quality.blocks()]
    assert names == ["test", "lint", "typecheck", "build"]
    assert all("PLACEHOLDER" in " ".join(b.argv) for b in quality.blocks())


def test_generated_blocks_replace_the_placeholders(monkeypatch):
    generated = [QualityCheckSpec(name="test-api", area="backend", operation="build",
                                  argv=["just", "test-api"], tier="fast")]
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: generated)
    assert [b.name for b in quality.blocks()] == ["test-api"]


def test_run_tests_runs_the_fast_tier_only(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="unit", area="backend", operation="build",
                         argv=["a"], tier="fast"),
        QualityCheckSpec(name="integration", area="backend", operation="build",
                         argv=["b"], tier="full"),
    ])
    monkeypatch.setattr(quality, "_run", lambda spec, run: _passing(spec, ran))

    result = quality.run_tests(_fake_run(tmp_path))

    assert ran == ["unit"]
    assert result.passed


def test_run_quality_runs_every_tier(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="unit", area="backend", operation="build",
                         argv=["a"], tier="fast"),
        QualityCheckSpec(name="integration", area="backend", operation="build",
                         argv=["b"], tier="full"),
    ])
    monkeypatch.setattr(quality, "_run", lambda spec, run: _passing(spec, ran))

    quality.run_quality(_fake_run(tmp_path))

    assert ran == ["unit", "integration"]


def test_a_failing_block_is_reported_with_its_output(tmp_path, monkeypatch):
    monkeypatch.setattr(quality, "_import_generated_blocks", lambda: [
        QualityCheckSpec(name="unit", area="backend", operation="build", argv=["a"]),
    ])
    monkeypatch.setattr(quality, "_run", lambda spec, run: _failing(spec))

    result = quality.run_tests(_fake_run(tmp_path))

    assert not result.passed
    assert len(result.failures) == 1
    assert "exited 1" in result.failures[0]
    assert "boom" in result.failures[0]


def test_a_broken_generated_module_is_not_swallowed(monkeypatch):
    """A typo in quality_blocks.py must raise, not silently fall back to fakes."""
    import pytest

    def raise_unrelated():
        raise ModuleNotFoundError("No module named 'nonexistent_dependency'",
                                  name="nonexistent_dependency")

    monkeypatch.setattr(quality, "_import_generated_blocks", raise_unrelated)
    with pytest.raises(ModuleNotFoundError):
        quality.blocks()
```

And add these two helpers near `_fake_run` at the top of the file:

```python
def _passing(spec, ran):
    from adw_modules.data_types import QualityCheckResult
    ran.append(spec.name)
    return QualityCheckResult(name=spec.name, area=spec.area, operation=spec.operation,
                              command=" ".join(spec.argv), returncode=0, passed=True,
                              duration_seconds=0.0, output_artifact="/dev/null")


def _failing(spec):
    from adw_modules.data_types import QualityCheckResult
    return QualityCheckResult(name=spec.name, area=spec.area, operation=spec.operation,
                              command=" ".join(spec.argv), returncode=1, passed=False,
                              duration_seconds=0.0, output_artifact="/dev/null",
                              output_tail="boom")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_quality_blocks.py -v`
Expected: FAIL — `AttributeError: module 'adw_modules.quality' has no attribute '_import_generated_blocks'`.

- [ ] **Step 3: Replace the blocks section**

In `quality.py`, delete `_placeholder`, the four block functions (`test`, `lint`, `typecheck`, `build`), the `run_tests` body and the `run_quality` body, and the `from typing import Callable` import if it becomes unused. Put this in their place (keep `as_envelope` exactly as it is, between `_run` and the new `run_tests`):

```python
# ── Blocks ────────────────────────────────────────────────────────────────────

def _placeholder(name: str) -> QualityCheckSpec:
    """A command that does nothing and admits it."""
    return QualityCheckSpec(
        name=name,
        area="backend",
        operation="build" if name in ("test", "build") else name,
        argv=["echo", f"PLACEHOLDER {name}: no profile generated "
                      f"adws/adw_modules/quality_blocks.py, and nobody wrote the "
                      f"real {name} command by hand"],
        timeout_seconds=600 if name == "test" else 120,
    )


PLACEHOLDER_BLOCKS = [_placeholder(n) for n in ("test", "lint", "typecheck", "build")]


def _import_generated_blocks() -> list[QualityCheckSpec] | None:
    """The generated block list, or None when no profile ever wrote one.

    Only a missing quality_blocks module means "not generated". Any OTHER
    import error — a typo in the generated file, a dependency it needs that is
    not installed — is re-raised. Swallowing it would replace a real command
    with an `echo` that exits 0, which is the exact failure this whole profile
    mechanism exists to remove.
    """
    try:
        from .quality_blocks import BLOCKS
    except ModuleNotFoundError as error:
        if error.name in ("adw_modules.quality_blocks", "quality_blocks"):
            return None
        raise
    return list(BLOCKS)


def blocks() -> list[QualityCheckSpec]:
    """This repo's quality blocks: generated if a profile wrote them, else fakes."""
    generated = _import_generated_blocks()
    return list(generated) if generated is not None else list(PLACEHOLDER_BLOCKS)


def _run_tier(run, tiers: set[str]) -> QualityResult:
    """Run every block in the given tiers and collect ALL failures.

    Ordering contract for the caller: a failing block does NOT fail the phase.
    The runner did its job; the CODE is what failed. Hand this result to the
    builder and let the bounded repair loop decide the run's fate.
    """
    checks = [_run(spec, run) for spec in blocks() if spec.tier in tiers]
    # A failure is the command, its exit code, and what it actually printed —
    # everything a builder needs to repair without opening a log or being told
    # what the error "means" by a parser that guessed.
    failures = [
        f"{check.name}: `{check.command}` exited {check.returncode}\n{check.output_tail}".rstrip()
        for check in checks if not check.passed
    ]
    return QualityResult(
        passed=not failures,
        checks=checks,
        failures=failures,
        artifacts=[check.output_artifact for check in checks],
    )


def run_tests(run) -> QualityResult:
    """The FAST tier — the deterministic verification inside a bounded fix loop.

    This is what replaces a `tester` agent once the commands are written down.
    An agent rediscovering the runner on every run costs a fortune to learn
    what a subprocess already knows; the repair loop is unchanged, because a
    failure still reaches the builder through `as_envelope`.

    Fast, not "tests": a typecheck that takes two seconds belongs in the loop
    that runs on every retry, and a Testcontainers suite that needs Docker up
    does not. Which is which is the block's `tier`.
    """
    return _run_tier(run, {"fast"})


def run_quality(run) -> QualityResult:
    """Every tier — final verification, run once."""
    return _run_tier(run, {"fast", "full"})
```

- [ ] **Step 4: Rewrite the file's banner**

Replace the box-drawing banner at the top of `quality.py` (everything between `╔` and `╝` inclusive) with:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  WHERE THE COMMANDS COME FROM.                                               ║
║                                                                              ║
║  `blocks()` returns adws/adw_modules/quality_blocks.py when it exists — a     ║
║  generated file holding this repo's real commands, written by                ║
║  `install.py --profile <name>` from what it found in the tree. Re-probe       ║
║  after a restructure with `install.py --doctor`.                             ║
║                                                                              ║
║  With no generated file, PLACEHOLDER_BLOCKS are used: every one is an `echo`  ║
║  that exits 0 and says out loud that it is fake. They are placeholders on     ║
║  purpose — a wrong-but-plausible command that silently passes is worse than   ║
║  one that admits it.                                                         ║
║                                                                              ║
║  To write blocks by hand, edit quality_blocks.py — it is plain Python, and    ║
║  a list of QualityCheckSpec. Two rules when you do:                          ║
║    1. argv LIST, never a shell string — no quoting bugs, no shell injection.  ║
║    2. Call binaries by BARE NAME. Blocks inherit the operator's environment   ║
║       (see utils.operator_env) and resolve through utils.resolve_argv, so     ║
║       `npm`, `dotnet`, `just` resolve as they do in their terminal. Never     ║
║       hard-code an absolute path — that bakes your machine into the trace.    ║
║    3. Set `tier="full"` on anything slow or service-dependent, so bounded     ║
║       fix loops do not pay for it on every retry.                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest tests/ -v`
Expected: PASS — 95 passed (85 pre-existing + 10 from this file).

- [ ] **Step 6: Commit**

```bash
git add tests/test_quality_blocks.py .claude/skills/sssf/templates/adws/adw_modules/quality.py
git commit -m "feat(quality): blocks become data, fast tier drives the fix loop"
```

---

## Task 3: The shared profile vocabulary

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/__init__.py`
- Create: `.claude/skills/sssf/templates/profiles/facts.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_profile_facts.py`

- [ ] **Step 1: Put the templates directory on `sys.path` for tests**

In `tests/conftest.py`, below the existing `TEMPLATES_ADWS` block, add:

```python
TEMPLATES = TEMPLATES_ADWS.parent          # .../skills/sssf/templates

if str(TEMPLATES) not in sys.path:
    sys.path.insert(0, str(TEMPLATES))
```

This makes `import profiles.facts` work in tests exactly as it will inside `install.py`, which does the same insert.

- [ ] **Step 2: Write the failing test**

Create `tests/test_profile_facts.py`:

```python
"""ProfileFacts is the typed handoff between detection and generation."""

import pytest
from pydantic import ValidationError

from profiles.facts import (DotnetProject, Frontend, GenerationReport, ProfileFacts,
                            QualityBlock)


def test_a_dotnet_project_must_declare_a_known_role():
    with pytest.raises(ValidationError):
        DotnetProject(path="a/B.csproj", name="B", role="maybe-tests")


def test_facts_default_to_an_empty_repo():
    facts = ProfileFacts(profile="dotnet-svelte", repo_root=".")
    assert facts.solution == ""
    assert facts.projects == []
    assert facts.frontends == []
    assert facts.recipes == []
    assert facts.task_runner == ""
    assert facts.default_branch == "main"
    assert facts.conventions == []


def test_projects_by_role_filters():
    facts = ProfileFacts(
        profile="dotnet-svelte", repo_root=".",
        projects=[
            DotnetProject(path="a/App.csproj", name="App", role="app"),
            DotnetProject(path="a/Unit.csproj", name="Unit", role="unit-tests"),
            DotnetProject(path="a/Int.csproj", name="Int", role="integration-tests"),
        ])
    assert [p.name for p in facts.projects_by_role("unit-tests")] == ["Unit"]
    assert [p.name for p in facts.projects_by_role("integration-tests")] == ["Int"]


def test_a_frontend_knows_which_scripts_it_has():
    frontend = Frontend(directory="apps/web", package_manager="npm",
                        scripts=["check", "test", "build"])
    assert frontend.has("check")
    assert not frontend.has("lint")
    assert frontend.label == "web"


def test_a_frontend_at_the_repo_root_still_has_a_label():
    assert Frontend(directory=".", package_manager="npm").label == "root"


def test_a_generation_report_lists_what_it_could_not_resolve():
    report = GenerationReport(profile="dotnet-svelte",
                              blocks=[QualityBlock(name="test-api", area="backend",
                                                   operation="build",
                                                   argv=["just", "test-api"],
                                                   source="recipe just test-api")],
                              unresolved=["no frontend declares a `test` script"])
    assert report.blocks[0].tier == "fast"
    assert report.unresolved == ["no frontend declares a `test` script"]
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_profile_facts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles'`.

- [ ] **Step 4: Create the package**

Create `.claude/skills/sssf/templates/profiles/__init__.py` containing exactly:

```python
"""Stack profiles. Installer-side only — nothing in here is stamped into a repo."""
```

Create `.claude/skills/sssf/templates/profiles/facts.py`:

```python
"""The typed vocabulary a profile speaks.

Detection fills a ProfileFacts; generation reads one and returns a
GenerationReport. Both are concrete Pydantic types rather than dicts, for the
same reason every agent handoff in this system is: a misspelled key should be
a validation error at the boundary, not a silent empty string four functions
later.

Nothing here knows about any particular repository. Every field is filled from
what a probe found in the tree it was pointed at.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

ProjectRole = Literal["app", "unit-tests", "integration-tests"]


class DotnetProject(BaseModel):
    """One project in the solution, and what it is for."""

    path: str                       # repo-relative, forward slashes
    name: str                       # the .csproj stem
    role: ProjectRole


class Frontend(BaseModel):
    """One JavaScript package: where it is, how to run it, what it can do."""

    directory: str                  # repo-relative, forward slashes; "." for the root
    package_manager: str = "npm"    # npm | pnpm | yarn | bun, from the lockfile
    scripts: list[str] = Field(default_factory=list)   # keys of package.json "scripts"
    env_example: str = ""           # the .env.example that governs it, if one exists
    hooks_server: str = ""          # src/hooks.server.ts, only when it mentions CSP

    def has(self, script: str) -> bool:
        return script in self.scripts

    @property
    def label(self) -> str:
        """A short, stable name for this frontend — used in block names."""
        name = PurePosixPath(self.directory).name
        return name or "root"


class ProfileFacts(BaseModel):
    """Everything a probe learned about one repository."""

    profile: str
    repo_root: str
    solution: str = ""                                  # repo-relative *.sln or *.slnx
    projects: list[DotnetProject] = Field(default_factory=list)
    frontends: list[Frontend] = Field(default_factory=list)
    task_runner: str = ""                               # "just", or "" if none
    recipes: list[str] = Field(default_factory=list)    # recipe names the runner knows
    default_branch: str = "main"
    conventions: list[str] = Field(default_factory=list)  # CLAUDE.md, AGENTS.md, dirs...

    def projects_by_role(self, role: str) -> list[DotnetProject]:
        return [p for p in self.projects if p.role == role]


class QualityBlock(BaseModel):
    """One block the generator decided to emit, plus WHY it chose that command.

    `source` never reaches the generated file — it exists for the install
    report, so "just test-api" and "dotnet test apps/api/X.csproj" are
    distinguishable at a glance from a preference the operator can override.
    """

    name: str
    area: str
    operation: str
    argv: list[str]
    cwd: str = "."
    tier: str = "fast"
    timeout_seconds: int = 120
    source: str = ""


class GenerationReport(BaseModel):
    """What generation wrote, wired, and could not work out."""

    profile: str
    files: list[str] = Field(default_factory=list)      # paths written (empty on a dry run)
    blocks: list[QualityBlock] = Field(default_factory=list)
    gates: list[str] = Field(default_factory=list)
    # Everything the probe expected to find and did not. This is the half of
    # the report that earns `--doctor` its place: a factory that wired three of
    # the five things it wanted must say which two are missing, out loud, at
    # install time — not leave them to be discovered as a green run that
    # checked nothing.
    unresolved: list[str] = Field(default_factory=list)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_profile_facts.py -v`
Expected: PASS — 6 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_profile_facts.py .claude/skills/sssf/templates/profiles/
git commit -m "feat(profiles): the typed vocabulary detection and generation share"
```

---

## Task 4: Detect the solution and classify its projects

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/dotnet_svelte/__init__.py`
- Create: `.claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py`
- Create: `tests/profile_fixtures.py`
- Test: `tests/test_detect_dotnet_svelte.py`

**Scene:** a `.sln` is an INI-ish text file whose project entries look like
`Project("{FAE04EC0-...}") = "Codec.Api", "apps\api\Codec.Api\Codec.Api.csproj", "{GUID}"`.
A `.slnx` is XML with `<Project Path="apps/api/Codec.Api/Codec.Api.csproj" />`. Solution
folders appear in `.sln` too, with a path that is not a `.csproj` — they are filtered out.
Classification then reads each `.csproj`: `Testcontainers` means an integration suite,
any test SDK means a unit suite, neither means an application project.

- [ ] **Step 1: Write the fixture builder**

Create `tests/profile_fixtures.py`:

```python
"""Fixture repositories of the dotnet-svelte shape, built in tmp_path.

Every test that exercises detection builds the tree it needs here rather than
pointing at a real repository. A fixture is the only place in this test suite
allowed to use concrete names like `apps/web` — they are this fake repo's
layout, not the profile's.
"""

from __future__ import annotations

import json
from pathlib import Path

CSPROJ_APP = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup><TargetFramework>net10.0</TargetFramework></PropertyGroup>
</Project>
"""

CSPROJ_UNIT = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
  </ItemGroup>
</Project>
"""

CSPROJ_INTEGRATION = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
    <PackageReference Include="Testcontainers.PostgreSql" Version="3.10.0" />
  </ItemGroup>
</Project>
"""


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def sln(root: Path, name: str, project_paths: list[str], folders: list[str] = ()) -> Path:
    """A minimal but real .sln naming the given projects (repo-relative)."""
    lines = ['Microsoft Visual Studio Solution File, Format Version 12.00']
    for index, project in enumerate(project_paths):
        stem = Path(project).stem
        windows_path = project.replace("/", "\\")
        lines.append(
            f'Project("{{9A19103F-16F7-4668-BE54-9A1E7A4F7556}}") = "{stem}", '
            f'"{windows_path}", "{{0000000{index}-0000-0000-0000-000000000000}}"')
        lines.append("EndProject")
    for index, folder in enumerate(folders):
        lines.append(
            f'Project("{{2150E333-8FDC-42A3-9474-1A3956D46DE8}}") = "{folder}", '
            f'"{folder}", "{{FFFFFFF{index}-0000-0000-0000-000000000000}}"')
        lines.append("EndProject")
    return write(root, name, "\n".join(lines) + "\n")


def frontend(root: Path, directory: str, scripts: dict[str, str],
             lockfile: str = "package-lock.json", sveltekit: bool = True) -> Path:
    package = {"name": Path(directory).name, "scripts": scripts,
               "devDependencies": {"@sveltejs/kit": "^2.20.0"} if sveltekit else {}}
    path = write(root, f"{directory}/package.json", json.dumps(package, indent=2))
    write(root, f"{directory}/{lockfile}", "{}")
    return path


def dotnet_svelte_repo(root: Path, *, integration: bool = True,
                       frontends: list[str] = ("apps/web",),
                       justfile_text: str = "") -> Path:
    """The default fixture: one app, one unit-test project, optional integration."""
    projects = ["apps/api/Api/Api.csproj", "apps/api/Api.Tests/Api.Tests.csproj"]
    write(root, "apps/api/Api/Api.csproj", CSPROJ_APP)
    write(root, "apps/api/Api.Tests/Api.Tests.csproj", CSPROJ_UNIT)
    if integration:
        projects.append("apps/api/Api.IntegrationTests/Api.IntegrationTests.csproj")
        write(root, "apps/api/Api.IntegrationTests/Api.IntegrationTests.csproj",
              CSPROJ_INTEGRATION)
    sln(root, "Fixture.sln", projects)
    for directory in frontends:
        frontend(root, directory, {"check": "svelte-check", "test": "vitest run",
                                   "build": "vite build"})
    if justfile_text:
        write(root, "justfile", justfile_text)
    return root
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_detect_dotnet_svelte.py`:

```python
"""Detection reads a tree and reports facts. It never guesses a layout."""

from pathlib import Path

from profile_fixtures import (CSPROJ_APP, CSPROJ_INTEGRATION, CSPROJ_UNIT,
                              dotnet_svelte_repo, sln, write)
from profiles.dotnet_svelte import detect as det


def test_finds_the_solution_and_classifies_every_project(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = det.detect(tmp_path)

    assert facts.solution == "Fixture.sln"
    roles = {p.name: p.role for p in facts.projects}
    assert roles == {"Api": "app", "Api.Tests": "unit-tests",
                     "Api.IntegrationTests": "integration-tests"}


def test_project_paths_are_repo_relative_with_forward_slashes(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = det.detect(tmp_path)
    assert all("\\" not in p.path for p in facts.projects)
    assert "apps/api/Api/Api.csproj" in [p.path for p in facts.projects]


def test_solution_folders_are_not_projects(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Folders.sln", ["src/App/App.csproj"], folders=["Solution Items"])
    facts = det.detect(tmp_path)
    assert [p.name for p in facts.projects] == ["App"]


def test_an_slnx_solution_is_read_too(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    write(tmp_path, "Modern.slnx",
          '<Solution>\n  <Project Path="src/App/App.csproj" />\n</Solution>\n')
    facts = det.detect(tmp_path)
    assert facts.solution == "Modern.slnx"
    assert [p.name for p in facts.projects] == ["App"]


def test_testcontainers_outranks_xunit(tmp_path):
    """A project with both is an INTEGRATION suite — it needs Docker up."""
    assert det.classify(CSPROJ_INTEGRATION) == "integration-tests"
    assert det.classify(CSPROJ_UNIT) == "unit-tests"
    assert det.classify(CSPROJ_APP) == "app"


def test_a_project_named_in_the_solution_but_missing_on_disk_is_an_app(tmp_path):
    """Never crash on a stale solution entry; the worst case is a wrong role."""
    sln(tmp_path, "Stale.sln", ["gone/Gone.csproj"])
    facts = det.detect(tmp_path)
    assert [(p.name, p.role) for p in facts.projects] == [("Gone", "app")]


def test_a_solution_inside_node_modules_is_ignored(tmp_path):
    write(tmp_path, "node_modules/pkg/Vendor.sln", "Microsoft Visual Studio Solution File")
    facts = det.detect(tmp_path)
    assert facts.solution == ""
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_detect_dotnet_svelte.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.dotnet_svelte'`.

- [ ] **Step 4: Write the package and the solution half of detection**

Create `.claude/skills/sssf/templates/profiles/dotnet_svelte/__init__.py`:

```python
"""The dotnet-svelte profile: ASP.NET Core + EF Core + SvelteKit repositories."""

from .detect import NAME, detect, matches
from .generate import generate

__all__ = ["NAME", "detect", "matches", "generate"]
```

Create `.claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py`:

```python
"""Probe a repository and report what this stack looks like there.

Read-only except for one subprocess: the task runner's summary command. Nothing
in this file names a path from any particular repository — every concrete string
it returns was read out of the tree it was pointed at.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..facts import DotnetProject, Frontend, ProfileFacts

NAME = "dotnet-svelte"

# Directories never worth walking: a vendored tree can contain anything,
# including another repo's solution file and a thousand package.json files.
SKIP_DIRS = {"node_modules", "bin", "obj", ".git", ".svelte-kit", "dist", "build",
             "artifacts", ".venv", "venv", "__pycache__"}

# `Project("{type-guid}") = "Name", "relative\path.csproj", "{project-guid}"`
SLN_PROJECT = re.compile(r'^Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"[^"]*",\s*"([^"]+)"',
                         re.MULTILINE)
SLNX_PROJECT = re.compile(r'<Project\s+[^>]*Path="([^"]+)"')

TEST_SDK_MARKERS = ("xunit", "Microsoft.NET.Test.Sdk", "NUnit", "MSTest")
INTEGRATION_MARKERS = ("Testcontainers",)


def _walk(root: Path):
    """Every file under root, skipping vendored and build-output directories."""
    for path in root.rglob("*"):
        if path.is_file() and not (SKIP_DIRS & set(path.relative_to(root).parts)):
            yield path


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def find_solution(root: Path) -> str:
    """The solution file, shallowest first so a repo-root one always wins."""
    candidates = [p for p in _walk(root) if p.suffix in (".sln", ".slnx")]
    if not candidates:
        return ""
    candidates.sort(key=lambda p: (len(p.relative_to(root).parts), p.name))
    return _relative(root, candidates[0])


def solution_projects(root: Path, solution: str) -> list[str]:
    """Repo-relative, forward-slashed paths of every .csproj the solution names."""
    text = (root / solution).read_text(errors="replace")
    pattern = SLNX_PROJECT if solution.endswith(".slnx") else SLN_PROJECT
    paths = []
    solution_dir = Path(solution).parent
    for raw in pattern.findall(text):
        entry = raw.replace("\\", "/")
        if not entry.lower().endswith(".csproj"):
            continue                       # a solution folder, not a project
        paths.append((solution_dir / entry).as_posix().lstrip("./") or entry)
    return paths


def classify(csproj_text: str) -> str:
    """What kind of project this is, from what it references.

    Integration wins over unit deliberately: a Testcontainers suite needs Docker
    running, which is precisely the thing that must not be inside a bounded fix
    loop, and a project referencing it is that suite whatever else it also uses.
    """
    if any(marker in csproj_text for marker in INTEGRATION_MARKERS):
        return "integration-tests"
    if any(marker in csproj_text for marker in TEST_SDK_MARKERS):
        return "unit-tests"
    return "app"


def dotnet_projects(root: Path, solution: str) -> list[DotnetProject]:
    projects = []
    for relative in solution_projects(root, solution):
        path = root / relative
        # A solution can name a project that is not on disk. Treat it as an app:
        # the worst case is one block too few, and crashing the installer over a
        # stale solution entry would be a far worse trade.
        text = path.read_text(errors="replace") if path.is_file() else ""
        projects.append(DotnetProject(path=relative, name=Path(relative).stem,
                                      role=classify(text)))
    return projects


def detect(root: Path) -> ProfileFacts:
    root = Path(root)
    solution = find_solution(root)
    return ProfileFacts(
        profile=NAME,
        repo_root=str(root),
        solution=solution,
        projects=dotnet_projects(root, solution) if solution else [],
    )


def matches(root: Path) -> bool:
    """Placeholder until Task 5 gives it the frontend half."""
    return bool(find_solution(Path(root)))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_detect_dotnet_svelte.py -v`
Expected: FAIL on import — `generate` does not exist yet. Create a stub `.claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py` containing exactly:

```python
"""Turn ProfileFacts into generated files. Filled in by Task 8."""


def generate(facts, root, write: bool = True):
    raise NotImplementedError("generate() lands in Task 8")
```

Then re-run. Expected: PASS — 7 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/profile_fixtures.py tests/test_detect_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/
git commit -m "feat(profiles): detect the solution and classify its projects"
```

---

## Task 5: Detect every frontend, its package manager, and its scripts

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py`
- Test: `tests/test_detect_dotnet_svelte.py` (append)

**Scene:** a repo of this stack has one frontend or four; the profile must not care. Each is found independently by its own `package.json` declaring `@sveltejs/kit`, and each reports its own package manager (from the nearest lockfile) and its own script names. Nothing assumes `apps/`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_detect_dotnet_svelte.py`:

```python
def test_finds_every_sveltekit_frontend_independently(tmp_path):
    dotnet_svelte_repo(tmp_path, frontends=["apps/web", "apps/admin", "packages/kiosk"])
    facts = det.detect(tmp_path)
    assert sorted(f.directory for f in facts.frontends) == [
        "apps/admin", "apps/web", "packages/kiosk"]
    assert sorted(f.label for f in facts.frontends) == ["admin", "kiosk", "web"]


def test_a_package_json_without_sveltekit_is_not_a_frontend(tmp_path):
    from profile_fixtures import frontend
    dotnet_svelte_repo(tmp_path, frontends=["apps/web"])
    frontend(tmp_path, "tools/scripts", {"build": "tsc"}, sveltekit=False)
    facts = det.detect(tmp_path)
    assert [f.directory for f in facts.frontends] == ["apps/web"]


def test_reports_the_scripts_the_frontend_actually_declares(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"check": "svelte-check", "lint": "eslint ."})
    facts = det.detect(tmp_path)
    assert facts.frontends[0].has("check")
    assert facts.frontends[0].has("lint")
    assert not facts.frontends[0].has("test")


def test_package_manager_comes_from_the_lockfile(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"build": "vite build"}, lockfile="pnpm-lock.yaml")
    assert det.detect(tmp_path).frontends[0].package_manager == "pnpm"


def test_package_manager_is_inherited_from_a_parent_lockfile(tmp_path):
    """A workspace keeps one lockfile at the root; the package below has none."""
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "apps/web", {"build": "vite build"}, lockfile="ignored.txt")
    write(tmp_path, "yarn.lock", "")
    assert det.detect(tmp_path).frontends[0].package_manager == "yarn"


def test_package_manager_defaults_to_npm_with_no_lockfile_anywhere(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"build": "vite build"}, lockfile="notes.txt")
    assert det.detect(tmp_path).frontends[0].package_manager == "npm"


def test_a_malformed_package_json_is_skipped_not_fatal(tmp_path):
    from profile_fixtures import write
    dotnet_svelte_repo(tmp_path, frontends=["apps/web"])
    write(tmp_path, "apps/broken/package.json", "{ this is not json")
    facts = det.detect(tmp_path)
    assert [f.directory for f in facts.frontends] == ["apps/web"]


def test_an_env_example_beside_a_frontend_is_recorded(tmp_path):
    from profile_fixtures import write
    dotnet_svelte_repo(tmp_path, frontends=["apps/web"])
    write(tmp_path, "apps/web/.env.example", "PUBLIC_API_URL=\n")
    assert det.detect(tmp_path).frontends[0].env_example == "apps/web/.env.example"


def test_a_hooks_file_is_recorded_only_when_it_mentions_csp(tmp_path):
    from profile_fixtures import write
    dotnet_svelte_repo(tmp_path, frontends=["apps/web", "apps/admin"])
    write(tmp_path, "apps/web/src/hooks.server.ts",
          "export const handle = ({ event, resolve }) => resolve(event);\n"
          "// content-security-policy is set here\n")
    write(tmp_path, "apps/admin/src/hooks.server.ts",
          "export const handle = ({ event, resolve }) => resolve(event);\n")
    by_dir = {f.directory: f for f in det.detect(tmp_path).frontends}
    assert by_dir["apps/web"].hooks_server == "apps/web/src/hooks.server.ts"
    assert by_dir["apps/admin"].hooks_server == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_detect_dotnet_svelte.py -v`
Expected: FAIL — `facts.frontends` is always `[]`.

- [ ] **Step 3: Implement frontend detection**

In `detect.py`, add these constants below `INTEGRATION_MARKERS`:

```python
SVELTEKIT_MARKER = "@sveltejs/kit"

# Lockfile -> package manager, most specific first. The lockfile is the only
# honest answer: a `packageManager` field in package.json states an intention,
# a lockfile records what was actually installed.
LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
             ("bun.lockb", "bun"), ("bun.lock", "bun"),
             ("package-lock.json", "npm"))

ENV_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template")
HOOKS_RELATIVE = "src/hooks.server.ts"
CSP_MARKERS = ("csp", "content-security-policy")
```

Add these functions above `detect`:

```python
def _package_manager(root: Path, directory: Path) -> str:
    """The lockfile nearest this package, walking up to the repo root."""
    current = directory
    while True:
        for lockfile, manager in LOCKFILES:
            if (current / lockfile).is_file():
                return manager
        if current == root:
            return "npm"
        current = current.parent


def _env_example(directory: Path) -> Path | None:
    for name in ENV_EXAMPLE_NAMES:
        if (directory / name).is_file():
            return directory / name
    return None


def _hooks_with_csp(directory: Path) -> Path | None:
    """The SvelteKit server hook, but only when it actually declares a CSP.

    Opt-in on purpose: the csp gate fires on external origins, and pointing it
    at a repo that has no policy would be noise on every single run.
    """
    hooks = directory / HOOKS_RELATIVE
    if not hooks.is_file():
        return None
    text = hooks.read_text(errors="replace").lower()
    return hooks if any(marker in text for marker in CSP_MARKERS) else None


def frontends(root: Path) -> list[Frontend]:
    """Every package declaring SvelteKit, wherever it lives."""
    found = []
    for manifest in sorted(p for p in _walk(root) if p.name == "package.json"):
        try:
            package = json.loads(manifest.read_text(errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # A broken manifest is the repo's problem, not a reason to abort an
            # install. It is reported as unresolved rather than crashing here.
            continue
        if not isinstance(package, dict):
            continue
        declared = {**(package.get("dependencies") or {}),
                    **(package.get("devDependencies") or {})}
        if SVELTEKIT_MARKER not in declared:
            continue
        directory = manifest.parent
        env_example = _env_example(directory)
        hooks = _hooks_with_csp(directory)
        found.append(Frontend(
            directory=_relative(root, directory) if directory != root else ".",
            package_manager=_package_manager(root, directory),
            scripts=sorted((package.get("scripts") or {}).keys()),
            env_example=_relative(root, env_example) if env_example else "",
            hooks_server=_relative(root, hooks) if hooks else "",
        ))
    return found
```

Add `import json` to the imports at the top of the file, then extend `detect`:

```python
def detect(root: Path) -> ProfileFacts:
    root = Path(root)
    solution = find_solution(root)
    return ProfileFacts(
        profile=NAME,
        repo_root=str(root),
        solution=solution,
        projects=dotnet_projects(root, solution) if solution else [],
        frontends=frontends(root),
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_detect_dotnet_svelte.py -v`
Expected: PASS — 16 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_detect_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py
git commit -m "feat(profiles): detect every frontend, its manager, and its scripts"
```

---

## Task 6: Detect the task runner, the default branch, and the convention files

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py`
- Test: `tests/test_detect_dotnet_svelte.py` (append)

**Scene:** when a repo already has a task runner, its recipes are better commands than anything the generator could compose — they are what the team actually runs, kept working by the team. `just --summary` is authoritative because it resolves imports; parsing the justfile is the offline fallback so detection still works with `just` uninstalled (and so these tests do not depend on a binary being present).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_detect_dotnet_svelte.py`:

```python
JUSTFILE = """set shell := ["bash", "-c"]

api_dir := "apps/api"

default:
    @just --list

# run the fast suite
test-fast: build-sln
    dotnet test

test-api:
    dotnet test {{api_dir}}

check-web dir="apps/web":
    npm --prefix {{dir}} run check
"""


def test_recipes_are_parsed_from_a_justfile_without_just_installed():
    names = det.recipes_from_justfile(JUSTFILE)
    assert "default" in names
    assert "test-fast" in names
    assert "test-api" in names
    assert "check-web" in names
    # assignments and settings are not recipes
    assert "api_dir" not in names
    assert "set shell" not in names


def test_a_comment_is_not_a_recipe():
    assert "# run the fast suite" not in det.recipes_from_justfile(JUSTFILE)


def test_recipe_bodies_are_not_mistaken_for_recipes():
    """Indented lines are the body of the recipe above them."""
    assert "npm --prefix {{dir}} run check" not in det.recipes_from_justfile(JUSTFILE)


def test_task_runner_is_empty_with_no_justfile(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = det.detect(tmp_path)
    assert facts.task_runner == ""
    assert facts.recipes == []


def test_task_runner_is_just_when_a_justfile_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(det, "_summary", lambda root: None)   # pretend just is absent
    dotnet_svelte_repo(tmp_path, justfile_text=JUSTFILE)
    facts = det.detect(tmp_path)
    assert facts.task_runner == "just"
    assert "test-api" in facts.recipes


def test_the_summary_command_wins_over_the_parser(tmp_path, monkeypatch):
    """`just --summary` resolves imports the parser cannot see."""
    monkeypatch.setattr(det, "_summary", lambda root: ["imported-recipe"])
    dotnet_svelte_repo(tmp_path, justfile_text=JUSTFILE)
    assert det.detect(tmp_path).recipes == ["imported-recipe"]


def test_a_capitalised_justfile_counts(tmp_path, monkeypatch):
    from profile_fixtures import write
    monkeypatch.setattr(det, "_summary", lambda root: None)
    dotnet_svelte_repo(tmp_path)
    write(tmp_path, "Justfile", JUSTFILE)
    assert det.detect(tmp_path).task_runner == "just"


def test_convention_files_and_directories_are_recorded(tmp_path):
    from profile_fixtures import write
    dotnet_svelte_repo(tmp_path)
    write(tmp_path, "CLAUDE.md", "# house rules\n")
    write(tmp_path, "AGENTS.md", "# agents\n")
    write(tmp_path, ".github/instructions/csharp.instructions.md", "# c#\n")
    write(tmp_path, ".github/instructions/svelte.instructions.md", "# svelte\n")

    conventions = det.detect(tmp_path).conventions

    assert "CLAUDE.md" in conventions
    assert "AGENTS.md" in conventions
    # A directory of instructions is ONE entry, not one per file — fifteen
    # bullets would drown the prompt overlay they end up in.
    assert ".github/instructions/" in conventions
    assert ".github/instructions/csharp.instructions.md" not in conventions


def test_no_convention_files_is_an_empty_list_not_an_error(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert det.detect(tmp_path).conventions == []


def test_default_branch_falls_back_to_main_outside_a_git_repo(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert det.detect(tmp_path).default_branch == "main"


def test_matches_requires_both_halves_of_the_stack(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    # A solution with no SvelteKit anywhere is not this stack.
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    assert not det.matches(tmp_path)
    frontend(tmp_path, "web", {"build": "vite build"})
    assert det.matches(tmp_path)


def test_a_sveltekit_repo_with_no_solution_does_not_match(tmp_path):
    from profile_fixtures import frontend
    frontend(tmp_path, "web", {"build": "vite build"})
    assert not det.matches(tmp_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_detect_dotnet_svelte.py -v`
Expected: FAIL — `det.recipes_from_justfile` does not exist, and `matches` still returns True for a solution-only repo.

- [ ] **Step 3: Implement the rest of detection**

Add to the imports at the top of `detect.py`:

```python
import shutil
import subprocess
```

Add these constants below `CSP_MARKERS`:

```python
JUSTFILE_NAMES = ("justfile", "Justfile", ".justfile")

# A recipe header starts at column 0, is a name, may take parameters and
# dependencies, and ends in a colon that is not `:=` (an assignment).
JUST_RECIPE = re.compile(r"^(?!\s)(?:@)?([A-Za-z_][A-Za-z0-9_-]*)[^:=\n]*:(?!=)",
                         re.MULTILINE)

CONVENTION_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules",
                    ".github/copilot-instructions.md", "CONTRIBUTING.md")
CONVENTION_DIRS = (".github/instructions", ".cursor/rules")
```

Add these functions above `detect`:

```python
def recipes_from_justfile(text: str) -> list[str]:
    """Recipe names parsed straight out of a justfile.

    The offline fallback for when `just` is not installed. It cannot see
    imported files, which is exactly why `just --summary` is preferred when the
    binary is there.
    """
    return sorted(set(JUST_RECIPE.findall(text)))


def _summary(root: Path) -> list[str] | None:
    """`just --summary`, or None when just is absent or refuses to run.

    shutil.which is what makes this work on Windows, where `just` may be a
    shim with an extension PATHEXT knows about and bare-name argv does not.
    """
    binary = shutil.which("just")
    if not binary:
        return None
    try:
        completed = subprocess.run([binary, "--summary"], cwd=root, text=True,
                                   capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return sorted(set(completed.stdout.split()))


def task_runner(root: Path) -> tuple[str, list[str]]:
    """The runner this repo uses, and the recipe names it knows."""
    justfile = next((root / name for name in JUSTFILE_NAMES
                     if (root / name).is_file()), None)
    if justfile is None:
        return "", []
    summary = _summary(root)
    if summary is not None:
        return "just", summary
    return "just", recipes_from_justfile(justfile.read_text(errors="replace"))


def default_branch(root: Path) -> str:
    """What this repo merges into, asked of git rather than assumed."""
    for args in (["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                 ["rev-parse", "--abbrev-ref", "HEAD"]):
        try:
            completed = subprocess.run(["git", *args], cwd=root, text=True,
                                       capture_output=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            return "main"
        name = completed.stdout.strip()
        if completed.returncode == 0 and name and name != "HEAD":
            return name.split("/")[-1]
    return "main"


def conventions(root: Path) -> list[str]:
    """The standards files this repo already keeps, as paths to be READ.

    Recorded, never copied. Restating a repo's rules inside a prompt duplicates
    them and then drifts from them; pointing an agent at the live file cannot.
    """
    found = [name for name in CONVENTION_FILES if (root / name).is_file()]
    for directory in CONVENTION_DIRS:
        path = root / directory
        if path.is_dir() and any(path.iterdir()):
            found.append(directory + "/")
    return found
```

Replace `detect` and `matches` with their final forms:

```python
def detect(root: Path) -> ProfileFacts:
    root = Path(root)
    solution = find_solution(root)
    runner, recipes = task_runner(root)
    return ProfileFacts(
        profile=NAME,
        repo_root=str(root),
        solution=solution,
        projects=dotnet_projects(root, solution) if solution else [],
        frontends=frontends(root),
        task_runner=runner,
        recipes=recipes,
        default_branch=default_branch(root),
        conventions=conventions(root),
    )


def matches(root: Path) -> bool:
    """Both halves of the stack, or it is not this stack.

    A solution alone is a .NET repo; a SvelteKit package alone is a Node repo.
    Only the pair implies the EF-migration and PUBLIC_-variable conventions this
    profile's gates and blocks are built around.
    """
    root = Path(root)
    return bool(find_solution(root)) and bool(frontends(root))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_detect_dotnet_svelte.py -v`
Expected: PASS — 28 passed.

- [ ] **Step 5: Verify the design rule holds for the whole detection module**

Run: `grep -nE "codec|Codec|apps/web|apps/admin|test-api|Codec\.sln" .claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py`
Expected: no output. If anything prints, a repository-specific literal leaked into profile source and must be replaced with a detected value.

- [ ] **Step 6: Commit**

```bash
git add tests/test_detect_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/detect.py
git commit -m "feat(profiles): detect task runner recipes, default branch, conventions"
```

---

## Task 7: `profile.yaml` and the registry

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/dotnet_svelte/profile.yaml`
- Create: `.claude/skills/sssf/templates/profiles/registry.py`
- Test: `tests/test_profile_registry.py`

**Scene:** the registry is what `install.py` talks to. It answers two questions: "give me the profile called X" and "which profiles match this repo?". Auto-detection must refuse to choose when two profiles both match — silently picking one would wire a repo to the wrong stack, and the operator can always pass `--profile`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_profile_registry.py`:

```python
"""The registry: profile lookup by name, and auto-detection across profiles."""

import pytest
from profile_fixtures import dotnet_svelte_repo

from profiles import registry


def test_the_dotnet_svelte_profile_is_registered():
    assert "dotnet-svelte" in registry.names()


def test_get_returns_a_module_with_the_profile_interface():
    profile = registry.get("dotnet-svelte")
    for attribute in registry.PROFILE_INTERFACE:
        assert hasattr(profile, attribute), attribute


def test_an_unknown_profile_name_says_what_is_available():
    with pytest.raises(SystemExit) as error:
        registry.get("cobol-jquery")
    assert "cobol-jquery" in str(error.value)
    assert "dotnet-svelte" in str(error.value)


def test_detect_all_finds_the_matching_profile(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert registry.detect_all(tmp_path) == ["dotnet-svelte"]


def test_detect_all_is_empty_for_an_unrecognised_repo(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    assert registry.detect_all(tmp_path) == []


def test_select_returns_none_when_nothing_matches(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    assert registry.select(tmp_path) is None


def test_select_returns_the_single_match(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert registry.select(tmp_path).NAME == "dotnet-svelte"


def test_select_refuses_to_guess_between_two_matches(tmp_path, monkeypatch):
    dotnet_svelte_repo(tmp_path)
    monkeypatch.setattr(registry, "detect_all", lambda root: ["dotnet-svelte", "other"])
    with pytest.raises(SystemExit) as error:
        registry.select(tmp_path)
    assert "--profile" in str(error.value)


def test_the_profile_yaml_is_loadable_and_names_itself():
    config = registry.config("dotnet-svelte")
    assert config["name"] == "dotnet-svelte"
    assert config["env_prefixes"]
    assert "dotnet_unit_tests" in config["recipes"]


def test_profile_yaml_declares_no_repository_specific_paths():
    """The design rule, enforced on the one file most likely to break it."""
    from pathlib import Path
    text = Path(registry.config_path("dotnet-svelte")).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/web", "apps/admin"):
        assert forbidden not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_profile_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.registry'`.

- [ ] **Step 3: Write `profile.yaml`**

Create `.claude/skills/sssf/templates/profiles/dotnet_svelte/profile.yaml`:

```yaml
# The declarative half of the dotnet-svelte profile.
#
# Every value here is a STACK fact or a CONVENTION name. None of it is a path,
# because a path belongs to one repository and this file belongs to a stack.
name: dotnet-svelte
description: ASP.NET Core + EF Core + SvelteKit repositories.

# What has to be true for this profile to claim a repo. Both markers are
# implemented in detect.matches(); this block documents them.
detect:
  all_of:
    - solution        # a *.sln or *.slnx outside vendored directories
    - sveltekit       # a package.json declaring @sveltejs/kit

# Candidate task-runner recipe names per block role, best first. A recipe the
# team already maintains beats a command the generator composed, so the first
# name that exists in the runner's summary wins and the raw argv is the
# fallback. `{name}` is substituted with a frontend's directory name — a
# DISCOVERED value, not a hard-coded one.
recipes:
  dotnet_unit_tests: [test-unit, test-api, test-dotnet, test-backend]
  dotnet_integration_tests: [test-api-integration, test-integration, test-e2e-api]
  solution_build: [build-sln, build-dotnet, build-api]
  frontend_check: ["check-{name}", check-frontend]
  frontend_test: ["test-{name}", test-frontend]
  frontend_build: ["build-{name}", build-frontend]
  frontend_lint: ["lint-{name}", lint-frontend]

# Public environment variables, by the conventions of the two build tools this
# stack uses: SvelteKit exposes PUBLIC_*, Vite exposes VITE_*.
env_prefixes: [PUBLIC_, VITE_]

# Which gates this profile wires, and what each one needs before it is wired.
gates:
  ef_migration_triad: always
  env_example_sync: when a frontend has an env example file
  sveltekit_csp: when a frontend's src/hooks.server.ts declares a CSP
```

- [ ] **Step 4: Write the registry**

Create `.claude/skills/sssf/templates/profiles/registry.py`:

```python
"""Profile lookup and auto-detection.

The one module install.py imports. Adding a profile means adding a package and
one entry in PROFILES — no core module changes, which is the whole point of
having a mechanism rather than a special case.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import yaml

from . import dotnet_svelte

# Directory name -> module. The KEY of the public name lives in each module's
# NAME, so a hyphenated profile name and an importable package name can differ
# (`dotnet-svelte` is not a legal Python identifier).
PROFILES: list[ModuleType] = [dotnet_svelte]

# What install.py may call on a profile. Checked at import so a half-written
# profile fails here, with the missing name, rather than at the moment the
# installer tries to use it.
PROFILE_INTERFACE = ("NAME", "matches", "detect", "generate")

for _profile in PROFILES:
    _missing = [a for a in PROFILE_INTERFACE if not hasattr(_profile, a)]
    if _missing:
        raise ImportError(f"profile {_profile.__name__} is missing "
                          f"{', '.join(_missing)} — see PROFILE_INTERFACE")


def names() -> list[str]:
    return sorted(p.NAME for p in PROFILES)


def get(name: str) -> ModuleType:
    for profile in PROFILES:
        if profile.NAME == name:
            return profile
    raise SystemExit(f"unknown profile {name!r} — available: {', '.join(names())}")


def config_path(name: str) -> Path:
    return Path(get(name).__file__).parent / "profile.yaml"


def config(name: str) -> dict:
    return yaml.safe_load(config_path(name).read_text()) or {}


def detect_all(root: Path) -> list[str]:
    """Every profile that claims this repo."""
    return sorted(p.NAME for p in PROFILES if p.matches(Path(root)))


def select(root: Path) -> ModuleType | None:
    """The profile to apply, or None when none matches.

    Refuses to choose between two matches. Wiring a repo to the wrong stack
    produces a factory whose checks all pass because none of them run anything
    real — the exact failure this mechanism exists to prevent — so ambiguity
    stops the install and asks.
    """
    matched = detect_all(root)
    if not matched:
        return None
    if len(matched) > 1:
        raise SystemExit(
            f"{len(matched)} profiles match this repo: {', '.join(matched)}. "
            f"Pick one with --profile <name>, or skip profiles with --no-profile.")
    return get(matched[0])
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_profile_registry.py -v`
Expected: PASS — 10 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/test_profile_registry.py .claude/skills/sssf/templates/profiles/registry.py .claude/skills/sssf/templates/profiles/dotnet_svelte/profile.yaml
git commit -m "feat(profiles): profile.yaml and the registry install.py talks to"
```

---

## Task 8: Generate `quality_blocks.py`

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py` (replacing the Task 4 stub)
- Test: `tests/test_generate_dotnet_svelte.py`

**Scene:** this is the task that closes the failure the README names first — *"the test phase reports green on a fresh install."* Preference order per block is: a task-runner recipe the team already maintains, else a raw argv composed from what was detected. Integration suites are tagged `full` because they need Docker up; everything else is `fast`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_generate_dotnet_svelte.py`:

```python
"""Generation turns facts into this repo's real commands."""

from pathlib import Path

from profile_fixtures import dotnet_svelte_repo
from profiles.dotnet_svelte import detect as det
from profiles.dotnet_svelte import generate as gen
from profiles import registry

CONFIG = registry.config("dotnet-svelte")


def _facts(tmp_path, **kwargs):
    dotnet_svelte_repo(tmp_path, **kwargs)
    return det.detect(tmp_path)


def _blocks(facts):
    return {b.name: b for b in gen.quality_blocks(facts, CONFIG)[0]}


def test_a_unit_test_project_becomes_a_fast_dotnet_test_block(tmp_path):
    blocks = _blocks(_facts(tmp_path, integration=False))
    block = blocks["test-Api.Tests"]
    assert block.argv == ["dotnet", "test", "apps/api/Api.Tests/Api.Tests.csproj"]
    assert block.tier == "fast"
    assert block.area == "backend"


def test_an_integration_project_is_tagged_full(tmp_path):
    blocks = _blocks(_facts(tmp_path, integration=True))
    assert blocks["test-Api.IntegrationTests"].tier == "full"


def test_the_solution_build_is_emitted(tmp_path):
    blocks = _blocks(_facts(tmp_path))
    assert blocks["build-sln"].argv == ["dotnet", "build", "Fixture.sln"]


def test_each_frontend_gets_its_own_blocks_in_its_own_directory(tmp_path):
    blocks = _blocks(_facts(tmp_path, frontends=["apps/web", "apps/admin"]))
    assert blocks["check-web"].argv == ["npm", "run", "check"]
    assert blocks["check-web"].cwd == "apps/web"
    assert blocks["check-web"].area == "frontend"
    assert blocks["check-web"].operation == "typecheck"
    assert blocks["check-admin"].cwd == "apps/admin"
    assert blocks["test-web"].argv == ["npm", "run", "test"]
    assert blocks["build-web"].argv == ["npm", "run", "build"]


def test_a_frontend_only_gets_blocks_for_scripts_it_declares(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"check": "svelte-check"})
    blocks = _blocks(det.detect(tmp_path))
    assert "check-web" in blocks
    assert "test-web" not in blocks
    assert "build-web" not in blocks


def test_the_frontend_package_manager_is_used(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"build": "vite build"}, lockfile="pnpm-lock.yaml")
    assert _blocks(det.detect(tmp_path))["build-web"].argv == ["pnpm", "run", "build"]


def test_a_task_runner_recipe_beats_a_raw_command(tmp_path, monkeypatch):
    monkeypatch.setattr(det, "_summary", lambda root: None)
    facts = _facts(tmp_path, justfile_text="test-unit:\n    dotnet test\n"
                                           "check-web:\n    npm run check\n")
    blocks = _blocks(facts)
    assert blocks["test-unit"].argv == ["just", "test-unit"]
    assert "recipe" in blocks["test-unit"].source
    # ...and the per-frontend recipe is matched by the frontend's own name
    assert blocks["check-web"].argv == ["just", "check-web"]
    assert blocks["check-web"].cwd == "."


def test_a_recipe_that_does_not_exist_falls_back_to_the_raw_command(tmp_path, monkeypatch):
    monkeypatch.setattr(det, "_summary", lambda root: None)
    facts = _facts(tmp_path, justfile_text="deploy:\n    echo deploying\n")
    assert _blocks(facts)["test-Api.Tests"].argv[0] == "dotnet"


def test_colliding_frontend_names_are_disambiguated_by_path(tmp_path):
    blocks = _blocks(_facts(tmp_path, frontends=["apps/web", "packages/web"]))
    assert "check-apps-web" in blocks
    assert "check-packages-web" in blocks


def test_block_names_are_unique(tmp_path):
    facts = _facts(tmp_path, frontends=["apps/web", "apps/admin"])
    names = [b.name for b in gen.quality_blocks(facts, CONFIG)[0]]
    assert len(names) == len(set(names))


def test_a_repo_with_no_test_project_and_no_recipe_reports_it_unresolved(tmp_path):
    from profile_fixtures import frontend, sln, write, CSPROJ_APP
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"build": "vite build"})
    _, unresolved = gen.quality_blocks(det.detect(tmp_path), CONFIG)
    assert any("unit" in note for note in unresolved)


def test_the_generated_module_is_valid_python_that_yields_specs(tmp_path):
    facts = _facts(tmp_path)
    report = gen.generate(facts, tmp_path)

    generated = tmp_path / "adws" / "adw_modules" / "quality_blocks.py"
    assert str(generated) in [str(Path(f)) for f in report.files]
    text = generated.read_text()
    assert "GENERATED" in text
    assert "from .data_types import QualityCheckSpec" in text

    # It parses, and the specs it builds are real QualityCheckSpec objects.
    import ast
    ast.parse(text)
    from adw_modules.data_types import QualityCheckSpec
    namespace = {"QualityCheckSpec": QualityCheckSpec}
    body = text.split("from .data_types import QualityCheckSpec", 1)[1]
    exec(body, namespace)
    assert all(isinstance(spec, QualityCheckSpec) for spec in namespace["BLOCKS"])
    assert {s.tier for s in namespace["BLOCKS"]} == {"fast", "full"}


def test_the_header_records_what_was_detected(tmp_path):
    gen.generate(_facts(tmp_path), tmp_path)
    text = (tmp_path / "adws" / "adw_modules" / "quality_blocks.py").read_text()
    assert "Fixture.sln" in text
    assert "apps/web" in text


def test_a_dry_run_writes_nothing_but_still_reports(tmp_path):
    facts = _facts(tmp_path)
    report = gen.generate(facts, tmp_path, write=False)
    assert report.files == []
    assert report.blocks
    assert not (tmp_path / "adws" / "adw_modules" / "quality_blocks.py").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_generate_dotnet_svelte.py -v`
Expected: FAIL — `module 'profiles.dotnet_svelte.generate' has no attribute 'quality_blocks'`.

- [ ] **Step 3: Write the generator**

Replace the whole contents of `.claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py` with:

```python
"""Turn ProfileFacts into the files a stamped factory actually runs.

The generator's one job is to replace guesses with facts. Everything it emits
is plain, readable, editable Python or Markdown — a file an operator can open
and correct is worth more than a clever indirection they cannot.

Preference order for every command: a task-runner recipe the team already
maintains, else a raw argv composed from what detection found. The recipe wins
because it is the command the humans run, kept working by the humans.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..facts import GenerationReport, ProfileFacts, QualityBlock

BLOCKS_RELATIVE = "adws/adw_modules/quality_blocks.py"

# Which package.json script drives which block, and what kind of check it is.
# (script name, recipe role, operation, block prefix)
FRONTEND_SCRIPTS = (
    ("check", "frontend_check", "typecheck", "check"),
    ("lint", "frontend_lint", "lint", "lint"),
    ("test", "frontend_test", "build", "test"),
    ("build", "frontend_build", "build", "build"),
)

BLOCKS_HEADER = '''"""GENERATED — do not expect edits here to survive a re-install.

Written by `install.py --profile {profile}` at {stamp}.

What was detected in this repository:
{summary}

This file is DATA: the list of commands this repo actually uses. It is plain
Python, so correcting a wrong command is opening it and typing the right one.
Re-probe after a restructure with `install.py --doctor`, which reports drift
without writing, then re-install with --profile to rewrite this file.

`tier="full"` means slow or service-dependent — a suite that needs Docker up.
Full blocks run in run_quality() only, never inside a bounded fix loop.
"""

from .data_types import QualityCheckSpec

BLOCKS = [
{entries}]
'''


def _labels(facts: ProfileFacts) -> dict[str, str]:
    """A short, unique name per frontend, for use in block names.

    `apps/web` is `web` until a repo also has `packages/web`, at which point
    both become their full path. Uniqueness matters: two blocks with one name
    produce two trace rows nobody can tell apart.
    """
    plain = {f.directory: f.label for f in facts.frontends}
    counts = Counter(plain.values())
    return {directory: (label if counts[label] == 1
                        else directory.replace("/", "-").strip("-") or "root")
            for directory, label in plain.items()}


def _recipe(facts: ProfileFacts, config: dict, role: str,
            name: str = "") -> tuple[list[str], str]:
    """The first candidate recipe for this role that the runner actually knows."""
    if not facts.task_runner:
        return [], ""
    for candidate in (config.get("recipes") or {}).get(role, []):
        recipe = candidate.replace("{name}", name)
        if recipe in facts.recipes:
            return [facts.task_runner, recipe], f"recipe {facts.task_runner} {recipe}"
    return [], ""


def quality_blocks(facts: ProfileFacts,
                   config: dict) -> tuple[list[QualityBlock], list[str]]:
    """Every block this repo should run, and everything that could not be wired."""
    blocks: list[QualityBlock] = []
    unresolved: list[str] = []

    # ── .NET ──────────────────────────────────────────────────────────────
    for role, block_role, block_name, tier, timeout in (
            ("unit-tests", "dotnet_unit_tests", "test-unit", "fast", 900),
            ("integration-tests", "dotnet_integration_tests", "test-integration",
             "full", 1800)):
        argv, source = _recipe(facts, config, block_role)
        projects = facts.projects_by_role(role)
        if argv:
            # One recipe covers every project of this role: a team that wrote
            # `test-unit` meant all of them, and running it once per project
            # would run the same suite N times.
            blocks.append(QualityBlock(name=block_name, area="backend",
                                       operation="build", argv=argv, tier=tier,
                                       timeout_seconds=timeout, source=source))
        elif projects:
            for project in projects:
                blocks.append(QualityBlock(
                    name=f"test-{project.name}", area="backend", operation="build",
                    argv=["dotnet", "test", project.path], tier=tier,
                    timeout_seconds=timeout, source=f"project role {role}"))
        else:
            unresolved.append(
                f"no {role} project in the solution and no task-runner recipe for "
                f"{block_role} — nothing verifies this tier")

    if facts.solution:
        argv, source = _recipe(facts, config, "solution_build")
        blocks.append(QualityBlock(
            name="build-sln", area="backend", operation="build",
            argv=argv or ["dotnet", "build", facts.solution],
            tier="fast", timeout_seconds=900,
            source=source or f"solution {facts.solution}"))
    else:
        unresolved.append("no .sln or .slnx found — no backend build block")

    # ── Frontends ─────────────────────────────────────────────────────────
    labels = _labels(facts)
    for frontend in facts.frontends:
        label = labels[frontend.directory]
        emitted = 0
        for script, role, operation, prefix in FRONTEND_SCRIPTS:
            if not frontend.has(script):
                continue
            argv, source = _recipe(facts, config, role, name=frontend.label)
            blocks.append(QualityBlock(
                name=f"{prefix}-{label}", area="frontend", operation=operation,
                argv=argv or [frontend.package_manager, "run", script],
                # A recipe runs from the repo root, because that is where the
                # task runner resolves its own paths from. A raw package-manager
                # command runs inside the package it belongs to.
                cwd="." if argv else frontend.directory,
                tier="fast", timeout_seconds=600,
                source=source or f"{frontend.package_manager} script {script!r}"))
            emitted += 1
        if not emitted:
            unresolved.append(
                f"frontend {frontend.directory} declares none of "
                f"{', '.join(s for s, *_ in FRONTEND_SCRIPTS)} — nothing verifies it")

    if not facts.frontends:
        unresolved.append("no package.json declares @sveltejs/kit — no frontend blocks")
    return blocks, unresolved


def _summary(facts: ProfileFacts) -> str:
    """The detection summary that rides in the generated file's header."""
    lines = [f"  solution: {facts.solution or '(none)'}"]
    for role in ("app", "unit-tests", "integration-tests"):
        named = [p.path for p in facts.projects_by_role(role)]
        if named:
            lines.append(f"  {role}: {', '.join(named)}")
    for frontend in facts.frontends:
        lines.append(f"  frontend: {frontend.directory} "
                     f"({frontend.package_manager}; scripts: "
                     f"{', '.join(frontend.scripts) or 'none'})")
    lines.append(f"  task runner: {facts.task_runner or '(none)'}")
    lines.append(f"  default branch: {facts.default_branch}")
    return "\n".join(lines)


def _entry(block: QualityBlock) -> str:
    return ("    QualityCheckSpec(\n"
            f"        name={block.name!r}, area={block.area!r}, "
            f"operation={block.operation!r},\n"
            f"        argv={block.argv!r},\n"
            f"        cwd={block.cwd!r}, tier={block.tier!r}, "
            f"timeout_seconds={block.timeout_seconds},\n"
            f"    ),  # {block.source}\n")


def render_blocks(facts: ProfileFacts, blocks: list[QualityBlock]) -> str:
    return BLOCKS_HEADER.format(
        profile=facts.profile,
        stamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        summary=_summary(facts),
        entries="".join(_entry(b) for b in blocks))


def _write(root: Path, relative: str, text: str, written: list[str]) -> None:
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    written.append(str(path))


def generate(facts: ProfileFacts, root, write: bool = True) -> GenerationReport:
    """Facts in, files out. `write=False` is the --doctor dry run."""
    config_blocks, unresolved = quality_blocks(facts, _config())
    written: list[str] = []
    if write:
        _write(root, BLOCKS_RELATIVE, render_blocks(facts, config_blocks), written)
    return GenerationReport(profile=facts.profile, files=written,
                            blocks=config_blocks, unresolved=unresolved)


def _config() -> dict:
    import yaml
    return yaml.safe_load((Path(__file__).parent / "profile.yaml").read_text()) or {}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_generate_dotnet_svelte.py -v`
Expected: PASS — 14 passed.

- [ ] **Step 5: Check the design rule again**

Run: `grep -nE "codec|Codec|apps/web|apps/admin|test-api\b" .claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add tests/test_generate_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py
git commit -m "feat(profiles): generate quality_blocks.py from detected facts"
```

---

## Task 9: One glob implementation, and the config-driven `doc_policy` gate

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/utils.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/permissions.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/data_types.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/gates.py`
- Modify: `.claude/skills/sssf/templates/sssf.config.yaml`
- Test: `tests/test_gates_doc_policy.py`

**Scene:** `permissions.py` already owns a careful glob translator — `*` deliberately stops at `/` so `adws/adw_*.py` cannot widen into `adws/adw_data/**/*.py`. `doc_policy` needs exactly those semantics on exactly the same kind of path, so the translator moves to `utils` rather than being written twice. One latent bug comes with it: `**/*.md` currently compiles to `.*/[^/]*\.md`, which requires at least one directory and so does not match `README.md` at the repo root. The documenter's `writes:` list papers over that by also listing `*.md`; `doc_policy` rules written by an operator will not.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gates_doc_policy.py`:

```python
"""doc_policy: a change here requires a doc there, declared in YAML."""

from types import SimpleNamespace

from adw_modules import gates
from adw_modules.data_types import BuildOutput, DocPolicyRule, SSSFConfig
from adw_modules.utils import path_matches


def _run(tmp_path, rules):
    cfg = SSSFConfig(doc_policy=rules)
    return SimpleNamespace(repo_root=str(tmp_path), cfg=cfg)


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


# ── the shared glob, now in utils ────────────────────────────────────────────

def test_a_star_does_not_cross_a_directory_separator():
    assert path_matches("adws/adw_plan.py", "adws/adw_*.py")
    assert not path_matches("adws/adw_data/x/adw_y.py", "adws/adw_*.py")


def test_double_star_slash_matches_zero_directories():
    assert path_matches("README.md", "**/*.md")
    assert path_matches("docs/a/b.md", "**/*.md")


def test_a_trailing_slash_is_a_directory_prefix():
    assert path_matches("docs/deep/file.md", "docs/")
    assert not path_matches("documents/file.md", "docs/")


def test_windows_separators_are_normalised():
    assert path_matches("docs\\a.md", "docs/*.md")


# ── the gate ─────────────────────────────────────────────────────────────────

def test_no_rules_means_no_checks(tmp_path):
    report = gates.doc_policy(_envelope(["src/a.cs"]), _run(tmp_path, []))
    assert report.passed
    assert report.checks == []


def test_a_rule_that_does_not_trigger_records_nothing(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**/Auth*.cs", require=["docs/AUTH.md"])]
    report = gates.doc_policy(_envelope(["apps/web/src/page.svelte"]),
                              _run(tmp_path, rules))
    assert report.passed
    assert report.checks == []


def test_a_triggered_rule_demands_its_document(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**/Auth*.cs", require=["docs/AUTH.md"])]
    report = gates.doc_policy(_envelope(["apps/api/Identity/AuthService.cs"]),
                              _run(tmp_path, rules))
    assert not report.passed
    assert "docs/AUTH.md" in report.violations[0]
    assert "AuthService.cs" in report.violations[0]


def test_a_triggered_rule_passes_when_the_document_is_in_the_change(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**/Auth*.cs", require=["docs/AUTH.md"])]
    report = gates.doc_policy(
        _envelope(["apps/api/Identity/AuthService.cs", "docs/AUTH.md"]),
        _run(tmp_path, rules))
    assert report.passed
    assert len(report.checks) == 1


def test_every_required_document_is_checked_separately(tmp_path):
    rules = [DocPolicyRule(when="apps/web/src/**",
                           require=["docs/ARCHITECTURE.md", "docs/FEATURES.md"])]
    report = gates.doc_policy(
        _envelope(["apps/web/src/routes/+page.svelte", "docs/FEATURES.md"]),
        _run(tmp_path, rules))
    assert len(report.checks) == 2
    assert len(report.violations) == 1
    assert "ARCHITECTURE" in report.violations[0]


def test_a_requirement_may_itself_be_a_glob(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**", require=["docs/*.md"])]
    report = gates.doc_policy(
        _envelope(["apps/api/Program.cs", "docs/anything.md"]),
        _run(tmp_path, rules))
    assert report.passed


def test_absolute_changed_file_paths_are_made_repo_relative(tmp_path):
    """Agents report whatever shape they like; the rule is written repo-relative."""
    rules = [DocPolicyRule(when="apps/api/**", require=["docs/AUTH.md"])]
    absolute = str(tmp_path / "apps" / "api" / "Program.cs")
    report = gates.doc_policy(_envelope([absolute]), _run(tmp_path, rules))
    assert not report.passed


def test_a_dot_slash_prefix_is_stripped(tmp_path):
    rules = [DocPolicyRule(when="apps/api/**", require=["docs/AUTH.md"])]
    report = gates.doc_policy(_envelope(["./apps/api/Program.cs"]),
                              _run(tmp_path, rules))
    assert not report.passed


def test_the_config_accepts_a_doc_policy_block(tmp_path):
    import yaml
    from adw_modules import agents
    path = tmp_path / "sssf.config.yaml"
    path.write_text(yaml.safe_dump({
        "defaults": {"coding_agent": "pi"},
        "doc_policy": [{"when": "apps/api/**", "require": ["docs/AUTH.md"]}],
        "agents": [],
    }))
    cfg = agents.load_config(str(path))
    assert cfg.doc_policy[0].when == "apps/api/**"
    assert cfg.doc_policy[0].require == ["docs/AUTH.md"]


def test_doc_policy_defaults_to_empty():
    assert SSSFConfig().doc_policy == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gates_doc_policy.py -v`
Expected: FAIL — `cannot import name 'path_matches' from 'adw_modules.utils'`.

- [ ] **Step 3: Move the glob into `utils`**

Add to `.claude/skills/sssf/templates/adws/adw_modules/utils.py` (with `import re` and `from functools import lru_cache` at the top if not already present):

```python
@lru_cache(maxsize=512)
def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a path glob, with `*` stopping at a path separator.

    fnmatch would let `*` cross `/`, which quietly widens every pattern:
    `adws/adw_*.py` would match `adws/adw_data/sessions/x/y.py` as well as the
    ADW scripts it means. `**` is the way to say "cross directories".

    `**/` matches zero or more directories, so `**/*.md` covers `README.md` at
    the root as well as `docs/a/b.md`. Requiring at least one directory there
    is a trap: the pattern reads as "any markdown file anywhere" and every
    author who writes it means that.
    """
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def path_matches(path: str, pattern: str) -> bool:
    """One path against one pattern: prefix, glob, or exact equality.

    Backslashes are folded to forward slashes first. git reports forward
    slashes on every platform, but an agent reporting `changed_files` on
    Windows may not, and a permission check that silently stops matching on
    one platform is the worst possible failure of a permission check.
    """
    path = str(path).replace("\\", "/")
    if pattern.endswith("/"):                      # directory prefix
        return path.startswith(pattern)
    if "*" in pattern or "?" in pattern:
        return glob_to_regex(pattern).fullmatch(path) is not None
    return path == pattern


def repo_relative(path: str, repo_root: str) -> str:
    """An agent's reported path, reduced to the repo-relative form rules use.

    Envelopes carry whatever shape the model wrote: absolute, `./`-prefixed, or
    already relative. Every rule in this system — `writes:`, `doc_policy`, the
    stack gates — is written repo-relative, so the normalization happens once,
    here, rather than in each of them slightly differently.
    """
    text = str(path).replace("\\", "/")
    root = str(repo_root).replace("\\", "/").rstrip("/")
    if root and text.startswith(root + "/"):
        return text[len(root) + 1:]
    return text[2:] if text.startswith("./") else text
```

- [ ] **Step 4: Point `permissions.py` at it**

In `permissions.py`: delete the `_glob` and `_matches` functions entirely, remove `import re` if nothing else uses it, add `from .utils import path_matches`, and replace the three `_matches(path, p)` call sites inside `permitted` with `path_matches(path, p)`.

- [ ] **Step 5: Add the config type**

In `data_types.py`, immediately above `class SSSFConfig`, add:

```python
class DocPolicyRule(BaseModel):
    """One documentation contract: touching `when` requires `require`.

    Both sides are path globs (see utils.path_matches), so a rule can be as
    broad as `apps/web/src/**` or as narrow as one file. The gate reports a
    violation; it never edits anything, because which document a change needs
    is a judgement the repo already made and wrote down here.
    """

    when: str                       # glob matched against changed files
    require: list[str] = Field(default_factory=list)   # globs that must also change
```

Then add the field to `SSSFConfig`:

```python
class SSSFConfig(BaseModel):
    defaults: ConfigDefaults = Field(default_factory=ConfigDefaults)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    # Opt-in and empty by default. A documentation gate that fires on
    # everything gets switched off wholesale within a week, so rules are added
    # one at a time, deliberately, by the people they bind.
    doc_policy: list[DocPolicyRule] = Field(default_factory=list)
    agents: list[AgentConfig] = Field(default_factory=list)
```

- [ ] **Step 6: Write the gate**

In `gates.py`, add `from .utils import path_matches, repo_relative` to the imports and append:

```python
def doc_policy(envelope: EnvelopeBase, run) -> GateReport:
    """The repo's documentation contract, as declared in sssf.config.yaml.

    Config-driven on purpose: every repository's contract is different, and a
    contract written as code is a contract only a programmer may change. This
    gate reads YAML and compares paths — the policy itself never becomes code.

    Silent when no rule triggers. A gate that records a check per rule per run
    would bury the one violation that matters under a hundred green lines.
    """
    report = GateReport()
    changed = [repo_relative(f, getattr(run, "repo_root", ""))
               for f in getattr(envelope, "changed_files", [])]
    for rule in getattr(run.cfg, "doc_policy", []) or []:
        triggers = [f for f in changed if path_matches(f, rule.when)]
        if not triggers:
            continue
        for required in rule.require:
            present = any(path_matches(f, required) for f in changed)
            report.check(
                required,
                present,
                f"required by {rule.when}, and in the change" if present
                else f"{triggers[0]} matches {rule.when}, which requires "
                     f"{required} — not in the change")
    return report
```

- [ ] **Step 7: Document the block in the shipped config**

In `.claude/skills/sssf/templates/sssf.config.yaml`, between the `observability:` block and `agents:`, add:

```yaml
# Optional documentation contract. Empty means the doc_policy gate never fires.
# `when` and each `require` are path globs: `*` stops at a directory separator,
# `**` crosses them, a trailing `/` is a directory prefix. A rule reports a
# violation when a changed file matches `when` and no changed file matches the
# requirement — the agent is then asked to update the document, in the same
# session, with its context intact.
#
# doc_policy:
#   - when: "apps/api/**/Auth*.cs"
#     require: ["docs/AUTH.md"]
#   - when: "apps/web/src/**"
#     require: ["docs/ARCHITECTURE.md"]
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/ -v`
Expected: PASS — 0 failures across the whole suite. The pre-existing permissions tests must still pass; if any fail, the glob move changed behaviour and the regex is wrong.

- [ ] **Step 9: Commit**

```bash
git add tests/test_gates_doc_policy.py .claude/skills/sssf/templates/adws/adw_modules/utils.py .claude/skills/sssf/templates/adws/adw_modules/permissions.py .claude/skills/sssf/templates/adws/adw_modules/data_types.py .claude/skills/sssf/templates/adws/adw_modules/gates.py .claude/skills/sssf/templates/sssf.config.yaml
git commit -m "feat(gates): config-driven doc_policy on one shared path glob"
```

---

## Task 10: `ef_migration_triad`

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_gates_dotnet_svelte.py`

**Scene:** an EF Core migration is three files, not one: `20260911_AddThing.cs`, its sibling `20260911_AddThing.Designer.cs`, and the folder's `ApplicationDbContextModelSnapshot.cs`. An agent that writes only the first produces something that *compiles* — and `Database.Migrate()` then skips it, because the migration has no model metadata. The break surfaces much later as a `PendingModelChangesWarning` in an integration test, pointing at the wrong change. This is pure EF Core semantics: no repository names a path here, only the framework's own file convention.

- [ ] **Step 1: Make the stamped gate module importable in tests**

Append to `tests/conftest.py`:

```python
# The profile's gate module is stamped INTO adw_modules at install time, and it
# imports its siblings relatively (`from .data_types import ...`). Extending the
# package's search path is what lets a test import it under its real stamped
# name, with its real package context, straight from the profile source — so
# what the tests exercise is the file that ships, not a copy of it.
import adw_modules  # noqa: E402

PROFILE_GATES_SRC = TEMPLATES / "profiles" / "dotnet_svelte" / "gates"

if str(PROFILE_GATES_SRC) not in adw_modules.__path__:
    adw_modules.__path__.append(str(PROFILE_GATES_SRC))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_gates_dotnet_svelte.py`:

```python
"""The dotnet-svelte stack gates. Each is a pure function over a changeset."""

from types import SimpleNamespace

from adw_modules.data_types import BuildOutput
from adw_modules.gates_dotnet_svelte import ef_migration_triad

MIGRATION = "apps/api/Api/Migrations/20260911120000_AddThing.cs"
DESIGNER = "apps/api/Api/Migrations/20260911120000_AddThing.Designer.cs"
SNAPSHOT = "apps/api/Api/Migrations/AppDbContextModelSnapshot.cs"


def _run(tmp_path):
    return SimpleNamespace(repo_root=str(tmp_path), cfg=SimpleNamespace())


def _touch(tmp_path, *relatives):
    for relative in relatives:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// generated\n")


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


def test_a_change_with_no_migration_is_silent(tmp_path):
    report = ef_migration_triad(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path))
    assert report.passed
    assert report.checks == []


def test_a_complete_triad_passes(tmp_path):
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, DESIGNER, SNAPSHOT]), _run(tmp_path))
    assert report.passed
    assert len(report.checks) == 2


def test_a_migration_with_no_designer_fails(tmp_path):
    _touch(tmp_path, MIGRATION, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, SNAPSHOT]), _run(tmp_path))
    assert not report.passed
    assert "Designer.cs" in report.violations[0]


def test_a_migration_with_an_unchanged_snapshot_fails(tmp_path):
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, DESIGNER]), _run(tmp_path))
    assert not report.passed
    assert "snapshot" in report.violations[0].lower()


def test_the_designer_may_be_on_disk_without_being_in_the_change(tmp_path):
    """Editing an existing migration does not rewrite its Designer file."""
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, SNAPSHOT]), _run(tmp_path))
    assert report.passed


def test_a_designer_file_is_not_itself_treated_as_a_migration(tmp_path):
    _touch(tmp_path, DESIGNER)
    assert ef_migration_triad(_envelope([DESIGNER]), _run(tmp_path)).checks == []


def test_a_snapshot_file_is_not_itself_treated_as_a_migration(tmp_path):
    _touch(tmp_path, SNAPSHOT)
    assert ef_migration_triad(_envelope([SNAPSHOT]), _run(tmp_path)).checks == []


def test_a_non_cs_file_in_a_migrations_folder_is_ignored(tmp_path):
    other = "apps/api/Api/Migrations/README.md"
    _touch(tmp_path, other)
    assert ef_migration_triad(_envelope([other]), _run(tmp_path)).checks == []


def test_the_migrations_folder_may_live_anywhere(tmp_path):
    """EF Core's convention is the folder NAME, not a location in the tree."""
    elsewhere = "src/Data/Migrations/20260101_Init.cs"
    snapshot = "src/Data/Migrations/CtxModelSnapshot.cs"
    _touch(tmp_path, elsewhere, snapshot)
    report = ef_migration_triad(_envelope([elsewhere, snapshot]), _run(tmp_path))
    assert len(report.checks) == 2
    assert not report.passed          # no Designer.cs beside it


def test_two_migrations_in_one_change_are_each_checked(tmp_path):
    second = "apps/api/Api/Migrations/20260912130000_AddOther.cs"
    _touch(tmp_path, MIGRATION, DESIGNER, second, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, second, SNAPSHOT]), _run(tmp_path))
    assert len(report.checks) == 4
    assert len(report.violations) == 1       # only the second lacks a Designer
    assert "AddOther" in report.violations[0]


def test_windows_separators_in_changed_files_are_handled(tmp_path):
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    windows = [p.replace("/", "\\") for p in (MIGRATION, DESIGNER, SNAPSHOT)]
    assert ef_migration_triad(_envelope(windows), _run(tmp_path)).passed
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gates_dotnet_svelte.py -v`
Expected: FAIL — `No module named 'adw_modules.gates_dotnet_svelte'`.

- [ ] **Step 4: Write the gate module**

Create `.claude/skills/sssf/templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py`:

```python
"""Stack gates for ASP.NET Core + EF Core + SvelteKit repositories.

STAMPED into adws/adw_modules/ by `install.py --profile dotnet-svelte`, which
is why the imports below are relative: this file is part of that package once
it lands.

Every rule here is a fact about a FRAMEWORK, never about a repository. EF Core
writes three files per migration; SvelteKit exposes variables by prefix; a CSP
lives in the server hook. Anything that varies per repo — which directory, which
example file, which prefixes — arrives as a parameter from detection.
"""

from __future__ import annotations

import re
from pathlib import Path

from .data_types import EnvelopeBase, GateReport
from .utils import repo_relative

# EF Core's own file convention, and the only thing this gate knows.
MIGRATIONS_DIR = "Migrations"
DESIGNER_SUFFIX = ".Designer.cs"
SNAPSHOT_SUFFIX = "ModelSnapshot.cs"


def _changed(envelope: EnvelopeBase, run) -> list[str]:
    return [repo_relative(f, getattr(run, "repo_root", ""))
            for f in getattr(envelope, "changed_files", [])]


def ef_migration_triad(envelope: EnvelopeBase, run) -> GateReport:
    """An EF Core migration is three files. Two of them are easy to forget.

    Without the sibling `.Designer.cs`, `Database.Migrate()` SKIPS the migration
    rather than failing — the schema silently does not change. Without an
    updated `*ModelSnapshot.cs`, the next migration is generated against a stale
    model and re-emits changes that are already applied. Both break far from
    where they were caused, which is exactly what a gate is for.

    The designer is checked on DISK, not in the changeset: editing an existing
    migration legitimately leaves its designer untouched. The snapshot is
    checked in the CHANGESET, because a migration that alters the model and
    leaves the snapshot alone is wrong however old the migration is.
    """
    report = GateReport()
    changed = _changed(envelope, run)
    for path in changed:
        parts = path.split("/")
        name = parts[-1]
        if MIGRATIONS_DIR not in parts[:-1] or not name.endswith(".cs"):
            continue
        if name.endswith(DESIGNER_SUFFIX) or name.endswith(SNAPSHOT_SUFFIX):
            continue

        directory = "/".join(parts[:-1])
        designer = f"{directory}/{name[:-3]}{DESIGNER_SUFFIX}"
        exists = (Path(run.repo_root) / designer).is_file()
        report.check(designer, exists,
                     "exists beside the migration" if exists else
                     f"{name} has no {DESIGNER_SUFFIX} — EF Core skips a migration "
                     f"with no model metadata instead of failing")

        snapshots = [f for f in changed
                     if f.startswith(f"{directory}/") and f.endswith(SNAPSHOT_SUFFIX)]
        report.check(f"{directory}/*{SNAPSHOT_SUFFIX}", bool(snapshots),
                     f"snapshot updated: {snapshots[0]}" if snapshots else
                     f"{name} changes the model but no model snapshot in "
                     f"{directory}/ was updated — the next migration will be "
                     f"generated against a stale model")
    return report
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gates_dotnet_svelte.py -v`
Expected: PASS — 11 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_gates_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/gates/
git commit -m "feat(gates): ef_migration_triad, the three-file EF Core change"
```

---

## Task 11: `env_example_sync`

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py`
- Test: `tests/test_gates_dotnet_svelte.py` (append)

**Scene:** SvelteKit exposes only variables prefixed `PUBLIC_`; Vite only `VITE_`. Both are build-tool conventions, not repo conventions. A frontend file that reads `PUBLIC_API_URL` while `.env.example` never mentions it produces a build that works on the author's machine and fails for everyone else, with a runtime `undefined` rather than an error. The gate is a factory because *which* directory and *which* example file are discovered facts.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gates_dotnet_svelte.py`:

```python
from adw_modules.gates_dotnet_svelte import env_example_sync

PREFIXES = ["PUBLIC_", "VITE_"]


def test_no_frontend_change_means_no_checks(tmp_path):
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path))
    assert report.passed
    assert report.checks == []


def test_a_public_variable_absent_from_the_example_fails(tmp_path):
    source = "apps/web/src/lib/api.ts"
    (tmp_path / "apps" / "web" / "src" / "lib").mkdir(parents=True)
    (tmp_path / source).write_text("import { PUBLIC_API_URL } from '$env/static/public';\n")
    (tmp_path / "apps" / "web" / ".env.example").write_text("PUBLIC_OTHER=\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "PUBLIC_API_URL" in report.violations[0]


def test_a_public_variable_present_in_the_example_passes(tmp_path):
    source = "apps/web/src/lib/api.ts"
    (tmp_path / "apps" / "web" / "src" / "lib").mkdir(parents=True)
    (tmp_path / source).write_text("import { PUBLIC_API_URL } from '$env/static/public';\n")
    (tmp_path / "apps" / "web" / ".env.example").write_text("PUBLIC_API_URL=http://x\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_vite_prefixed_variables_are_checked_too(tmp_path):
    source = "apps/web/src/main.ts"
    (tmp_path / "apps" / "web" / "src").mkdir(parents=True)
    (tmp_path / source).write_text("const key = import.meta.env.VITE_MAP_KEY;\n")
    (tmp_path / "apps" / "web" / ".env.example").write_text("")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "VITE_MAP_KEY" in gate(_envelope([source]), _run(tmp_path)).violations[0]


def test_a_private_variable_is_not_this_gate_s_business(tmp_path):
    source = "apps/web/src/lib/db.ts"
    (tmp_path / "apps" / "web" / "src" / "lib").mkdir(parents=True)
    (tmp_path / source).write_text("import { DATABASE_URL } from '$env/static/private';\n")
    (tmp_path / "apps" / "web" / ".env.example").write_text("")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_a_change_in_another_frontend_is_checked_against_its_own_example(tmp_path):
    for app in ("web", "admin"):
        (tmp_path / "apps" / app / "src").mkdir(parents=True)
        (tmp_path / "apps" / app / ".env.example").write_text("")
    (tmp_path / "apps/admin/src/x.ts").write_text("const u = PUBLIC_ADMIN_URL;\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example"),
                             ("apps/admin", "apps/admin/.env.example")], PREFIXES)
    report = gate(_envelope(["apps/admin/src/x.ts"]), _run(tmp_path))

    assert len(report.checks) == 1
    assert "apps/admin/.env.example" in report.violations[0]


def test_a_non_source_file_is_not_scanned(tmp_path):
    (tmp_path / "apps" / "web").mkdir(parents=True)
    (tmp_path / "apps/web/README.md").write_text("set PUBLIC_DOCS_URL before running\n")
    (tmp_path / "apps" / "web" / ".env.example").write_text("")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope(["apps/web/README.md"]), _run(tmp_path)).passed


def test_a_deleted_source_file_does_not_crash_the_gate(tmp_path):
    """changed_files includes deletions; the file is gone from disk."""
    (tmp_path / "apps" / "web").mkdir(parents=True)
    (tmp_path / "apps" / "web" / ".env.example").write_text("")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope(["apps/web/src/gone.ts"]), _run(tmp_path)).passed


def test_a_missing_example_file_is_reported_not_raised(tmp_path):
    source = "apps/web/src/a.ts"
    (tmp_path / "apps" / "web" / "src").mkdir(parents=True)
    (tmp_path / source).write_text("const u = PUBLIC_API_URL;\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))
    assert not report.passed


def test_the_gate_has_a_readable_name_for_the_trace():
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "env_example_sync" in gate.__name__
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gates_dotnet_svelte.py -v`
Expected: FAIL — `cannot import name 'env_example_sync'`.

- [ ] **Step 3: Implement the factory**

Append to `gates_dotnet_svelte.py`:

```python
# Files worth scanning for variable references. A README that mentions a
# variable is documentation, not a dependency on it.
SOURCE_SUFFIXES = {".ts", ".js", ".mjs", ".cjs", ".svelte", ".tsx", ".jsx"}


def _read(path: Path) -> str:
    """File text, or empty when it is gone — a deletion is in changed_files too."""
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def env_example_sync(pairs: list[tuple[str, str]], prefixes: list[str]):
    """Gate factory: a public variable a frontend reads must be in its example file.

    `pairs` is (frontend directory, its example file) and `prefixes` the build
    tools' public-variable conventions — SvelteKit's `PUBLIC_`, Vite's `VITE_`.
    All three are discovered at install time, which is what keeps this gate a
    stack rule rather than one repository's rule.

    It checks every public variable the changed files reference, not only newly
    added ones. Deriving "newly added" needs a diff and gives a weaker answer:
    a variable that was missing from the example three commits ago is just as
    broken for the next person who clones.
    """
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in prefixes)
                         + r")[A-Z0-9_]+\b")

    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = _changed(envelope, run)
        for directory, example in pairs:
            prefix = directory.rstrip("/") + "/"
            sources = [f for f in changed
                       if f.startswith(prefix) and Path(f).suffix in SOURCE_SUFFIXES]
            if not sources:
                continue
            declared = _read(Path(run.repo_root) / example)
            referenced = set()
            for source in sources:
                referenced |= set(pattern.findall(_read(Path(run.repo_root) / source)))
            for name in sorted(referenced):
                present = name in declared
                report.check(f"{name} in {example}", present,
                             "declared" if present else
                             f"{name} is read by {directory} but {example} does not "
                             f"declare it — the build works here and nowhere else")
        return report

    gate.__name__ = f"env_example_sync({len(pairs)} frontend(s))"
    return gate
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gates_dotnet_svelte.py -v`
Expected: PASS — 21 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gates_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py
git commit -m "feat(gates): env_example_sync for PUBLIC_ and VITE_ variables"
```

---

## Task 12: `sveltekit_csp`

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py`
- Test: `tests/test_gates_dotnet_svelte.py` (append)

**Scene:** a SvelteKit app that sets a Content-Security-Policy in `src/hooks.server.ts` will block any origin the policy does not list — silently, in the browser, at runtime. Adding a script tag or a fetch to a new host therefore has a second half that is easy to forget. The gate only exists for frontends where detection actually found a CSP, so a repo without one never sees it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gates_dotnet_svelte.py`:

```python
from adw_modules.gates_dotnet_svelte import sveltekit_csp

HOOKS = "apps/web/src/hooks.server.ts"


def _web(tmp_path, hooks_text="const csp = \"default-src 'self'\";\n"):
    (tmp_path / "apps" / "web" / "src").mkdir(parents=True)
    (tmp_path / HOOKS).write_text(hooks_text)


def test_no_frontend_change_means_no_checks(tmp_path):
    _web(tmp_path)
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path)).checks == []


def test_a_new_external_origin_requires_the_hooks_file_to_change(tmp_path):
    _web(tmp_path)
    source = "apps/web/src/lib/maps.ts"
    (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / source).write_text("fetch('https://tiles.example.com/a.png');\n")

    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "tiles.example.com" in report.violations[0]


def test_an_origin_already_in_the_policy_is_fine(tmp_path):
    _web(tmp_path, "const csp = \"img-src https://tiles.example.com\";\n")
    source = "apps/web/src/lib/maps.ts"
    (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / source).write_text("fetch('https://tiles.example.com/a.png');\n")

    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_changing_the_hooks_file_satisfies_the_gate(tmp_path):
    _web(tmp_path)
    source = "apps/web/src/lib/maps.ts"
    (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / source).write_text("fetch('https://tiles.example.com/a.png');\n")

    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source, HOOKS]), _run(tmp_path)).passed


def test_localhost_is_not_an_external_origin(tmp_path):
    _web(tmp_path)
    source = "apps/web/src/lib/dev.ts"
    (tmp_path / source).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / source).write_text("fetch('http://localhost:5173/x');\n"
                                   "fetch('http://127.0.0.1:8080/y');\n")

    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_the_hooks_file_itself_is_not_scanned_for_origins(tmp_path):
    _web(tmp_path, "const csp = \"connect-src https://api.example.com\";\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([HOOKS]), _run(tmp_path)).checks == []


def test_the_gate_has_a_readable_name_for_the_trace():
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert "sveltekit_csp" in gate.__name__
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gates_dotnet_svelte.py -v`
Expected: FAIL — `cannot import name 'sveltekit_csp'`.

- [ ] **Step 3: Implement the factory**

Append to `gates_dotnet_svelte.py`:

```python
ORIGIN = re.compile(r"https?://[A-Za-z0-9.\-]+(?::\d+)?")

# A development host is not an origin a production policy has to allow.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


def sveltekit_csp(pairs: list[tuple[str, str]]):
    """Gate factory: a new external origin requires the CSP to be updated.

    `pairs` is (frontend directory, its src/hooks.server.ts). Only frontends
    where detection found an actual policy are wired, because a repo with no
    CSP would see this fire on every external URL it ever adds — and a gate
    that cries wolf gets deleted along with the ones that do not.

    The failure it prevents is browser-side and silent: the request is blocked,
    nothing throws on the server, and the feature simply does not work.
    """
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = _changed(envelope, run)
        for directory, hooks in pairs:
            prefix = directory.rstrip("/") + "/"
            sources = [f for f in changed
                       if f.startswith(prefix) and f != hooks
                       and Path(f).suffix in SOURCE_SUFFIXES]
            if not sources:
                continue
            policy = _read(Path(run.repo_root) / hooks)
            origins = set()
            for source in sources:
                origins |= set(ORIGIN.findall(_read(Path(run.repo_root) / source)))
            unknown = sorted(o for o in origins
                             if not any(host in o for host in LOCAL_HOSTS)
                             and o not in policy)
            if not unknown:
                continue
            report.check(hooks, hooks in changed,
                         "updated alongside the new origin(s)" if hooks in changed else
                         f"{len(unknown)} origin(s) not in the CSP and {hooks} was not "
                         f"changed: {', '.join(unknown[:3])} — the browser will block "
                         f"these and nothing will throw on the server")
        return report

    gate.__name__ = f"sveltekit_csp({len(pairs)} frontend(s))"
    return gate
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gates_dotnet_svelte.py -v`
Expected: PASS — 28 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gates_dotnet_svelte.py .claude/skills/sssf/templates/profiles/dotnet_svelte/gates/gates_dotnet_svelte.py
git commit -m "feat(gates): sveltekit_csp, opt-in on a detected policy"
```

---

## Task 13: Generate `profile_gates.py`, and load it from core

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/gates.py`
- Test: `tests/test_generate_dotnet_svelte.py` (append), `tests/test_gates_doc_policy.py` (append)

**Scene:** the three gates from Tasks 10–12 are dead code until something puts them in a gate list. Two of them are factories that need discovered facts, so the wiring itself has to be generated — and the core has to be able to load it without knowing any profile exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_generate_dotnet_svelte.py`:

```python
def test_gate_wiring_always_includes_the_migration_gate(tmp_path):
    facts = _facts(tmp_path)
    report = gen.generate(facts, tmp_path)
    assert "ef_migration_triad" in report.gates


def test_env_example_sync_is_wired_only_when_an_example_exists(tmp_path):
    facts = _facts(tmp_path)
    assert "env_example_sync" not in gen.generate(facts, tmp_path, write=False).gates

    (tmp_path / "apps" / "web" / ".env.example").write_text("PUBLIC_X=\n")
    facts = det.detect(tmp_path)
    assert "env_example_sync" in gen.generate(facts, tmp_path, write=False).gates


def test_csp_is_wired_only_when_a_policy_was_detected(tmp_path):
    from profile_fixtures import write
    facts = _facts(tmp_path)
    assert "sveltekit_csp" not in gen.generate(facts, tmp_path, write=False).gates

    write(tmp_path, "apps/web/src/hooks.server.ts", "// csp lives here\n")
    facts = det.detect(tmp_path)
    assert "sveltekit_csp" in gen.generate(facts, tmp_path, write=False).gates


def test_the_generated_gate_module_is_valid_python(tmp_path):
    import ast
    from profile_fixtures import write
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    write(tmp_path, "apps/web/src/hooks.server.ts", "// csp\n")
    facts = _facts(tmp_path)
    gen.generate(facts, tmp_path)

    text = (tmp_path / "adws" / "adw_modules" / "profile_gates.py").read_text()
    ast.parse(text)
    assert "PROFILE_GATES" in text
    assert "from .gates_dotnet_svelte import" in text
    assert "apps/web/.env.example" in text


def test_the_generated_wiring_builds_real_callables(tmp_path):
    """Execute the generated module against the real gate factories."""
    from profile_fixtures import write
    from adw_modules import gates_dotnet_svelte
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    facts = _facts(tmp_path)
    gen.generate(facts, tmp_path)

    text = (tmp_path / "adws" / "adw_modules" / "profile_gates.py").read_text()
    body = text.split("import", 1)[1].split("\n", 1)[1]
    namespace = {name: getattr(gates_dotnet_svelte, name)
                 for name in ("ef_migration_triad", "env_example_sync", "sveltekit_csp")}
    exec(body, namespace)
    assert all(callable(gate) for gate in namespace["PROFILE_GATES"])
```

Append to `tests/test_gates_doc_policy.py`:

```python
def test_profile_gates_is_empty_when_nothing_was_generated(monkeypatch):
    monkeypatch.setattr(gates, "_import_profile_gates", lambda: None)
    assert gates.profile_gates() == []


def test_profile_gates_returns_what_was_generated(monkeypatch):
    sentinel = [lambda envelope, run: None]
    monkeypatch.setattr(gates, "_import_profile_gates", lambda: sentinel)
    assert gates.profile_gates() == sentinel


def test_a_broken_generated_gate_module_is_not_swallowed(monkeypatch):
    import pytest

    def raise_unrelated():
        raise ModuleNotFoundError("No module named 'missing_thing'", name="missing_thing")

    monkeypatch.setattr(gates, "_import_profile_gates", raise_unrelated)
    with pytest.raises(ModuleNotFoundError):
        gates.profile_gates()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_generate_dotnet_svelte.py tests/test_gates_doc_policy.py -v`
Expected: FAIL — `report.gates` is empty and `gates._import_profile_gates` does not exist.

- [ ] **Step 3: Add the loader to core `gates.py`**

Append to `.claude/skills/sssf/templates/adws/adw_modules/gates.py`:

```python
def _import_profile_gates() -> list | None:
    """The generated profile gate list, or None when no profile wrote one.

    Only a missing module means "not generated". Any other import error is
    re-raised: a gate list that silently shrinks to nothing is a definition of
    done that quietly stopped being enforced.
    """
    try:
        from .profile_gates import PROFILE_GATES
    except ModuleNotFoundError as error:
        if error.name in ("adw_modules.profile_gates", "profile_gates"):
            return None
        raise
    return list(PROFILE_GATES)


def profile_gates() -> list:
    """The stack gates a profile wired for this repo. Empty without one.

    Spread into a phase's gate list: `gates=[gates.diff_matches_claims,
    *gates.profile_gates()]`. An un-profiled repo gets an empty list and
    behaves exactly as it did before profiles existed.
    """
    wired = _import_profile_gates()
    return list(wired) if wired is not None else []
```

- [ ] **Step 4: Generate the wiring**

In `generate.py`, add the constant beside `BLOCKS_RELATIVE`:

```python
GATES_RELATIVE = "adws/adw_modules/profile_gates.py"

GATES_HEADER = '''"""GENERATED — do not expect edits here to survive a re-install.

Written by `install.py --profile {profile}` at {stamp}.

The stack gates, parameterized with what detection found in THIS repository.
`gates.profile_gates()` loads this list; an un-profiled repo has no such file
and gets an empty list instead.

Each gate is a plain function of (envelope, run). To stop enforcing one, delete
its line — the factory will not argue, and the next re-install will put it back.
"""

from .gates_dotnet_svelte import ef_migration_triad, env_example_sync, sveltekit_csp

PROFILE_GATES = [
{entries}]
'''
```

Add the wiring builder above `generate`:

```python
def gate_wiring(facts: ProfileFacts, config: dict) -> tuple[list[str], list[str]]:
    """The rendered gate entries, and the names for the install report.

    A gate is wired only when the fact it needs was actually found. Wiring
    `sveltekit_csp` at a repo with no policy would fire on every external URL
    forever, and a gate that cries wolf is deleted along with the ones that do
    not — so an absent fact means an absent gate, not a disabled one.
    """
    entries = ["    ef_migration_triad,\n"]
    names = ["ef_migration_triad"]

    env_pairs = [(f.directory, f.env_example) for f in facts.frontends if f.env_example]
    if env_pairs:
        prefixes = list(config.get("env_prefixes") or [])
        entries.append(f"    env_example_sync({env_pairs!r}, {prefixes!r}),\n")
        names.append("env_example_sync")

    csp_pairs = [(f.directory, f.hooks_server) for f in facts.frontends if f.hooks_server]
    if csp_pairs:
        entries.append(f"    sveltekit_csp({csp_pairs!r}),\n")
        names.append("sveltekit_csp")
    return entries, names


def render_gates(facts: ProfileFacts, entries: list[str]) -> str:
    return GATES_HEADER.format(
        profile=facts.profile,
        stamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        entries="".join(entries))
```

Replace `generate` with:

```python
def generate(facts: ProfileFacts, root, write: bool = True) -> GenerationReport:
    """Facts in, files out. `write=False` is the --doctor dry run."""
    config = _config()
    blocks, unresolved = quality_blocks(facts, config)
    entries, gate_names = gate_wiring(facts, config)
    written: list[str] = []
    if write:
        _write(root, BLOCKS_RELATIVE, render_blocks(facts, blocks), written)
        _write(root, GATES_RELATIVE, render_gates(facts, entries), written)
    return GenerationReport(profile=facts.profile, files=written, blocks=blocks,
                            gates=gate_names, unresolved=unresolved)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_generate_dotnet_svelte.py tests/test_gates_doc_policy.py -v`
Expected: PASS — 19 in test_generate_dotnet_svelte.py and 17 in test_gates_doc_policy.py.

- [ ] **Step 6: Commit**

```bash
git add tests/test_generate_dotnet_svelte.py tests/test_gates_doc_policy.py .claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py .claude/skills/sssf/templates/adws/adw_modules/gates.py
git commit -m "feat(profiles): generate gate wiring and load it from core gates"
```

---

## Task 14: Wire the gates into every build phase

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_build.py`, `adw_build_review.py`, `adw_build_test.py`, `adw_plan_build.py`, `adw_plan_build_test.py`, `adw_plan_build_test_quality.py`, `adw_simple_sdlc.py`
- Test: `tests/test_gate_wiring.py`

**Scene:** a gate nobody calls is a comment. The rule that decides where these belong is simple and checkable: **every agent call whose `output_type` is `BuildOutput` is a phase that changed code**, and those are exactly the phases whose claims `doc_policy` and the stack gates check. A test enforces the rule across the whole ADW directory, so a new ADW written next month cannot quietly skip it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_wiring.py`:

```python
"""Every code-changing phase runs the repo's own gates.

This is a structural test over the shipped ADW scripts, not a behavioural one.
It exists because the failure it catches is invisible at runtime: a build phase
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
        source = _gate_source(call)
        assert "*gates.profile_gates()" in source, name
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate_wiring.py -v`
Expected: FAIL — every build phase is listed as missing both gates.

- [ ] **Step 3: Wire the gates**

In each of the seven ADW scripts, find every `AgentCall(output_type=BuildOutput, ...)` and extend its `gates=` list with `gates.doc_policy` and `*gates.profile_gates()`. There are two existing shapes:

```python
                                     gates=[gates.diff_matches_claims]))
```
becomes
```python
                                     gates=[gates.diff_matches_claims, gates.doc_policy,
                                            *gates.profile_gates()]))
```

and (in `adw_plan_build_test.py`, both the `build` and `fix_{i}` phases)

```python
                                     gates=[gates.artifacts_exist]))
```
becomes
```python
                                     gates=[gates.artifacts_exist, gates.doc_policy,
                                            *gates.profile_gates()]))
```

There are **13** such calls today, spread over the seven files above:
`adw_build.py` 1, `adw_build_review.py` 2, `adw_build_test.py` 2,
`adw_plan_build.py` 1, `adw_plan_build_test.py` 2,
`adw_plan_build_test_quality.py` 2, `adw_simple_sdlc.py` 3. Use the test to
find them rather than trusting that tally — run it after each file and watch
the `missing` set shrink. Do not change any gate list on a phase whose `output_type` is not `BuildOutput`: a planner writing a spec has not changed code, and a reviewer must not be asked to update a document it is not allowed to write.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate_wiring.py -v`
Expected: PASS — 4 passed.

- [ ] **Step 5: Confirm nothing else broke**

Run: `uv run pytest tests/ -v`
Expected: PASS — 0 failures across the whole suite.

- [ ] **Step 6: Commit**

```bash
git add tests/test_gate_wiring.py .claude/skills/sssf/templates/adws/adw_build.py .claude/skills/sssf/templates/adws/adw_build_review.py .claude/skills/sssf/templates/adws/adw_build_test.py .claude/skills/sssf/templates/adws/adw_plan_build.py .claude/skills/sssf/templates/adws/adw_plan_build_test.py .claude/skills/sssf/templates/adws/adw_plan_build_test_quality.py .claude/skills/sssf/templates/adws/adw_simple_sdlc.py
git commit -m "feat(adws): every code-changing phase runs doc_policy and profile gates"
```

---

## Task 15: The prompt overlay

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agents.py`
- Modify: `.claude/skills/sssf/templates/prompt_engineering/builder/system.md`
- Modify: `.claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py`
- Create: `.claude/skills/sssf/templates/profiles/dotnet_svelte/prompts/overlay.md`
- Test: `tests/test_prompt_overlay.py`

**Scene:** the shipped builder prompt tells agents to call `bun`, `uv`, and `pytest` — right for the repo SSSF was written in, wrong for this stack. The overlay replaces that with stack guidance, and with a list of the convention files detection actually found. Repository standards are **referenced, never restated**: copying `CLAUDE.md` into a prompt duplicates it and then drifts from it, and .NET 10 / C# 14 and Svelte 5 runes post-date most model priors, so pointing at the live file is also the more accurate answer.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prompt_overlay.py`:

```python
"""The profile overlay: stack guidance injected into the builder's prompt."""

from pathlib import Path
from types import SimpleNamespace

from profile_fixtures import dotnet_svelte_repo, write
from profiles.dotnet_svelte import detect as det
from profiles.dotnet_svelte import generate as gen

from adw_modules import agents

TEMPLATES = (Path(__file__).resolve().parent.parent
             / ".claude" / "skills" / "sssf" / "templates")


def test_the_shipped_builder_prompt_has_the_placeholder():
    text = (TEMPLATES / "prompt_engineering" / "builder" / "system.md").read_text()
    assert "{{profile_overlay}}" in text


def test_the_shipped_builder_prompt_names_no_toolchain():
    """bun/uv/pytest were THIS repo's tools, not every repo's.

    Matched on the backticked forms the prompt actually used, not bare
    substrings: `uv` appears inside ordinary English words and a test that
    fails on the word "value" teaches nobody anything.
    """
    text = (TEMPLATES / "prompt_engineering" / "builder" / "system.md").read_text()
    for tool in ("`bun`", "`uv`", "`pytest`"):
        assert tool not in text
    assert "stack notes below" in text


def test_the_overlay_is_empty_when_no_profile_generated_one(tmp_path):
    run = SimpleNamespace(cfg=SimpleNamespace(
        defaults=SimpleNamespace(data_dir=str(tmp_path / "adw_data"))))
    assert agents.profile_overlay(run) == ""


def test_the_overlay_is_read_when_it_exists(tmp_path):
    overlay = tmp_path / "adw_data" / "prompt_engineering" / "profile_overlay.md"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("## Stack\n\nrunes, not stores.\n")
    run = SimpleNamespace(cfg=SimpleNamespace(
        defaults=SimpleNamespace(data_dir=str(tmp_path / "adw_data"))))
    assert "runes, not stores" in agents.profile_overlay(run)


def test_generation_writes_the_overlay(tmp_path):
    dotnet_svelte_repo(tmp_path)
    report = gen.generate(det.detect(tmp_path), tmp_path)
    overlay = tmp_path / "adws" / "adw_data" / "prompt_engineering" / "profile_overlay.md"
    assert overlay.exists()
    assert str(overlay) in [str(Path(f)) for f in report.files]


def test_the_overlay_references_convention_files_rather_than_restating_them(tmp_path):
    dotnet_svelte_repo(tmp_path)
    write(tmp_path, "CLAUDE.md", "NEVER use var in C#.\n")
    write(tmp_path, ".github/instructions/csharp.instructions.md", "# c#\n")
    gen.generate(det.detect(tmp_path), tmp_path)

    text = (tmp_path / "adws" / "adw_data" / "prompt_engineering"
            / "profile_overlay.md").read_text()

    assert "CLAUDE.md" in text
    assert ".github/instructions/" in text
    # the CONTENT of the convention file must not be copied in
    assert "NEVER use var" not in text


def test_the_overlay_names_the_detected_task_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(det, "_summary", lambda root: None)
    dotnet_svelte_repo(tmp_path, justfile_text="test-unit:\n    dotnet test\n")
    gen.generate(det.detect(tmp_path), tmp_path)
    text = (tmp_path / "adws" / "adw_data" / "prompt_engineering"
            / "profile_overlay.md").read_text()
    assert "just" in text


def test_the_overlay_says_so_when_there_are_no_conventions(tmp_path):
    dotnet_svelte_repo(tmp_path)
    gen.generate(det.detect(tmp_path), tmp_path)
    text = (tmp_path / "adws" / "adw_data" / "prompt_engineering"
            / "profile_overlay.md").read_text()
    assert "EF Core" in text            # the stack half is always present
    assert "no convention files" in text.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_prompt_overlay.py -v`
Expected: FAIL — the placeholder is absent, `agents.profile_overlay` does not exist.

- [ ] **Step 3: Add the prompt variable**

In `agents.py`, add `from pathlib import Path` if absent, then add above `execute`:

```python
def profile_overlay(run) -> str:
    """Stack guidance a profile generated for this repo, or nothing.

    A variable rather than a rewritten prompt file: the prompts are where an
    operator's own standards live, and an installer that overwrites them would
    delete the most valuable thing in the stamped tree. Any prompt that wants
    the overlay includes `{{profile_overlay}}`; one that does not, does not.
    """
    path = (Path(run.cfg.defaults.data_dir) / "prompt_engineering"
            / "profile_overlay.md")
    return path.read_text(encoding="utf-8") if path.is_file() else ""
```

and add the entry to the `variables` dict inside `execute`:

```python
    variables = {
        "prompt": call.prompt,
        "previous_envelope": call.previous.model_dump_json(indent=2) if call.previous else "(none)",
        "context_handoff_dir": str(run.context_handoff_dir),
        "profile_overlay": profile_overlay(run),
    }
```

- [ ] **Step 4: Edit the shipped builder prompt**

In `.claude/skills/sssf/templates/prompt_engineering/builder/system.md`, replace the toolchain bullet:

```
- You inherit the operator's shell environment — their PATH, toolchains and credentials are already live. Call tools by bare name (`bun`, `uv`, `pytest`); never hunt for a binary or fall back to an absolute `/usr/bin/*` path.
```

with:

```
- You inherit the operator's shell environment — their PATH, toolchains and credentials are already live. Call tools by bare name; never hunt for a binary or fall back to an absolute `/usr/bin/*` path. Which tools this repo uses is in the stack notes below, if there are any.
```

and append at the end of the file:

```

{{profile_overlay}}
```

- [ ] **Step 5: Write the overlay template**

Create `.claude/skills/sssf/templates/profiles/dotnet_svelte/prompts/overlay.md`:

```markdown
## Stack notes

This repository is ASP.NET Core + EF Core on the backend and SvelteKit on the
frontend. Four things about that stack are worth stating, because getting them
wrong produces code that compiles and then misbehaves at runtime.

- **An EF Core migration is three files, not one.** The migration, its sibling
  `.Designer.cs`, and the folder's `*ModelSnapshot.cs`. Generate migrations with
  the EF tooling rather than writing the file by hand — a migration with no
  Designer file is silently SKIPPED by `Database.Migrate()`, so the schema does
  not change and nothing errors.
- **Svelte 5 uses runes.** `$state`, `$derived`, `$effect`, `$props` — not
  `writable`/`readable` stores and not `export let`. Both spellings still work,
  which is why this is worth saying: a legacy-style component will run, and will
  be the odd one out forever.
- **Only prefixed environment variables reach the browser.** SvelteKit exposes
  `PUBLIC_*` and Vite exposes `VITE_*`. Adding one means adding it to the
  frontend's example env file in the same change.
- **Judge success by exit status**, never by scanning output for the word
  "error". A build that prints warnings and exits 0 succeeded.

{{commands}}

## This repository's own standards

{{conventions}}
```

- [ ] **Step 6: Render and write it from the generator**

In `generate.py`, add the constant beside `GATES_RELATIVE`:

```python
OVERLAY_RELATIVE = "adws/adw_data/prompt_engineering/profile_overlay.md"

NO_CONVENTIONS = (
    "This repository has no convention files (no CLAUDE.md, AGENTS.md, or\n"
    "instructions directory were found), so there is nothing extra to read.\n"
    "Follow the patterns in the code you are editing.")
```

and these functions above `generate`:

```python
def render_overlay(facts: ProfileFacts) -> str:
    """The stack half is fixed; the repository half is whatever was found.

    Convention files are LISTED, never inlined. Copying a repo's standards into
    a prompt duplicates them and then drifts from them — and the live file is
    the one the humans keep correct.
    """
    template = (Path(__file__).parent / "prompts" / "overlay.md").read_text(
        encoding="utf-8")

    if facts.task_runner:
        commands = (f"This repository drives its commands through `{facts.task_runner}`. "
                    f"Prefer a recipe over a raw command when one exists — "
                    f"`{facts.task_runner} --list` shows them.")
    else:
        commands = ("This repository has no task runner. Use `dotnet` for the "
                    "solution and the frontend's own package manager for each "
                    "frontend.")

    if facts.conventions:
        conventions = ("Read these before you change anything. They are the rules "
                       "this team already agreed on, and they win over anything "
                       "here:\n\n"
                       + "\n".join(f"- `{c}`" for c in facts.conventions))
    else:
        conventions = NO_CONVENTIONS

    return (template.replace("{{commands}}", commands)
                    .replace("{{conventions}}", conventions))
```

and add the third write inside `generate`, after the gates write:

```python
        _write(root, OVERLAY_RELATIVE, render_overlay(facts), written)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_prompt_overlay.py -v`
Expected: PASS — 8 passed.

- [ ] **Step 8: Commit**

```bash
git add tests/test_prompt_overlay.py .claude/skills/sssf/templates/adws/adw_modules/agents.py .claude/skills/sssf/templates/prompt_engineering/builder/system.md .claude/skills/sssf/templates/profiles/dotnet_svelte/prompts/ .claude/skills/sssf/templates/profiles/dotnet_svelte/generate.py
git commit -m "feat(prompts): a generated stack overlay that references, never restates"
```

---

## Task 16: `install.py --profile`

**Files:**
- Modify: `.claude/skills/sssf/scripts/install.py`
- Test: `tests/test_install_profile.py`

**Scene:** everything so far is inert until the installer runs it. `install.py` gains three flags and one new stage: after stamping the base factory, select a profile (explicitly, or by unambiguous detection), stamp its gate module, generate the three files, and print what it wired.

Two constraints carried over from Part A: **every line this file prints must be ASCII**, because the console it prints to may be cp1252 and a `UnicodeEncodeError` here would kill the install; and the report must say what it could *not* resolve as loudly as what it could.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_install_profile.py`:

```python
"""install.py --profile: stamp a factory that is wired to this repo."""

import subprocess
import sys
from pathlib import Path

from profile_fixtures import dotnet_svelte_repo, write

INSTALL = (Path(__file__).resolve().parent.parent
           / ".claude" / "skills" / "sssf" / "scripts" / "install.py")


def _install(cwd, *args):
    return subprocess.run([sys.executable, str(INSTALL), *args],
                          cwd=cwd, capture_output=True, text=True)


def _generated(root):
    modules = root / "adws" / "adw_modules"
    return {
        "blocks": modules / "quality_blocks.py",
        "gates": modules / "profile_gates.py",
        "stack_gates": modules / "gates_dotnet_svelte.py",
        "overlay": root / "adws" / "adw_data" / "prompt_engineering" / "profile_overlay.md",
    }


def test_a_matching_repo_is_profiled_automatically(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "dotnet-svelte" in result.stdout
    for path in _generated(tmp_path).values():
        assert path.is_file(), path


def test_the_generated_blocks_name_this_repo_s_real_commands(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    text = _generated(tmp_path)["blocks"].read_text()
    assert "dotnet" in text
    assert "PLACEHOLDER" not in text


def test_no_profile_leaves_the_factory_unwired(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path, "--no-profile")
    assert result.returncode == 0, result.stderr
    for path in _generated(tmp_path).values():
        assert not path.exists(), path
    # the base factory is still stamped
    assert (tmp_path / "adws" / "adw_modules" / "quality.py").is_file()


def test_an_unrecognised_repo_installs_without_a_profile(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    result = _install(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "no profile" in result.stdout.lower()
    assert (tmp_path / "adws" / "adw_modules" / "quality.py").is_file()
    assert not _generated(tmp_path)["blocks"].exists()


def test_an_unknown_profile_name_fails_and_lists_the_real_ones(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path, "--profile", "cobol-jquery")
    assert result.returncode != 0
    assert "dotnet-svelte" in result.stdout + result.stderr


def test_profile_and_no_profile_together_is_refused(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path, "--profile", "dotnet-svelte", "--no-profile")
    assert result.returncode != 0


def test_the_report_names_what_it_could_not_resolve(tmp_path):
    """A repo with no test project must say so at install time."""
    from profile_fixtures import CSPROJ_APP, frontend, sln
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    frontend(tmp_path, "web", {"build": "vite build"})
    result = _install(tmp_path)
    assert "unresolved" in result.stdout.lower()
    assert "unit-tests" in result.stdout


def test_every_line_of_output_is_ascii(tmp_path):
    """The console this prints to may be cp1252; a crash here kills the install."""
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path)
    result.stdout.encode("ascii")


def test_installing_twice_is_idempotent(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    first = _generated(tmp_path)["blocks"].read_text()
    second_result = _install(tmp_path)
    assert second_result.returncode == 0
    # the generated file is rewritten from facts, so its blocks are identical
    second = _generated(tmp_path)["blocks"].read_text()
    assert first.split("BLOCKS = [")[1] == second.split("BLOCKS = [")[1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_install_profile.py -v`
Expected: FAIL — `install.py` has no `--profile` flag, so argparse exits 2.

- [ ] **Step 3: Teach the installer about profiles**

In `.claude/skills/sssf/scripts/install.py`, change the PEP 723 header to declare the two dependencies profile code needs:

```python
# /// script
# dependencies = ["pydantic>=2", "pyyaml>=6"]
# ///
```

Below `TEMPLATES = ...`, add the import path setup and the registry import:

```python
# The profile packages live beside the templates and import each other
# relatively, so `templates/` has to be importable as a package root. This is
# the same insert tests/conftest.py performs, deliberately: what the tests
# import is what the installer imports.
if str(TEMPLATES) not in sys.path:
    sys.path.insert(0, str(TEMPLATES))

from profiles import registry  # noqa: E402  (must follow the sys.path insert)
```

Add these functions above `main`:

```python
def stamp_profile_gates(profile, root: Path, force: bool,
                        stamped: list, skipped: list) -> None:
    """Copy the profile's gate module into adws/adw_modules/.

    Stamped like every other shipped module, which means an existing copy is
    left alone without --force. A gate is code an operator is invited to edit;
    silently overwriting their edit on a re-install would be the one thing this
    installer has never done.
    """
    source = Path(profile.__file__).parent / "gates"
    if source.is_dir():
        stamp(source, root / "adws" / "adw_modules", force, stamped, skipped)


def print_profile_report(facts, report) -> None:
    """What was detected, what was wired, and what could not be.

    ASCII only, deliberately, like the Windows warning below: this is the
    output most likely to be read on a fresh machine with a cp1252 console,
    and a UnicodeEncodeError here would take the install down with it.
    """
    print(f"\nprofile: {report.profile}")
    print(f"  solution: {facts.solution or '(none)'}")
    for role in ("app", "unit-tests", "integration-tests"):
        for project in facts.projects_by_role(role):
            print(f"  project: {project.path}  [{role}]")
    for frontend in facts.frontends:
        print(f"  frontend: {frontend.directory}  [{frontend.package_manager}] "
              f"scripts: {', '.join(frontend.scripts) or 'none'}")
    print(f"  task runner: {facts.task_runner or '(none)'}"
          f"{f' ({len(facts.recipes)} recipes)' if facts.recipes else ''}")
    print(f"  default branch: {facts.default_branch}")
    print(f"  conventions: {', '.join(facts.conventions) or '(none found)'}")

    print(f"\n  quality blocks wired: {len(report.blocks)}")
    for block in report.blocks:
        location = "" if block.cwd == "." else f"  (in {block.cwd})"
        print(f"    [{block.tier:>4}] {block.name}: {' '.join(block.argv)}{location}")
    print(f"  gates wired: {', '.join(report.gates) or '(none)'}")

    if report.unresolved:
        print(f"\n  UNRESOLVED ({len(report.unresolved)}) - these are not checked "
              f"by anything:")
        for note in report.unresolved:
            print(f"    ! {note}")
    for path in report.files:
        print(f"    + {path}")


def select_profile(root: Path, name: str | None, disabled: bool):
    """The profile to apply, or None."""
    if disabled:
        return None
    if name:
        return registry.get(name)
    profile = registry.select(root)
    if profile is None:
        print(f"\nno profile matches this repo (tried: {', '.join(registry.names())}). "
              f"\n  quality.py keeps its placeholder blocks - wire them by hand, or "
              f"write a profile.")
    return profile
```

Replace `main` with:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument("--profile", metavar="NAME",
                        help=f"stack profile to apply ({', '.join(registry.names())}); "
                             f"omit to auto-detect")
    parser.add_argument("--no-profile", action="store_true",
                        help="stamp the factory only; wire nothing")
    parser.add_argument("--doctor", action="store_true",
                        help="probe and report only; write nothing")
    args = parser.parse_args()

    if args.profile and args.no_profile:
        parser.error("--profile and --no-profile contradict each other")

    root = Path.cwd()
    stamped, skipped = [], []

    if not args.doctor:
        stamp(TEMPLATES / "adws", root / "adws", args.force, stamped, skipped)
        stamp(TEMPLATES / "prompt_engineering",
              root / "adws" / "adw_data" / "prompt_engineering", args.force, stamped, skipped)
        stamp(TEMPLATES / "harness_engineering",
              root / "adws" / "adw_data" / "harness_engineering", args.force, stamped, skipped)
        stamp(TEMPLATES / "sssf.config.yaml",
              root / "adws" / "adw_sssf_config" / "sssf.config.yaml",
              args.force, stamped, skipped)
        stamp(TEMPLATES / "env.sample", root / ".env.sample", args.force, stamped, skipped)
        # The recipes are part of the operating experience, and several cookbooks
        # plus the run banner tell you to use them, so a stamped repo has to have
        # them. Skipped like any other file if the repo already has a justfile.
        stamp(TEMPLATES / "justfile", root / "justfile", args.force, stamped, skipped)
        ensure_gitignore(root, stamped)

        print(f"sssf installed into {root}")
        print(f"  stamped: {len(stamped)} file(s)")
        for s in stamped:
            print(f"    + {s}")
        if skipped:
            print(f"  skipped (already exist, use --force to overwrite): {len(skipped)}")

    profile = select_profile(root, args.profile, args.no_profile)
    if profile is not None:
        if not args.doctor:
            stamp_profile_gates(profile, root, args.force, stamped, skipped)
        facts = profile.detect(root)
        report = profile.generate(facts, root, write=not args.doctor)
        print_profile_report(facts, report)

    if args.doctor:
        # A dry run reports; it does not judge. Unresolved items are printed
        # above and are the operator's call, not an error to exit on.
        print("\n  doctor: nothing was written.")
        return 0

    print("\nnext steps:")
    print("  1. cp .env.sample .env   # then set the key(s) your roster needs")
    print("  2. just demo             # two cheap read-only runs, end to end")
    print("  3. just sessions         # what just happened")
    print("  4. just obs              # the trace UI, needs bun")
    print("\n  no just? the raw form of step 2 is:")
    print("     uv run adws/adw_prompt.py \"say hello\" --agent scout")
    if os.name == "nt":
        # ASCII only, deliberately. This is the one message that must survive the
        # very console it is warning about - an em dash here would raise the
        # UnicodeEncodeError it exists to prevent, before anyone could read it.
        print("\n  windows: set PYTHONUTF8=1 and PYTHONIOENCODING=utf-8 in your shell.")
        print("           The run banner cannot encode on a cp1252 console, and the")
        print("           crash leaves the session's trace row stuck at 'running'.")
    return 0
```

Note the em dash already in the shipped Windows warning comment was replaced with a hyphen above — keep it that way; the comment is fine either way but the print statements must stay ASCII.

- [ ] **Step 4: Update the module docstring**

Replace the `Usage:` and `Stamps:` paragraphs of `install.py`'s docstring with:

```
Usage:
    uv run <skill>/scripts/install.py [--force] [--profile NAME | --no-profile]
    uv run <skill>/scripts/install.py --doctor

Stamps: adws/ (modules + starter ADWs), adws/adw_data/prompt_engineering/
(4 starter agents), adws/adw_sssf_config/sssf.config.yaml, .env.sample,
.gitignore entries. Existing files are skipped unless --force.

Then applies a stack PROFILE: probes the repo, stamps the profile's gate
module, and GENERATES this repo's real quality blocks, gate wiring, and prompt
overlay. With no --profile, the profile whose detection rules match is applied;
an ambiguous match stops and asks. --doctor re-probes and reports without
writing anything, which is what to run after the repo's layout changes.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_install_profile.py -v`
Expected: PASS — 9 passed. (`--doctor` gets its own test in Task 17.)

- [ ] **Step 6: Commit**

```bash
git add tests/test_install_profile.py .claude/skills/sssf/scripts/install.py
git commit -m "feat(install): apply a stack profile and report what it wired"
```

---

## Task 17: `install.py --doctor`

**Files:**
- Modify: `.claude/skills/sssf/scripts/install.py` (only if Task 16's implementation needs correcting)
- Test: `tests/test_install_profile.py` (append)

**Scene:** `--doctor` is the re-probe. A repo restructures, a frontend moves, a test project is added — and the generated blocks silently keep running the old commands. Doctor answers "what would an install wire today?" without touching anything, which makes it safe to run on a repo you do not own.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_install_profile.py`:

```python
def test_doctor_writes_nothing_at_all(tmp_path):
    dotnet_svelte_repo(tmp_path)
    before = sorted(p.relative_to(tmp_path).as_posix()
                    for p in tmp_path.rglob("*") if p.is_file())

    result = _install(tmp_path, "--doctor")

    after = sorted(p.relative_to(tmp_path).as_posix()
                   for p in tmp_path.rglob("*") if p.is_file())
    assert result.returncode == 0, result.stderr
    assert before == after


def test_doctor_reports_the_detection(tmp_path):
    dotnet_svelte_repo(tmp_path, frontends=["apps/web"])
    result = _install(tmp_path, "--doctor")
    assert "Fixture.sln" in result.stdout
    assert "apps/web" in result.stdout
    assert "integration-tests" in result.stdout
    assert "nothing was written" in result.stdout


def test_doctor_reports_drift_after_a_restructure(tmp_path):
    """Install, move a frontend, then ask doctor what it would wire now."""
    dotnet_svelte_repo(tmp_path, frontends=["apps/web"])
    _install(tmp_path)
    assert "apps/web" in _generated(tmp_path)["blocks"].read_text()

    (tmp_path / "apps" / "web").rename(tmp_path / "frontend")
    result = _install(tmp_path, "--doctor")

    assert "frontend" in result.stdout
    # the stale generated file is untouched, which is the drift being reported
    assert "apps/web" in _generated(tmp_path)["blocks"].read_text()


def test_doctor_on_an_unrecognised_repo_says_so_and_succeeds(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    result = _install(tmp_path, "--doctor")
    assert result.returncode == 0
    assert "no profile" in result.stdout.lower()


def test_doctor_output_is_ascii(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path, "--doctor").stdout.encode("ascii")
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_install_profile.py -v`
Expected: PASS — 14 passed. Task 16's `main` already implements `--doctor`; these tests exist to hold it to the "writes nothing" contract, which is the only property that makes doctor safe to point at a repository you do not own.

If any fail, the most likely cause is `stamp_profile_gates` or `ensure_gitignore` running on the doctor path. Both must be inside `if not args.doctor:`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_install_profile.py
git commit -m "test(install): doctor re-probes and writes nothing"
```

---

## Task 18: Documentation

**Files:**
- Modify: `.claude/skills/sssf/references/config.md`
- Modify: `.claude/skills/sssf/cookbooks/install.md`
- Modify: `.claude/skills/sssf/SKILL.md`
- Modify: `README.md`
- Test: `tests/test_docs_accurate.py`

**Scene:** SSSF's docs are part of the product — the cookbooks are what an agent reads to operate the factory. Three shipped claims are now false: that `quality.py` ships placeholders you must edit by hand, that the test phase is theatre until you do, and that `install.py` takes only `--force`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_accurate.py`:

```python
"""Documentation claims that code can check.

Prose drifts silently. These are the handful of claims where drift would send
an operator to a file that no longer works the way the sentence says.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "sssf"


def _text(*parts) -> str:
    return (SKILL.joinpath(*parts)).read_text(encoding="utf-8")


def test_the_install_cookbook_documents_every_flag():
    text = _text("cookbooks", "install.md")
    for flag in ("--profile", "--no-profile", "--doctor", "--force"):
        assert flag in text, flag


def test_the_config_reference_documents_doc_policy():
    text = _text("references", "config.md")
    assert "doc_policy" in text
    assert "require" in text


def test_the_config_reference_documents_the_block_tiers():
    text = _text("references", "config.md")
    assert "quality_blocks.py" in text
    assert "tier" in text


def test_no_document_still_tells_operators_to_edit_quality_py_by_hand():
    """The generated file is quality_blocks.py; quality.py is the engine now."""
    for document in ("README.md",):
        text = (ROOT / document).read_text(encoding="utf-8")
        assert "replace this echo" not in text
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "quality_blocks.py" in readme


def test_the_skill_describes_profiles():
    text = _text("SKILL.md")
    assert "profile" in text.lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_docs_accurate.py -v`
Expected: FAIL — none of these strings are in the docs yet.

- [ ] **Step 3: Update `cookbooks/install.md`**

Add a section after the existing install instructions:

```markdown
## Stack profiles

A bare install stamps a factory whose quality blocks are `echo` placeholders.
A profile replaces them with this repo's real commands, discovered by probing
the tree.

```bash
uv run <skill>/scripts/install.py                       # auto-detect
uv run <skill>/scripts/install.py --profile dotnet-svelte
uv run <skill>/scripts/install.py --no-profile          # stamp only, wire nothing
uv run <skill>/scripts/install.py --doctor              # re-probe, write nothing
```

With no flag, every profile's detection rules are evaluated. Exactly one match
is applied; none leaves the placeholders in place and says so; more than one
stops and asks for `--profile`, because wiring a repo to the wrong stack
produces a factory whose checks all pass without running anything real.

Applying a profile writes three files and stamps one:

| Path | What it is |
|---|---|
| `adws/adw_modules/quality_blocks.py` | generated: this repo's commands, each with a `fast` or `full` tier |
| `adws/adw_modules/profile_gates.py` | generated: the stack gates, parameterized with what was found |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | generated: stack guidance, injected into prompts that include `{{profile_overlay}}` |
| `adws/adw_modules/gates_<profile>.py` | stamped: the gate implementations, skipped if it already exists |

All three generated files are plain and editable, and all three are overwritten
by the next install with a profile. Hand edits belong in `quality.py`,
`gates.py`, or the prompt files — none of which an install overwrites without
`--force`.

**`--doctor`** re-probes and prints what an install would wire today, without
writing anything. Run it after a restructure: generated blocks do not notice
that a frontend moved, and a command pointing at a directory that no longer
exists fails in a way that reads like a broken build.

### The `dotnet-svelte` profile

Matches a repo containing both a `*.sln` (or `*.slnx`) and a `package.json`
declaring `@sveltejs/kit`.

It classifies every project in the solution (`xunit` and friends mean a test
project; adding `Testcontainers` makes it an *integration* test project, tagged
`full` so it stays out of bounded fix loops), finds every frontend
independently and reads its `scripts`, and prefers a task-runner recipe over a
raw command wherever the runner declares one. It wires `ef_migration_triad`
always, `env_example_sync` when a frontend has an example env file, and
`sveltekit_csp` when a frontend's `src/hooks.server.ts` declares a policy.
```

- [ ] **Step 4: Update `references/config.md`**

Add these two sections:

```markdown
## `doc_policy` — the documentation contract

Optional, empty by default, and checked by the `doc_policy` gate on every
code-changing phase.

```yaml
doc_policy:
  - when: "apps/api/**/Auth*.cs"
    require: ["docs/AUTH.md"]
  - when: "apps/web/src/**"
    require: ["docs/ARCHITECTURE.md", "docs/FEATURES.md"]
```

A rule fires when a changed file matches `when`; it then requires each
`require` entry to appear in the same change. Both sides are path globs with
the same semantics as `writes:` — `*` stops at a directory separator, `**`
crosses them (and `**/` also matches zero directories, so `**/*.md` covers
`README.md`), a trailing `/` is a directory prefix.

A violation is reported to the agent in the same session, with its context
intact, so the correction is "also update this document" rather than a fresh
run. Keep the list short: a documentation gate that fires on everything gets
switched off wholesale.

## Quality blocks — `quality_blocks.py`

`quality.py` is the engine; the commands live in
`adws/adw_modules/quality_blocks.py` as a list of `QualityCheckSpec`. A profile
generates that file at install time; without one, `quality.py` falls back to
placeholder blocks that exit 0 and say so.

```python
QualityCheckSpec(
    name="check-web", area="frontend", operation="typecheck",
    argv=["npm", "run", "check"],
    cwd="apps/web", tier="fast", timeout_seconds=600,
)
```

- `tier` — `fast` runs inside bounded fix loops (`quality.run_tests`); `full`
  adds the slow, service-dependent blocks and runs only in final verification
  (`quality.run_quality`). A Testcontainers suite needs Docker up, so paying for
  it on every retry is a real cost, not a theoretical one.
- `cwd` — repo-relative working directory. A monorepo runs the same command in
  several packages; this is how, without a per-package-manager flag table.
- `argv` — a list, never a shell string, and binaries called by bare name so
  they resolve through the operator's own PATH.
```

- [ ] **Step 5: Update `SKILL.md`**

In the section that describes what an install produces, add:

```markdown
## Stack profiles

`install.py` probes the repo and generates its quality blocks, gate wiring, and
a prompt overlay from what it finds — so a fresh install runs the repo's real
commands instead of placeholders. `--profile <name>` picks one, `--no-profile`
skips the step, `--doctor` re-probes and reports without writing. Profiles live
in `templates/profiles/<name>/` and adding one touches no core module.

A profile may only encode **stack** facts (EF Core writes three files per
migration), **discovered** facts (where the solution is), and **configured**
facts (`doc_policy` in the roster). Never a path from one repository.
```

- [ ] **Step 6: Update `README.md`**

Replace the first row of the "Where it can still fail" table:

```markdown
| The test phase reports green on a fresh install | Only without a profile. `install.py` probes the repo and generates `quality_blocks.py` with its real commands; with no matching profile those blocks stay `echo` placeholders that exit 0 | Run `install.py --doctor` to see what was wired. If no profile matched, write the specs into `adws/adw_modules/quality_blocks.py` by hand before trusting `adw_build_test`, `adw_plan_build_test`, or `adw_simple_sdlc` |
```

and in the "what you customize" table replace the `quality.py` row:

```markdown
| Your real commands | `adws/adw_modules/quality_blocks.py` | Generated from a profile at install time. Plain Python: open it and correct anything the probe got wrong |
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `uv run pytest tests/test_docs_accurate.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 8: Commit**

```bash
git add tests/test_docs_accurate.py .claude/skills/sssf/references/config.md .claude/skills/sssf/cookbooks/install.md .claude/skills/sssf/SKILL.md README.md
git commit -m "docs: profiles, doc_policy, and the generated quality blocks"
```

---

## Task 19: Live verification

**Files:** none modified. This task produces evidence and appends it to the spec.

**Scene:** Part A shipped with 85 green tests and a bug that broke every single run, because every test asserted on the shape of an argv list and none on how the CLI parsed it. The lesson generalizes: unit tests prove the generator emits what we told it to emit, not that the commands it emits actually run. So the profile gets probed against a real repository of the stack, and then exercised against a disposable copy of one.

`C:\Source\Repos\codec-chat` must not be modified. Step 1 is read-only by construction (`--doctor` writes nothing, proven by a test); Step 2 works on a throwaway clone.

- [ ] **Step 1: Doctor against the real reference repo**

```bash
cd /c/Source/Repos/codec-chat
uv run /c/Source/Repos/super-simple-software-factory/.claude/skills/sssf/scripts/install.py --doctor
git status --porcelain
```

Expected: a report naming `Codec.sln`, five projects with `Codec.Api.Tests` as `unit-tests` and `Codec.Api.IntegrationTests` as `integration-tests`, both frontends (`apps/web` and `apps/admin`, npm), `just` as the task runner, and the convention files `CLAUDE.md`, `AGENTS.md`, `.github/instructions/`. The `git status --porcelain` must print **nothing**.

Record any mismatch between the report and the repo rather than adjusting the report to match: a misclassification here is a detection bug, and `--doctor` exists precisely so it is visible before anything is wired.

- [ ] **Step 2: Full install into a disposable clone**

```bash
SCRATCH=$(mktemp -d)
git clone --depth 1 /c/Source/Repos/codec-chat "$SCRATCH/codec-chat"
cd "$SCRATCH/codec-chat"
uv run /c/Source/Repos/super-simple-software-factory/.claude/skills/sssf/scripts/install.py
```

Expected: the same detection, then `quality blocks wired: N` with real commands
(`just test-api`, `just check-web`, and so on, since this repo has a justfile
declaring them), `gates wired: ef_migration_triad, ...`, and four new files.

- [ ] **Step 3: Prove the generated blocks actually execute**

```bash
cd "$SCRATCH/codec-chat"
uv run adws/adw_quality.py "verify the generated blocks run"
uv run adws/adw_trace.py events --type tool_call
```

Expected: a `tool_call` row per block, each carrying the real command and a real
exit code. Blocks may legitimately FAIL here (a fresh clone has no `node_modules`
and no database) — a failure is fine and a `PLACEHOLDER` command is not. What
this step proves is that the argv the generator wrote is an argv the operating
system can launch, which is exactly the class of bug unit tests missed in Part A.

Record the block names, commands and exit codes.

- [ ] **Step 4: Confirm the reference repo is still untouched**

```bash
git -C /c/Source/Repos/codec-chat status --porcelain
```

Expected: no output.

- [ ] **Step 5: Append the evidence to the spec**

Add a `## 8b. Verified (Part B)` section to
`docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md` with a
table of the blocks that were wired, their commands and exit codes, the gates
wired, anything reported unresolved, and — if the live run found a defect the
unit tests missed — what it was and what test now encodes it.

- [ ] **Step 6: Write the worked example**

Spec §7 asks for a worked example that walks one install end to end. Append it
to `.claude/skills/sssf/cookbooks/install.md`, under
`## Worked example: an ASP.NET Core + SvelteKit monorepo`, using the **real**
output captured in Steps 1–3 rather than invented output — a worked example
whose numbers nobody ever saw is worth less than none.

It must be documentation, not configuration: it is the one place in this change
allowed to name a specific repository, and no shipped file may reference it.
State that up front in the section's first line, so the next person reading
`templates/profiles/` does not take the example as a licence.

Structure it as: the command, the abridged report (detection, blocks, gates,
unresolved), a sentence on which blocks came from recipes and which were
composed, and what `--doctor` prints after a frontend is moved.

- [ ] **Step 7: Clean up and commit**

```bash
rm -rf "$SCRATCH"
git add docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md .claude/skills/sssf/cookbooks/install.md
git commit -m "docs: record Part B live verification and the worked example"
```

---

## Done criteria

- [ ] `uv run pytest tests/ -v` passes with 0 failures (~225 tests: the 85 that
      existed before this plan, plus the per-file counts each task states).
- [ ] `install.py` into a fixture repo produces a `quality_blocks.py` containing
      no `PLACEHOLDER`, and `run_tests` runs only its `fast` blocks.
- [ ] `install.py --doctor` against `codec-chat` reports its real layout and
      leaves `git status --porcelain` empty.
- [ ] `grep -rnE "codec|Codec|apps/web|apps/admin" .claude/skills/sssf/templates/profiles/`
      returns nothing outside comments — no repository-specific path in profile source.
- [ ] `grep -rn "replace this echo\|placeholder commands that exit 0" README.md .claude/skills/sssf/`
      returns nothing.
- [ ] Every `AgentCall(output_type=BuildOutput, ...)` in the shipped ADWs runs
      `gates.doc_policy` and `*gates.profile_gates()` (enforced by
      `tests/test_gate_wiring.py`).
- [ ] No file in `C:\Source\Repos\codec-chat` is modified.

## Deferred, deliberately

Recorded so they are not lost, and so a reviewer does not read their absence as an oversight.

- **Part C is not in this plan.** Branch per run, `git_helper.default_branch/create_run_branch/push_branch/open_pr`, and `adw_plan_build_test_pr.py` are spec §6 and get their own plan. `detect.default_branch` lands here because the profile report needs it; nothing consumes it yet.

- **A profile cannot add an ADW.** The mechanism generates blocks, gate wiring, and a prompt overlay, but a profile that wants a stack-specific workflow has no way to ship one. Nothing needs it yet, and a generated ADW would be the first generated file an operator is likely to want to edit heavily — which is exactly the file you do not want regenerated out from under them.

- **The four deferred items from the Part A plan still stand**, unchanged: the cp1252 console crash that leaves a trace row stuck at `running`; prompts riding on argv against a ~32KB Windows ceiling (now slightly larger, since the overlay adds to the system prompt — worth measuring during Task 19); `agent_pi`'s `tools: []` inversion; and the trace recording a bare command while executing a resolved path.

- **Detection does not read `dotnet sln list`, `just --evaluate`, or `package.json` workspaces.** A repo whose frontends are declared only as npm workspaces and whose solution is assembled by a generator would be under-detected. `--doctor` makes that visible, and the generated file is editable Python — which is the intended escape hatch for anything a probe cannot see.
