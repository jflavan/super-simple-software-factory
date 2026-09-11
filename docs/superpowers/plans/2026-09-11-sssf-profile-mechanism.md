# SSSF Profile Mechanism + `dotnet-svelte` Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `install.py` probe a repository, discover its real build and test commands, and stamp a factory wired to them — so a fresh install of SSSF into any ASP.NET Core + EF Core + SvelteKit repo runs real checks instead of `echo` placeholders.

**Architecture:** A **framework module** owns everything about one technology: how to find it, what commands it implies, which gates it brings, and what an agent should know about it. A **profile** is a YAML file naming the frameworks a stack is made of. A generic driver composes them, and generation writes three plain files into the target repo (`quality_blocks.py`, `profile_gates.py`, `profile_overlay.md`). Core modules load those when present and fall back to shipped defaults when absent, so an un-profiled install behaves exactly as it does today.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, pytest. Target stack under test: ASP.NET Core / EF Core (`.sln`, `.csproj`, xunit, Testcontainers) and SvelteKit 5 (`package.json`, `@sveltejs/kit`), optionally driven by a `justfile`.

**Spec:** `docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md` §5 (Part B), plus the §7 items Part B introduces.

---

## Ground rules for every task

**1. Check your branch before you touch anything.** Run `git rev-parse --abbrev-ref HEAD` first. If it prints `HEAD`, you are detached and MUST stop and report it — a previous run of this workflow lost three commits that way.

**2. The design rule, restated because it is the whole point.** Nothing you write under `templates/profiles/` may name a path specific to one repository. `apps/web`, `Codec.sln`, and `test-api` are values DETECTION produces at install time; they must never appear as literals in profile or framework source. The only places such strings may appear are: generated files inside a target repo, test fixtures, and documentation examples. A reviewer will grep for them.

**3. Every commit ends with this trailer block**, separated from the message body by a blank line:

```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_019yQfXSXQtrrHu6ooNpecG6
```

**4. Do not modify anything under `C:\Source\Repos\codec-chat`.** It is a read-only reference repository. Task 21 probes it; nothing writes to it.

**5. Run tests with `uv run pytest`** from the repo root (`C:\Source\Repos\super-simple-software-factory`). The suite currently passes 85 tests; each task states how many its own file adds.

---

## Designed to grow: frameworks compose, profiles are data

The first version of this plan made `dotnet-svelte` a self-contained package: one `detect.py`, one `generate.py`, one gate module. That works exactly once. Adding ASP.NET Core + Angular would copy solution parsing, project classification, lockfile detection, task-runner probing, default-branch lookup, convention scanning, and the entire EF Core gate — roughly **70% of the code, duplicated on day one** — and would then drift from the original the first time either is fixed.

Worse, whole-stack profiles multiply: backends × frontends. Angular is not a row in a list, it is a **column in a matrix**. A flat profile list means writing the Angular half again for every backend it is ever paired with.

So the unit of reuse is the **framework**, not the profile.

```
framework module  = everything about ONE technology
profile           = a YAML file naming which frameworks a stack is made of
composite driver  = generic; merges the frameworks a profile declares
```

Each framework module exposes the same eight names, checked at import:

| Name | What it does |
|---|---|
| `NAME` | the framework's id, e.g. `"dotnet"` |
| `matches(root)` | is this technology present in this repo? |
| `detect(root)` | probe it, return a typed `FrameworkFacts` subclass |
| `blocks(facts, repo)` | the quality blocks this technology implies |
| `describe(facts)` | report lines for `--doctor` |
| `gate_wiring(facts)` | which gates to wire, with which discovered arguments |
| `GATE_MODULE` | the gate file to stamp, or `""` |
| `OVERLAY` | the prompt fragment an agent should read about this technology, or `""` |

**What adding Angular then costs.** Three new files, one line in the framework
registry, and a four-line YAML file:

```
profiles/frameworks/angular.py          # marker @angular/core, its blocks, its gates, its describe
profiles/gates/gates_angular.py         # environment.ts file-replacement gate
profiles/prompts/angular.md             # standalone components, signals, the injector
profiles/dotnet_angular/profile.yaml    # name + frameworks: [dotnet, angular]
```

Nothing about .NET is written twice. `probes.node_packages(root, marker)` finds Angular workspaces exactly as it finds SvelteKit ones, and `emit.script_blocks(...)` turns their `package.json` scripts into blocks with the same code. A `node-angular` profile later is one more YAML file.

**Two things this deliberately does not try to be.** A framework may not depend on another framework — `sveltekit.py` never imports `dotnet.py`, it calls shared helpers in `probes.py` and `emit.py`. And the driver does not merge conflicting opinions: if two frameworks emit a block with the same name, generation fails loudly rather than picking one, because a silently dropped block is a check that stopped running.

**Where the abstraction is still a guess.** The framework interface is extracted from two implementations, which is the minimum that justifies extracting anything — but Angular is not one of them. Angular enumerates build targets from `angular.json`, not only from `package.json` scripts, so its `blocks()` may need to do more than call `emit.script_blocks`. The interface allows that (each framework owns its own `blocks`), but it has not been proven. **Task 19 is the acceptance test for exactly this**: it builds a third framework inside the test suite from the shared pieces and asserts that detection, blocks, gates, and the overlay all compose without touching a single shared file.

---

## Deliberate deviations from the spec

Five, each a refinement rather than a reduction. Recorded here so a spec reviewer does not flag them as drift.

1. **§B0 describes a profile as a directory of Python (`detect.py`, `generate.py`, `gates/`, `prompts/`). This plan makes a profile a YAML file and moves the Python into framework modules.** The spec's shape is right for one profile and duplicates itself for the second; see the section above. The spec's *intent* — "a future `node-only` or `python-uv` profile is purely additive and touches no core module" — is strengthened, not weakened: such a profile is now additive at the framework level too.

2. **§B2 says "writes a concrete `quality.py`". This plan generates `quality_blocks.py` instead.** `quality.py` holds the engine — `_run`, `as_envelope`, artifact capture, tracer events. Generating the whole file would copy that engine into the generator and fork it on the first change. Instead the engine stays hand-written and generic, the generated file holds nothing but data (`BLOCKS: list[QualityCheckSpec]`), and regeneration overwrites a file containing zero hand-written code. Hard rule 8 still holds: the command is code, written down, in the repo.

3. **§B4 lists `doc_policy` among the profile's gates. This plan puts it in core `gates.py`.** The gate contains no .NET and no Svelte: it reads a YAML block and compares changed paths. By the design rule in spec §3, a gate with no stack facts in it belongs to no stack. Any repo on any stack can declare a `doc_policy:` block.

4. **§B1 says "enumerate solution projects via `dotnet sln list`". This plan parses the solution file directly.** `dotnet sln list` prints what the file already says, but requires the .NET SDK on PATH during install and costs a subprocess per probe. Parsing `.sln` (a documented line format) and `.slnx` (XML) works offline, is deterministic, and is testable against fixture trees with no toolchain installed.

5. **`QualityCheckSpec` gains a `cwd` field rather than the spec's `npm --prefix <dir>` form.** A `--prefix`-style flag needs a different spelling per package manager (npm `--prefix`, pnpm `--dir`, yarn `--cwd`, bun none), so that table grows a row per manager and is wrong for the next one. A working directory is what all of them mean, and it costs one line in `_run`.

---

## File structure

**New, installer-side (read and executed by `install.py`; never stamped into a target repo):**

| File | Responsibility |
|---|---|
| `templates/profiles/__init__.py` | Makes `profiles` a package. |
| `templates/profiles/facts.py` | The typed vocabulary: `ProfileFacts`, `FrameworkFacts`, `DotnetProject`, `Frontend`, `QualityBlock`, `GateWiring`, `GenerationReport`. |
| `templates/profiles/probes.py` | Stack-agnostic repo probes: tree walk, task runner, default branch, convention files, node package discovery, package manager. |
| `templates/profiles/emit.py` | Stack-agnostic emitters: recipe preference, unique labels, spec rendering, module rendering, file writing, npm-script blocks. |
| `templates/profiles/frameworks/__init__.py` | The framework registry and its interface check. |
| `templates/profiles/frameworks/dotnet.py` | Everything about .NET: solution parsing, project classification, `dotnet` blocks, the EF gate wiring, its overlay. |
| `templates/profiles/frameworks/sveltekit.py` | Everything about SvelteKit: marker, CSP probe, frontend blocks, its two gates, its overlay. |
| `templates/profiles/composite.py` | The generic profile driver: `matches`, `detect`, `generate`, `describe` over a declared framework list. |
| `templates/profiles/registry.py` | Profile discovery from `*/profile.yaml`, lookup by name, auto-detection. |
| `templates/profiles/dotnet_svelte/profile.yaml` | Four lines: a name, a description, and `frameworks: [dotnet, sveltekit]`. |
| `templates/profiles/prompts/{dotnet,sveltekit}.md` | Per-framework prompt fragments. |

**New, stamped into the target repo by the installer (one file per framework that declares a `GATE_MODULE`):**

| Source | Stamped to |
|---|---|
| `templates/profiles/gates/gates_dotnet.py` | `adws/adw_modules/gates_dotnet.py` |
| `templates/profiles/gates/gates_sveltekit.py` | `adws/adw_modules/gates_sveltekit.py` |

**New, generated into the target repo (plain, editable, overwritten on regeneration):**

| File | Responsibility |
|---|---|
| `adws/adw_modules/quality_blocks.py` | `BLOCKS: list[QualityCheckSpec]` — this repo's real commands, with tiers. |
| `adws/adw_modules/profile_gates.py` | `PROFILE_GATES: list[Callable]` — the stack gates, parameterized with discovered facts. |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | Stack guidance plus the convention files that were actually found. |

**Modified, core (shipped templates):**

| File | Change |
|---|---|
| `templates/adws/adw_modules/data_types.py` | `QualityCheckSpec` gains `tier` + `cwd`; new `DocPolicyRule`; `SSSFConfig` gains `doc_policy`. |
| `templates/adws/adw_modules/utils.py` | `glob_to_regex`, `path_matches`, `repo_relative`, `claimed_files`, `read_text`. |
| `templates/adws/adw_modules/permissions.py` | Uses `utils.path_matches`; its private `_glob`/`_matches` are removed. |
| `templates/adws/adw_modules/quality.py` | Blocks become data; `blocks()` loader; `run_tests` = fast tier, `run_quality` = all tiers; `_run` honours `spec.cwd`. |
| `templates/adws/adw_modules/gates.py` | New `doc_policy` gate and `profile_gates()` loader. |
| `templates/adws/adw_modules/agents.py` | `execute()` adds the `profile_overlay` prompt variable. |
| `templates/adws/adw_*.py` (7 files) | Build-phase gate lists gain `gates.doc_policy` and `*gates.profile_gates()`. |
| `templates/prompt_engineering/builder/system.md` | Toolchain-agnostic wording + `{{profile_overlay}}` placeholder. |
| `templates/sssf.config.yaml` | Commented `doc_policy:` block. |
| `scripts/install.py` | `--profile`, `--no-profile`, `--doctor`; profile application; the report. |
| `references/config.md`, `cookbooks/install.md`, `SKILL.md`, `README.md` | Documentation, including how to add a framework. |

**New tests:** `tests/profile_fixtures.py` plus eleven `tests/test_*.py` files named per task.

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

import pytest

from adw_modules import quality
from adw_modules.data_types import QualityCheckResult, QualityCheckSpec


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


def _passing(spec, ran):
    ran.append(spec.name)
    return QualityCheckResult(name=spec.name, area=spec.area, operation=spec.operation,
                              command=" ".join(spec.argv), returncode=0, passed=True,
                              duration_seconds=0.0, output_artifact="/dev/null")


def _failing(spec):
    return QualityCheckResult(name=spec.name, area=spec.area, operation=spec.operation,
                              command=" ".join(spec.argv), returncode=1, passed=False,
                              duration_seconds=0.0, output_artifact="/dev/null",
                              output_tail="boom")


def test_spec_defaults_to_the_fast_tier_at_the_repo_root():
    spec = QualityCheckSpec(name="x", area="backend", operation="build", argv=["true"])
    assert spec.tier == "fast"
    assert spec.cwd == "."


def test_spec_rejects_an_unknown_tier():
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

In `data_types.py`, beside the existing `QualityArea` / `QualityOperation` aliases, add:

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
    # same command in several packages, and every package manager spells its
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
    def raise_unrelated():
        raise ModuleNotFoundError("No module named 'nonexistent_dependency'",
                                  name="nonexistent_dependency")

    monkeypatch.setattr(quality, "_import_generated_blocks", raise_unrelated)
    with pytest.raises(ModuleNotFoundError):
        quality.blocks()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_quality_blocks.py -v`
Expected: FAIL — `AttributeError: module 'adw_modules.quality' has no attribute '_import_generated_blocks'`.

- [ ] **Step 3: Replace the blocks section**

In `quality.py`, delete `_placeholder`, the four block functions (`test`, `lint`, `typecheck`, `build`), and the bodies of `run_tests` and `run_quality`. Put this in their place, keeping `as_envelope` exactly as it is between `_run` and the new `run_tests`:

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
║  a list of QualityCheckSpec. Three rules when you do:                        ║
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

## Task 3: One path glob for the whole system, and the `doc_policy` gate

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/utils.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/permissions.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/data_types.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/gates.py`
- Modify: `.claude/skills/sssf/templates/sssf.config.yaml`
- Test: `tests/test_gates_doc_policy.py`

**Scene:** `permissions.py` already owns a careful glob translator — `*` deliberately stops at `/` so `adws/adw_*.py` cannot widen into `adws/adw_data/**/*.py`. `doc_policy` needs exactly those semantics on exactly the same kind of path, and so will every stack gate in Tasks 12 and 13, so the translator moves to `utils` rather than being written four times.

One latent bug comes with it: `**/*.md` currently compiles to `.*/[^/]*\.md`, which requires at least one directory and so does not match `README.md` at the repo root. The documenter's `writes:` list papers over that by also listing `*.md`; a `doc_policy` rule written by an operator will not.

This task lands before any profile code because every gate written later depends on `repo_relative`, `claimed_files`, and `read_text`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gates_doc_policy.py`:

```python
"""doc_policy: a change here requires a doc there, declared in YAML."""

from types import SimpleNamespace

import pytest

from adw_modules import gates
from adw_modules.data_types import BuildOutput, DocPolicyRule, SSSFConfig
from adw_modules.utils import claimed_files, path_matches, repo_relative


def _run(tmp_path, rules=()):
    return SimpleNamespace(repo_root=str(tmp_path), cfg=SSSFConfig(doc_policy=list(rules)))


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


# ── the shared path helpers ──────────────────────────────────────────────────

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


def test_repo_relative_strips_an_absolute_root():
    assert repo_relative("/repo/apps/a.cs", "/repo") == "apps/a.cs"
    assert repo_relative("./apps/a.cs", "/repo") == "apps/a.cs"
    assert repo_relative("apps/a.cs", "/repo") == "apps/a.cs"


def test_claimed_files_normalises_every_entry(tmp_path):
    envelope = _envelope([str(tmp_path / "a.cs"), "./b.cs", "c\\d.cs"])
    assert claimed_files(envelope, _run(tmp_path)) == ["a.cs", "b.cs", "c/d.cs"]


def test_claimed_files_on_an_envelope_without_the_field_is_empty(tmp_path):
    assert claimed_files(SimpleNamespace(), _run(tmp_path)) == []


# ── the gate ─────────────────────────────────────────────────────────────────

def test_no_rules_means_no_checks(tmp_path):
    report = gates.doc_policy(_envelope(["src/a.cs"]), _run(tmp_path))
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

- [ ] **Step 3: Add the path helpers to `utils`**

Add to `.claude/skills/sssf/templates/adws/adw_modules/utils.py`. Check the imports at the top of that file first and add whichever of `re`, `functools.lru_cache`, and `pathlib.Path` are not already there:

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


def claimed_files(envelope, run) -> list[str]:
    """Every path an envelope CLAIMS to have changed, repo-relative.

    Named for its epistemics, and deliberately not `changed_files` — that name
    belongs to git_helper, which reports what git OBSERVED. A gate that mixes
    the two up is checking the agent's homework against its own answer sheet.
    """
    return [repo_relative(f, run.repo_root)
            for f in getattr(envelope, "changed_files", [])]


def read_text(path) -> str:
    """File text, or empty when it is gone.

    A gate reads files the change touched, and `changed_files` includes
    DELETIONS — so "the file is not there" is an ordinary case, not an error.
    """
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""
```

- [ ] **Step 4: Point `permissions.py` at the shared translator**

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

In `gates.py`, add `from .utils import claimed_files, path_matches` to the imports and append:

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
    changed = claimed_files(envelope, run)
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

- [ ] **Step 8: Run the whole suite**

Run: `uv run pytest tests/ -v`
Expected: PASS — 0 failures. The pre-existing permissions tests must still pass; if any fail, the glob move changed behaviour and the regex is wrong.

- [ ] **Step 9: Commit**

```bash
git add tests/test_gates_doc_policy.py .claude/skills/sssf/templates/adws/adw_modules/utils.py .claude/skills/sssf/templates/adws/adw_modules/permissions.py .claude/skills/sssf/templates/adws/adw_modules/data_types.py .claude/skills/sssf/templates/adws/adw_modules/gates.py .claude/skills/sssf/templates/sssf.config.yaml
git commit -m "feat(gates): config-driven doc_policy on one shared path glob"
```

---

## Task 4: The shared vocabulary

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/__init__.py`
- Create: `.claude/skills/sssf/templates/profiles/facts.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_profile_facts.py`

**Scene:** `ProfileFacts` is the handoff between detection and generation. Repo-level facts — task runner, default branch, convention files — live on it directly, because every stack has them. Anything a *framework* learned lives in a `FrameworkFacts` subclass, keyed by framework name. Pydantic keeps subclass instances intact inside a `dict[str, FrameworkFacts]` (it does not revalidate model instances by default), so `facts.of("dotnet")` hands back the real `DotnetFacts` with its own fields and methods.

- [ ] **Step 1: Put the templates directory on `sys.path` for tests**

In `tests/conftest.py`, below the existing `TEMPLATES_ADWS` block, add:

```python
TEMPLATES = TEMPLATES_ADWS.parent          # .../skills/sssf/templates

if str(TEMPLATES) not in sys.path:
    sys.path.insert(0, str(TEMPLATES))
```

This makes `import profiles.facts` work in tests exactly as it will inside `install.py`, which performs the same insert.

- [ ] **Step 2: Write the failing test**

Create `tests/test_profile_facts.py`:

```python
"""The vocabulary detection and generation share."""

import pytest
from pydantic import BaseModel, ValidationError

from profiles.facts import (Frontend, FrameworkFacts, GateWiring, GenerationReport,
                            ProfileFacts, QualityBlock)


class _Fake(FrameworkFacts):
    """Stands in for a real framework's facts, so this file imports none."""
    thing: str = ""
    items: list[str] = []

    def loud(self) -> str:
        return self.thing.upper()


def test_repo_level_facts_default_to_an_empty_repo():
    facts = ProfileFacts(profile="x", repo_root=".")
    assert facts.task_runner == ""
    assert facts.recipes == []
    assert facts.default_branch == "main"
    assert facts.conventions == []
    assert facts.frameworks == {}


def test_a_framework_section_keeps_its_own_type_fields_and_methods():
    """The load-bearing property: pydantic must not downcast to the base."""
    facts = ProfileFacts(profile="x", repo_root=".",
                         frameworks={"fake": _Fake(thing="sln", items=["a"])})
    section = facts.of("fake")
    assert isinstance(section, _Fake)
    assert section.thing == "sln"
    assert section.loud() == "SLN"


def test_a_framework_section_may_be_filled_after_construction():
    """Detection fills the dict one framework at a time."""
    facts = ProfileFacts(profile="x", repo_root=".")
    facts.frameworks["fake"] = _Fake(thing="later")
    assert facts.of("fake").thing == "later"


def test_asking_for_a_framework_the_profile_does_not_declare_is_an_error():
    facts = ProfileFacts(profile="x", repo_root=".")
    with pytest.raises(KeyError):
        facts.of("angular")


def test_profile_facts_requires_its_identity():
    with pytest.raises(ValidationError):
        ProfileFacts(repo_root=".")


def test_a_frontend_knows_which_scripts_it_has():
    frontend = Frontend(directory="apps/web", package_manager="npm",
                        scripts=["check", "test", "build"])
    assert frontend.has("check")
    assert not frontend.has("lint")


def test_a_quality_block_defaults_to_fast_at_the_repo_root():
    block = QualityBlock(name="t", area="backend", operation="build", argv=["a"])
    assert block.tier == "fast"
    assert block.cwd == "."


def test_gate_wiring_carries_its_module_name_and_call():
    wiring = GateWiring(module="gates_dotnet", name="ef_migration_triad",
                        call="ef_migration_triad")
    assert wiring.module == "gates_dotnet"


def test_a_generation_report_lists_what_it_could_not_resolve():
    report = GenerationReport(profile="dotnet-svelte",
                              unresolved=["no frontend declares a `test` script"])
    assert report.files == []
    assert report.blocks == []
    assert report.unresolved == ["no frontend declares a `test` script"]


def test_framework_facts_is_a_plain_model_any_framework_can_extend():
    assert issubclass(FrameworkFacts, BaseModel)


def test_the_block_vocabulary_matches_the_stamped_runtime():
    """A generator must not be able to emit a value the runtime will reject.

    `facts.py` is installer-side and `data_types.py` is stamped into the target
    repo, so the two cannot share a definition without coupling the installer to
    the runtime tree. They can be pinned to each other, which is what this does:
    the day someone adds an operation to one and not the other, a generated
    block becomes a pydantic error inside an ADW run instead of here.
    """
    from typing import get_args

    from adw_modules.data_types import QualityOperation as RuntimeOperation
    from adw_modules.data_types import QualityTier as RuntimeTier
    from profiles.facts import QualityOperation, QualityTier

    assert set(get_args(QualityOperation)) == set(get_args(RuntimeOperation))
    assert set(get_args(QualityTier)) == set(get_args(RuntimeTier))
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

Nothing here knows about any particular technology, let alone any particular
repository. Repo-level facts sit on ProfileFacts because every stack has them;
anything a framework learned lives in its own FrameworkFacts subclass under
`frameworks`.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field


class FrameworkFacts(BaseModel):
    """Base for whatever ONE framework learned about this repo.

    Each framework module defines its own subclass and is the only code that
    reads it. They are kept in ProfileFacts.frameworks as instances of this
    base type, which is safe because pydantic does not revalidate model
    instances: a DotnetFacts goes in and a DotnetFacts comes back out, fields
    and methods intact.
    """


class Frontend(BaseModel):
    """One JavaScript package: where it is, how to run it, what it can do.

    Shared by every framework that lives in a package.json — SvelteKit today,
    Angular or React tomorrow.

    Deliberately generic: this is exactly what `probes.node_packages` can learn
    from a package.json and a lockfile, and nothing more. Anything only one
    framework cares about belongs in that framework's own FrameworkFacts
    subclass, not as an empty slot every other framework carries.
    """

    directory: str                  # repo-relative, forward slashes; "." for the root
    package_manager: str = "npm"    # npm | pnpm | yarn | bun, from the lockfile
    scripts: list[str] = Field(default_factory=list)   # keys of package.json "scripts"
    env_example: str = ""           # the .env.example that governs it, if one exists

    def has(self, script: str) -> bool:
        return script in self.scripts


class ProfileFacts(BaseModel):
    """Everything a probe learned about one repository."""

    profile: str
    repo_root: str
    task_runner: str = ""                               # "just", or "" if none
    recipes: list[str] = Field(default_factory=list)    # recipe names the runner knows
    default_branch: str = "main"
    conventions: list[str] = Field(default_factory=list)  # CLAUDE.md, AGENTS.md, dirs...
    frameworks: dict[str, FrameworkFacts] = Field(default_factory=dict)

    def of(self, name: str) -> FrameworkFacts:
        """This framework's section. KeyError if the profile never declared it."""
        return self.frameworks[name]


QualityOperation = Literal["lint", "typecheck", "build", "test"]
QualityTier = Literal["fast", "full"]


class QualityBlock(BaseModel):
    """One block the generator decided to emit, plus WHY it chose that command.

    `source` never reaches the generated file — it exists for the install
    report, so "just test-api" and "dotnet test apps/api/X.csproj" are
    distinguishable at a glance from a preference the operator can override.
    """

    name: str
    area: Literal["frontend", "backend"]
    # Typed against the same values QualityCheckSpec accepts. An untyped string
    # here would let a framework emit a bad operation that nothing rejects until
    # the GENERATED file is imported at ADW runtime, a whole install later.
    operation: QualityOperation
    argv: list[str]
    cwd: str = "."
    tier: QualityTier = "fast"
    timeout_seconds: int = 120
    source: str = ""


class GateWiring(BaseModel):
    """One gate a framework wants wired, ready to render into a generated file.

    `call` is a rendered Python expression rather than a callable, because it
    has to survive being written to disk and imported by a different process.
    """

    module: str                     # stamped module it comes from, e.g. "gates_dotnet"
    name: str                       # the symbol to import
    call: str                       # the expression, e.g. "env_example_sync([...], [...])"


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
Expected: PASS — 11 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_profile_facts.py .claude/skills/sssf/templates/profiles/
git commit -m "feat(profiles): the typed vocabulary frameworks share"
```

---

## Task 5: Stack-agnostic repo probes

> **Amended after review (commit `b3d4e8f`).** The code block below is the text
> as planned; the shipped module differs in five ways the review required, and
> `probes.py` is now the authority. `walk()` prunes with `os.walk` instead of
> filtering `rglob` output (measured 4.05s to 0.018s on a 25k-file repo, and an
> install walks four times). `package_manager` stops at the filesystem root as
> well as the repo root, so a call from outside the tree cannot hang.
> `_summary` returns `(recipes, reason)` and `task_runner` returns
> `(name, recipes, source)`, so a runner that RAN and refused is distinguishable
> from one that is absent. `node_packages` takes an optional `unreadable` list,
> because a manifest that does not parse was otherwise invisible even to
> `matches()`. `default_branch` drops the `rev-parse HEAD` rung, which returned
> whatever branch you were standing on in any repo made with `git init`.


**Files:**
- Create: `.claude/skills/sssf/templates/profiles/probes.py`
- Create: `tests/profile_fixtures.py`
- Test: `tests/test_probes.py`

**Scene:** this is the module that stops the second profile being a copy of the first. Finding the task runner, the default branch, the convention files, and every Node package with its lockfile-derived package manager has nothing to do with .NET or Svelte — an Angular profile needs all of it, unchanged. `node_packages(root, marker)` is parameterized by the dependency that identifies the framework, which is the single difference between finding SvelteKit apps and finding Angular ones.

- [ ] **Step 1: Write the fixture builder**

Create `tests/profile_fixtures.py`:

```python
"""Fixture repositories, built in tmp_path.

Every test that exercises detection builds the tree it needs here rather than
pointing at a real repository. A fixture is the only place in this test suite
allowed to use concrete names like `apps/web` — they are this fake repo's
layout, not a profile's.
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

JUSTFILE = """set shell := ["bash", "-c"]

api_dir := "apps/api"

default:
    @just --list

# run the fast suite
test-unit: build-sln
    dotnet test

build-sln:
    dotnet build

check-web dir="apps/web":
    npm --prefix {{dir}} run check
"""


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def sln(root: Path, name: str, project_paths: list[str], folders: list[str] = ()) -> Path:
    """A minimal but real .sln naming the given projects (repo-relative)."""
    lines = ["Microsoft Visual Studio Solution File, Format Version 12.00"]
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


def package(root: Path, directory: str, scripts: dict[str, str],
            marker: str = "@sveltejs/kit", lockfile: str = "package-lock.json") -> Path:
    """A package.json declaring `marker` as a dependency, plus its lockfile."""
    manifest = {"name": Path(directory).name, "scripts": scripts,
                "devDependencies": {marker: "^2.20.0"} if marker else {}}
    path = write(root, f"{directory}/package.json", json.dumps(manifest, indent=2))
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
        package(root, directory, {"check": "svelte-check", "test": "vitest run",
                                  "build": "vite build"})
    if justfile_text:
        write(root, "justfile", justfile_text)
    return root
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_probes.py`:

```python
"""Repo probes: true of every stack, owned by none of them."""

from profile_fixtures import JUSTFILE, dotnet_svelte_repo, package, write

from profiles import probes


# ── node packages ────────────────────────────────────────────────────────────

def test_finds_every_package_declaring_the_marker(tmp_path):
    for directory in ("apps/web", "apps/admin", "packages/kiosk"):
        package(tmp_path, directory, {"build": "vite build"})
    found = probes.node_packages(tmp_path, "@sveltejs/kit")
    assert sorted(f.directory for f in found) == ["apps/admin", "apps/web", "packages/kiosk"]


def test_the_marker_is_what_selects_a_package(tmp_path):
    """The one line that separates finding SvelteKit apps from finding Angular ones."""
    package(tmp_path, "svelte-app", {"build": "vite build"}, marker="@sveltejs/kit")
    package(tmp_path, "ng-app", {"build": "ng build"}, marker="@angular/core")
    assert [f.directory for f in probes.node_packages(tmp_path, "@angular/core")] == ["ng-app"]
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["svelte-app"]


def test_a_package_without_the_marker_is_skipped(tmp_path):
    package(tmp_path, "tools", {"build": "tsc"}, marker="")
    assert probes.node_packages(tmp_path, "@sveltejs/kit") == []


def test_reports_the_scripts_the_package_declares(tmp_path):
    package(tmp_path, "web", {"check": "svelte-check", "lint": "eslint ."})
    found = probes.node_packages(tmp_path, "@sveltejs/kit")[0]
    assert found.has("check") and found.has("lint")
    assert not found.has("test")


def test_package_manager_comes_from_the_lockfile(tmp_path):
    package(tmp_path, "web", {"build": "x"}, lockfile="pnpm-lock.yaml")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].package_manager == "pnpm"


def test_package_manager_is_inherited_from_a_parent_lockfile(tmp_path):
    """A workspace keeps one lockfile at the root; the package below has none."""
    package(tmp_path, "apps/web", {"build": "x"}, lockfile="ignored.txt")
    write(tmp_path, "yarn.lock", "")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].package_manager == "yarn"


def test_package_manager_defaults_to_npm_with_no_lockfile_anywhere(tmp_path):
    package(tmp_path, "web", {"build": "x"}, lockfile="notes.txt")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].package_manager == "npm"


def test_a_malformed_package_json_is_skipped_not_fatal(tmp_path):
    package(tmp_path, "web", {"build": "x"})
    write(tmp_path, "broken/package.json", "{ this is not json")
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["web"]


def test_an_env_example_beside_a_package_is_recorded(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_API_URL=\n")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].env_example == \
        "apps/web/.env.example"


def test_vendored_directories_are_never_walked(tmp_path):
    package(tmp_path, "node_modules/vendor", {"build": "x"})
    package(tmp_path, "web", {"build": "x"})
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["web"]


# ── task runner ──────────────────────────────────────────────────────────────

def test_recipes_are_parsed_from_a_justfile_without_just_installed():
    names = probes.recipes_from_justfile(JUSTFILE)
    assert {"default", "test-unit", "build-sln", "check-web"} <= set(names)
    assert "api_dir" not in names          # an assignment is not a recipe
    assert "set shell" not in names        # nor is a setting


def test_a_comment_is_not_a_recipe():
    assert "# run the fast suite" not in probes.recipes_from_justfile(JUSTFILE)


def test_recipe_bodies_are_not_mistaken_for_recipes():
    """Indented lines are the body of the recipe above them."""
    assert "npm --prefix {{dir}} run check" not in probes.recipes_from_justfile(JUSTFILE)


def test_no_runner_when_no_marker_file_exists(tmp_path):
    assert probes.task_runner(tmp_path) == ("", [])


def test_just_is_detected_from_its_marker_file(tmp_path, monkeypatch):
    monkeypatch.setattr(probes, "_summary", lambda runner, root: None)
    write(tmp_path, "justfile", JUSTFILE)
    name, recipes = probes.task_runner(tmp_path)
    assert name == "just"
    assert "test-unit" in recipes


def test_a_capitalised_justfile_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(probes, "_summary", lambda runner, root: None)
    write(tmp_path, "Justfile", JUSTFILE)
    assert probes.task_runner(tmp_path)[0] == "just"


def test_the_summary_command_wins_over_the_parser(tmp_path, monkeypatch):
    """`just --summary` resolves imports the offline parser cannot see."""
    monkeypatch.setattr(probes, "_summary", lambda runner, root: ["imported-recipe"])
    write(tmp_path, "justfile", JUSTFILE)
    assert probes.task_runner(tmp_path)[1] == ["imported-recipe"]


def test_every_runner_declares_the_same_four_things():
    """The shape a second runner (nx, make, task) would have to fill in."""
    for runner in probes.RUNNERS:
        assert runner.name and runner.markers and runner.summary and runner.parse_marker


# ── branch and conventions ───────────────────────────────────────────────────

def test_default_branch_falls_back_to_main_outside_a_git_repo(tmp_path):
    assert probes.default_branch(tmp_path) == "main"


def test_convention_files_and_directories_are_recorded(tmp_path):
    write(tmp_path, "CLAUDE.md", "# house rules\n")
    write(tmp_path, "AGENTS.md", "# agents\n")
    write(tmp_path, ".github/instructions/csharp.instructions.md", "# c#\n")
    write(tmp_path, ".github/instructions/svelte.instructions.md", "# svelte\n")

    found = probes.conventions(tmp_path)

    assert "CLAUDE.md" in found
    assert "AGENTS.md" in found
    # A directory of instructions is ONE entry, not one per file — fifteen
    # bullets would drown the prompt overlay they end up in.
    assert ".github/instructions/" in found
    assert ".github/instructions/csharp.instructions.md" not in found


def test_an_empty_instructions_directory_is_not_recorded(tmp_path):
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    assert probes.conventions(tmp_path) == []


def test_no_convention_files_is_an_empty_list_not_an_error(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert probes.conventions(tmp_path) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_probes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.probes'`.

- [ ] **Step 4: Write the probes**

Create `.claude/skills/sssf/templates/profiles/probes.py`:

```python
"""Repo probes that are true of every stack.

Nothing here knows what technology it is looking at. That is the point: an
Angular profile needs the task runner, the default branch, the convention
files, and the package manager exactly as a SvelteKit one does, and the only
difference between finding Angular workspaces and finding SvelteKit apps is
one dependency name passed to `node_packages`.

Read-only except for one subprocess per probe: the task runner's summary
command and `git`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .facts import Frontend

# Directories never worth walking: a vendored tree can contain anything,
# including another repo's solution file and a thousand package.json files.
SKIP_DIRS = {"node_modules", "bin", "obj", ".git", ".svelte-kit", "dist", "build",
             "artifacts", ".venv", "venv", "__pycache__", ".next", ".nuxt"}

# Lockfile -> package manager, most specific first. The lockfile is the only
# honest answer: a `packageManager` field in package.json states an intention,
# a lockfile records what was actually installed.
LOCKFILES = (("pnpm-lock.yaml", "pnpm"), ("yarn.lock", "yarn"),
             ("bun.lockb", "bun"), ("bun.lock", "bun"),
             ("package-lock.json", "npm"))

ENV_EXAMPLE_NAMES = (".env.example", ".env.sample", ".env.template")

CONVENTION_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules",
                    ".github/copilot-instructions.md", "CONTRIBUTING.md")
CONVENTION_DIRS = (".github/instructions", ".cursor/rules")

# A just recipe header starts at column 0, is a name, may take parameters and
# dependencies, and ends in a colon that is not `:=` (an assignment).
#
# The middle is `[^\n]*?` and not `[^:=\n]*`: a recipe may declare a default
# parameter (`check-web dir="apps/web":`), and excluding `=` there means the
# match dies before it ever reaches the terminal colon, silently dropping the
# recipe. Lazy, so the FIRST colon wins, and the lookahead still rejects `:=`.
JUST_RECIPE = re.compile(r"^(?!\s)(?:@)?([A-Za-z_][A-Za-z0-9_-]*)[^\n]*?:(?!=)",
                         re.MULTILINE)


def walk(root: Path):
    """Every file under root, skipping vendored and build-output directories."""
    for path in root.rglob("*"):
        if path.is_file() and not (SKIP_DIRS & set(path.relative_to(root).parts)):
            yield path


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# ── Node packages ────────────────────────────────────────────────────────────

def package_manager(root: Path, directory: Path) -> str:
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


def node_packages(root: Path, marker: str) -> list[Frontend]:
    """Every package.json declaring `marker`, wherever it lives.

    `marker` is the dependency that identifies a framework — `@sveltejs/kit`,
    `@angular/core`, `react`. Everything else about a JavaScript package is
    the same whichever of those it is, which is why this function is here and
    not in a framework module.
    """
    root = Path(root)
    found = []
    for manifest in sorted(p for p in walk(root) if p.name == "package.json"):
        try:
            package = json.loads(manifest.read_text(errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # A broken manifest is the repo's problem, not a reason to abort an
            # install. The framework reports it as unresolved instead.
            continue
        if not isinstance(package, dict):
            continue
        declared = {**(package.get("dependencies") or {}),
                    **(package.get("devDependencies") or {})}
        if marker not in declared:
            continue
        directory = manifest.parent
        example = _env_example(directory)
        found.append(Frontend(
            directory=relative(root, directory) if directory != root else ".",
            package_manager=package_manager(root, directory),
            scripts=sorted((package.get("scripts") or {}).keys()),
            env_example=relative(root, example) if example else "",
        ))
    return found


# ── Task runner ──────────────────────────────────────────────────────────────

def recipes_from_justfile(text: str) -> list[str]:
    """Recipe names parsed straight out of a justfile.

    The offline fallback for when `just` is not installed. It cannot see
    imported files, which is exactly why the summary command is preferred when
    the binary is there.
    """
    return sorted(set(JUST_RECIPE.findall(text)))


@dataclass(frozen=True)
class RunnerProbe:
    """How to recognise one task runner and ask it what it can do.

    Four fields, because that is what recognising a runner takes: the files
    that prove it is in use, the command that lists its tasks, how to read that
    command's output, and how to read the marker file when the binary is not
    installed. A second runner is a second entry in RUNNERS.
    """

    name: str
    markers: tuple[str, ...]
    summary: tuple[str, ...]                      # argv, argv[0] resolved via PATH
    parse_summary: Callable[[str], list[str]]
    parse_marker: Callable[[str], list[str]]


RUNNERS: tuple[RunnerProbe, ...] = (
    RunnerProbe(
        name="just",
        markers=("justfile", "Justfile", ".justfile"),
        summary=("just", "--summary"),
        parse_summary=lambda out: sorted(set(out.split())),
        parse_marker=recipes_from_justfile,
    ),
)


def _summary(runner: RunnerProbe, root: Path) -> list[str] | None:
    """The runner's own task list, or None when it is absent or refuses to run.

    shutil.which is what makes this work on Windows, where a runner may be a
    shim with an extension PATHEXT knows about and bare-name argv does not.
    """
    binary = shutil.which(runner.summary[0])
    if not binary:
        return None
    try:
        completed = subprocess.run([binary, *runner.summary[1:]], cwd=root,
                                   text=True, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return runner.parse_summary(completed.stdout)


def task_runner(root: Path) -> tuple[str, list[str]]:
    """The runner this repo uses, and the task names it knows."""
    root = Path(root)
    for runner in RUNNERS:
        marker = next((root / name for name in runner.markers
                       if (root / name).is_file()), None)
        if marker is None:
            continue
        summary = _summary(runner, root)
        if summary is not None:
            return runner.name, summary
        return runner.name, runner.parse_marker(marker.read_text(errors="replace"))
    return "", []


# ── git and conventions ──────────────────────────────────────────────────────

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
    root = Path(root)
    found = [name for name in CONVENTION_FILES if (root / name).is_file()]
    for directory in CONVENTION_DIRS:
        path = root / directory
        if path.is_dir() and any(path.iterdir()):
            found.append(directory + "/")
    return found
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_probes.py -v`
Expected: PASS — 22 passed.

- [ ] **Step 6: Verify the design rule holds**

Run: `grep -nE "sveltejs|dotnet|csproj|sln" .claude/skills/sssf/templates/profiles/probes.py`
Expected: matches only inside the `node_packages` docstring, where `@sveltejs/kit` and `@angular/core` are named as examples of a marker. Anything else means a framework fact leaked into the shared layer.

- [ ] **Step 7: Commit**

```bash
git add tests/profile_fixtures.py tests/test_probes.py .claude/skills/sssf/templates/profiles/probes.py
git commit -m "feat(profiles): stack-agnostic repo probes every framework reuses"
```

---

## Task 6: Stack-agnostic emitters

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/emit.py`
- Test: `tests/test_emit.py`

**Scene:** the other half of what stops duplication. Preferring a task-runner recipe over a raw command, giving each package a unique block label, turning `package.json` scripts into blocks, and rendering a generated module are all identical whatever the framework. `script_blocks` in particular is the reason Angular is cheap: an Angular package's `npm run build` becomes a block through exactly the code a SvelteKit one does.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_emit.py`:

```python
"""Emitters: shared by every framework, owned by none."""

import ast

from profiles import emit
from profiles.facts import Frontend, GateWiring, ProfileFacts, QualityBlock

SCRIPTS = [
    ("check", ["check-{name}", "check-frontend"], "typecheck", "check"),
    ("test", ["test-{name}"], "test", "test"),
    ("build", ["build-{name}"], "build", "build"),
]


def _repo(**kwargs):
    return ProfileFacts(profile="p", repo_root=".", **kwargs)


# ── recipe preference ────────────────────────────────────────────────────────

def test_no_runner_means_no_recipe():
    argv, source = emit.recipe(_repo(), ["test-unit"])
    assert argv == []
    assert source == ""


def test_the_first_candidate_the_runner_knows_wins():
    repo = _repo(task_runner="just", recipes=["build", "test-api", "test-unit"])
    argv, source = emit.recipe(repo, ["test-unit", "test-api"])
    assert argv == ["just", "test-unit"]
    assert "test-unit" in source


def test_a_candidate_the_runner_does_not_know_is_skipped():
    repo = _repo(task_runner="just", recipes=["test-api"])
    assert emit.recipe(repo, ["test-unit", "test-api"])[0] == ["just", "test-api"]


def test_the_name_placeholder_is_substituted():
    repo = _repo(task_runner="just", recipes=["check-web"])
    assert emit.recipe(repo, ["check-{name}"], name="web")[0] == ["just", "check-web"]


# ── labels ───────────────────────────────────────────────────────────────────

def test_a_unique_directory_name_is_the_label():
    assert emit.labels(["apps/web", "apps/admin"]) == {"apps/web": "web",
                                                       "apps/admin": "admin"}


def test_colliding_names_fall_back_to_the_full_path():
    assert emit.labels(["apps/web", "packages/web"]) == {
        "apps/web": "apps-web", "packages/web": "packages-web"}


def test_the_repo_root_is_labelled_root():
    assert emit.labels(["."]) == {".": "root"}


# ── script blocks ────────────────────────────────────────────────────────────

def test_a_script_becomes_a_block_in_its_own_directory():
    frontends = [Frontend(directory="apps/web", package_manager="npm",
                          scripts=["check", "build"])]
    blocks, unresolved = emit.script_blocks(frontends, _repo(), SCRIPTS)
    by_name = {b.name: b for b in blocks}

    assert by_name["check-web"].argv == ["npm", "run", "check"]
    assert by_name["check-web"].cwd == "apps/web"
    assert by_name["check-web"].area == "frontend"
    assert by_name["check-web"].operation == "typecheck"
    assert "test-web" not in by_name          # no `test` script declared
    assert unresolved == []


def test_the_package_manager_is_honoured():
    frontends = [Frontend(directory="web", package_manager="pnpm", scripts=["build"])]
    blocks, _ = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks[0].argv == ["pnpm", "run", "build"]


def test_a_recipe_beats_the_package_manager_and_runs_from_the_root():
    repo = _repo(task_runner="just", recipes=["check-web"])
    frontends = [Frontend(directory="apps/web", scripts=["check"])]
    block = emit.script_blocks(frontends, repo, SCRIPTS)[0][0]
    assert block.argv == ["just", "check-web"]
    assert block.cwd == "."


def test_a_package_declaring_none_of_the_scripts_is_reported_unresolved():
    frontends = [Frontend(directory="apps/web", scripts=["dev"])]
    blocks, unresolved = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks == []
    assert "apps/web" in unresolved[0]


def test_colliding_package_names_produce_unique_block_names():
    frontends = [Frontend(directory="apps/web", scripts=["build"]),
                 Frontend(directory="packages/web", scripts=["build"])]
    names = [b.name for b in emit.script_blocks(frontends, _repo(), SCRIPTS)[0]]
    assert sorted(names) == ["build-apps-web", "build-packages-web"]


def test_colliding_packages_do_not_share_one_recipe():
    """Unique names are not enough if both run the SAME check.

    With a runner declaring `build-web`, a naive per-package label resolves it
    twice: two differently-named blocks, one identical command, one package
    actually checked. The duplicate-name guard cannot see it, because the names
    differ.

    Correct behaviour is to decline the ambiguous recipe - neither
    `build-apps-web` nor `build-packages-web` is declared - and fall through to
    per-package commands. Those argvs are then IDENTICAL, which is exactly what
    `cwd` exists for, so the pair is what has to be distinct rather than the
    argv alone.
    """
    repo = _repo(task_runner="just", recipes=["build-web"])
    frontends = [Frontend(directory="apps/web", scripts=["build"]),
                 Frontend(directory="packages/web", scripts=["build"])]

    blocks, _ = emit.script_blocks(frontends, repo, SCRIPTS)

    assert len({(tuple(b.argv), b.cwd) for b in blocks}) == 2
    assert {b.cwd for b in blocks} == {"apps/web", "packages/web"}
    # The point of the test: the ambiguous recipe is borrowed by neither.
    assert all("build-web" not in block.argv for block in blocks)


# ── rendering ────────────────────────────────────────────────────────────────

def test_a_rendered_blocks_module_is_valid_python_that_builds_specs():
    from adw_modules.data_types import QualityCheckSpec
    facts = _repo(task_runner="just")
    blocks = [QualityBlock(name="t", area="backend", operation="build",
                           argv=["dotnet", "test", "a/B.csproj"], tier="full",
                           timeout_seconds=1800, source="project role unit-tests")]

    text = emit.render_blocks_module(facts, blocks)

    ast.parse(text)
    assert "GENERATED" in text
    assert "from .data_types import QualityCheckSpec" in text
    namespace = {"QualityCheckSpec": QualityCheckSpec}
    exec(text.split("from .data_types import QualityCheckSpec", 1)[1], namespace)
    assert namespace["BLOCKS"][0].tier == "full"
    assert namespace["BLOCKS"][0].timeout_seconds == 1800


def test_a_rendered_gates_module_imports_only_what_it_wires():
    facts = _repo()
    wirings = [GateWiring(module="gates_dotnet", name="ef_migration_triad",
                          call="ef_migration_triad"),
               GateWiring(module="gates_sveltekit", name="env_example_sync",
                          call="env_example_sync([('a', 'a/.env.example')], ['PUBLIC_'])")]

    text = emit.render_gates_module(facts, wirings)

    ast.parse(text)
    assert "from .gates_dotnet import ef_migration_triad" in text
    assert "from .gates_sveltekit import env_example_sync" in text
    assert "sveltekit_csp" not in text
    assert "PROFILE_GATES" in text


def test_two_gates_from_one_module_share_an_import_line():
    facts = _repo()
    wirings = [GateWiring(module="gates_sveltekit", name="env_example_sync",
                          call="env_example_sync([], [])"),
               GateWiring(module="gates_sveltekit", name="sveltekit_csp",
                          call="sveltekit_csp([])")]
    text = emit.render_gates_module(facts, wirings)
    assert text.count("from .gates_sveltekit import") == 1
    assert "env_example_sync, sveltekit_csp" in text


def test_writing_records_the_path_it_wrote(tmp_path):
    written = []
    emit.write_file(tmp_path, "adws/adw_modules/x.py", "BLOCKS = []\n", written)
    assert (tmp_path / "adws" / "adw_modules" / "x.py").read_text() == "BLOCKS = []\n"
    assert len(written) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_emit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.emit'`.

- [ ] **Step 3: Write the emitters**

Create `.claude/skills/sssf/templates/profiles/emit.py`:

```python
"""Turning facts into files. Shared by every framework, owned by none.

Everything emitted is plain, readable, editable Python — a file an operator can
open and correct is worth more than a clever indirection they cannot.

The preference order encoded here, once, for all frameworks: a task-runner
recipe the team already maintains beats a command composed from parts, because
the recipe is what the humans run and the humans keep it working.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .facts import Frontend, GateWiring, ProfileFacts, QualityBlock

# (package.json script, candidate recipe names, quality operation, block prefix)
FrontendScript = tuple[str, list[str], str, str]

BLOCKS_HEADER = '''"""GENERATED - do not expect edits here to survive a re-install.

Written by `install.py --profile {profile}` at {stamp}.

What was detected in this repository:
{summary}

This file is DATA: the list of commands this repo actually uses. It is plain
Python, so correcting a wrong command is opening it and typing the right one.
Re-probe after a restructure with `install.py --doctor`, which reports drift
without writing, then re-install with --profile to rewrite this file.

`tier="full"` means slow or service-dependent - a suite that needs Docker up.
Full blocks run in run_quality() only, never inside a bounded fix loop.
"""

from .data_types import QualityCheckSpec

BLOCKS = [
{entries}]
'''

GATES_HEADER = '''"""GENERATED - do not expect edits here to survive a re-install.

Written by `install.py --profile {profile}` at {stamp}.

The stack gates, parameterized with what detection found in THIS repository.
`gates.profile_gates()` loads this list; an un-profiled repo has no such file
and gets an empty list instead.

Each entry is a plain function of (envelope, run). To stop enforcing one,
delete its line - the factory will not argue, and the next re-install will put
it back.
"""

{imports}

PROFILE_GATES = [
{entries}]
'''


def recipe(repo: ProfileFacts, candidates: list[str],
           name: str = "") -> tuple[list[str], str]:
    """The first candidate task the runner actually knows, as an argv.

    Returns `([], "")` when there is no runner or no candidate matches, which
    is the caller's cue to compose a raw command instead.
    """
    if not repo.task_runner:
        return [], ""
    for candidate in candidates:
        task = candidate.replace("{name}", name)
        if task in repo.recipes:
            return [repo.task_runner, task], f"recipe {repo.task_runner} {task}"
    return [], ""


def labels(directories: list[str]) -> dict[str, str]:
    """A short, unique name per directory, for use in block names.

    `apps/web` is `web` until a repo also has `packages/web`, at which point
    both become their full path. Uniqueness matters: two blocks with one name
    produce two trace rows nobody can tell apart.
    """
    plain = {d: (Path(d).name or "root") for d in directories}
    counts = Counter(plain.values())
    return {directory: (label if counts[label] == 1
                        else directory.replace("/", "-").strip("-") or "root")
            for directory, label in plain.items()}


def script_blocks(frontends: list[Frontend], repo: ProfileFacts,
                  scripts: list[FrontendScript]) -> tuple[list[QualityBlock], list[str]]:
    """package.json scripts, as quality blocks. One implementation, every framework.

    This is the function that makes a second frontend framework cheap: an
    Angular package's `npm run build` becomes a block through exactly the code
    a SvelteKit one does. Only WHICH packages to pass in, and which script
    names to look for, differ.
    """
    blocks: list[QualityBlock] = []
    unresolved: list[str] = []
    label_of = labels([f.directory for f in frontends])

    for frontend in frontends:
        emitted = 0
        for script, candidates, operation, prefix in scripts:
            if not frontend.has(script):
                continue
            # The collision-aware label, NOT the bare directory name. Two
            # packages both called `web` would otherwise resolve the same
            # `check-{name}` recipe and emit two differently-named blocks
            # running one identical command against one of them.
            argv, source = recipe(repo, candidates,
                                  name=label_of[frontend.directory])
            blocks.append(QualityBlock(
                name=f"{prefix}-{label_of[frontend.directory]}",
                area="frontend", operation=operation,
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
                f"package {frontend.directory} declares none of "
                f"{', '.join(s for s, *_ in scripts)} - nothing verifies it")
    return blocks, unresolved


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _summary(facts: ProfileFacts, extra: list[str]) -> str:
    lines = list(extra)
    lines.append(f"  task runner: {facts.task_runner or '(none)'}")
    lines.append(f"  default branch: {facts.default_branch}")
    lines.append(f"  conventions: {', '.join(facts.conventions) or '(none found)'}")
    return "\n".join(lines)


def _entry(block: QualityBlock) -> str:
    return ("    QualityCheckSpec(\n"
            f"        name={block.name!r}, area={block.area!r}, "
            f"operation={block.operation!r},\n"
            f"        argv={block.argv!r},\n"
            f"        cwd={block.cwd!r}, tier={block.tier!r}, "
            f"timeout_seconds={block.timeout_seconds},\n"
            f"    ),  # {block.source}\n")


def render_blocks_module(facts: ProfileFacts, blocks: list[QualityBlock],
                         summary: list[str] = ()) -> str:
    return BLOCKS_HEADER.format(
        profile=facts.profile, stamp=_stamp(), summary=_summary(facts, list(summary)),
        entries="".join(_entry(b) for b in blocks))


def render_gates_module(facts: ProfileFacts, wirings: list[GateWiring]) -> str:
    """Import only the gates that are actually wired, grouped one line per module."""
    by_module: dict[str, list[str]] = {}
    for wiring in wirings:
        names = by_module.setdefault(wiring.module, [])
        if wiring.name not in names:
            names.append(wiring.name)
    imports = "\n".join(f"from .{module} import {', '.join(sorted(names))}"
                        for module, names in sorted(by_module.items()))
    return GATES_HEADER.format(
        profile=facts.profile, stamp=_stamp(), imports=imports,
        entries="".join(f"    {w.call},\n" for w in wirings))


def write_file(root, relative: str, text: str, written: list[str]) -> None:
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    written.append(str(path))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_emit.py -v`
Expected: PASS — 17 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_emit.py .claude/skills/sssf/templates/profiles/emit.py
git commit -m "feat(profiles): stack-agnostic emitters every framework reuses"
```

---

## Task 7: The `dotnet` framework module

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/frameworks/__init__.py` (placeholder, completed in Task 9)
- Create: `.claude/skills/sssf/templates/profiles/frameworks/dotnet.py`
- Test: `tests/test_framework_dotnet.py`

**Scene:** the first framework module, and the template every later one copies its *shape* from. Everything about .NET lives here: how to find a solution, how to tell a test project from an application, which commands that implies, which gate it brings. A `dotnet-angular` profile written next month imports this file unchanged.

A `.sln` is an INI-ish text file whose project entries look like
`Project("{FAE04EC0-...}") = "Api", "apps\api\Api\Api.csproj", "{GUID}"`. A `.slnx` is XML with `<Project Path="apps/api/Api/Api.csproj" />`. Solution *folders* appear in `.sln` too, with a path that is not a `.csproj` — they are filtered out.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_framework_dotnet.py`:

```python
"""The dotnet framework: solution parsing, project roles, its blocks and gate."""

from profile_fixtures import (CSPROJ_APP, CSPROJ_INTEGRATION, CSPROJ_UNIT,
                              dotnet_svelte_repo, sln, write)

from profiles.facts import ProfileFacts
from profiles.frameworks import dotnet


def _repo(**kwargs):
    return ProfileFacts(profile="p", repo_root=".", **kwargs)


# ── detection ────────────────────────────────────────────────────────────────

def test_finds_the_solution_and_classifies_every_project(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)

    assert facts.solution == "Fixture.sln"
    assert {p.name: p.role for p in facts.projects} == {
        "Api": "app", "Api.Tests": "unit-tests",
        "Api.IntegrationTests": "integration-tests"}


def test_project_paths_are_repo_relative_with_forward_slashes(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)
    assert all("\\" not in p.path for p in facts.projects)
    assert "apps/api/Api/Api.csproj" in [p.path for p in facts.projects]


def test_solution_folders_are_not_projects(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Folders.sln", ["src/App/App.csproj"], folders=["Solution Items"])
    assert [p.name for p in dotnet.detect(tmp_path).projects] == ["App"]


def test_an_slnx_solution_is_read_too(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    write(tmp_path, "Modern.slnx",
          '<Solution>\n  <Project Path="src/App/App.csproj" />\n</Solution>\n')
    facts = dotnet.detect(tmp_path)
    assert facts.solution == "Modern.slnx"
    assert [p.name for p in facts.projects] == ["App"]


def test_testcontainers_outranks_a_test_sdk():
    """A project with both is an INTEGRATION suite - it needs Docker up."""
    assert dotnet.classify(CSPROJ_INTEGRATION) == "integration-tests"
    assert dotnet.classify(CSPROJ_UNIT) == "unit-tests"
    assert dotnet.classify(CSPROJ_APP) == "app"


def test_a_project_named_in_the_solution_but_missing_on_disk_is_an_app(tmp_path):
    """Never crash on a stale solution entry; the worst case is a wrong role."""
    sln(tmp_path, "Stale.sln", ["gone/Gone.csproj"])
    assert [(p.name, p.role) for p in dotnet.detect(tmp_path).projects] == [("Gone", "app")]


def test_a_solution_inside_node_modules_is_ignored(tmp_path):
    write(tmp_path, "node_modules/pkg/Vendor.sln", "Microsoft Visual Studio Solution File")
    assert dotnet.detect(tmp_path).solution == ""


def test_the_shallowest_solution_wins(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Root.sln", ["src/App/App.csproj"])
    sln(tmp_path, "src/Nested.sln", ["App/App.csproj"])
    assert dotnet.detect(tmp_path).solution == "Root.sln"


def test_matches_requires_a_solution(tmp_path):
    assert not dotnet.matches(tmp_path)
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    assert dotnet.matches(tmp_path)


def test_by_role_filters(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)
    assert [p.name for p in facts.by_role("unit-tests")] == ["Api.Tests"]
    assert [p.name for p in facts.by_role("integration-tests")] == ["Api.IntegrationTests"]


# ── blocks ───────────────────────────────────────────────────────────────────

def _blocks(tmp_path, repo=None, **kwargs):
    dotnet_svelte_repo(tmp_path, **kwargs)
    facts = dotnet.detect(tmp_path)
    blocks, unresolved = dotnet.blocks(facts, repo or _repo())
    return {b.name: b for b in blocks}, unresolved


def test_a_unit_test_project_becomes_a_fast_dotnet_test_block(tmp_path):
    blocks, _ = _blocks(tmp_path, integration=False)
    block = blocks["test-Api.Tests"]
    assert block.argv == ["dotnet", "test", "apps/api/Api.Tests/Api.Tests.csproj"]
    assert block.tier == "fast"
    assert block.area == "backend"


def test_an_integration_project_is_tagged_full(tmp_path):
    blocks, _ = _blocks(tmp_path)
    assert blocks["test-Api.IntegrationTests"].tier == "full"


def test_the_solution_build_is_emitted(tmp_path):
    blocks, _ = _blocks(tmp_path)
    assert blocks["build-sln"].argv == ["dotnet", "build", "Fixture.sln"]


def test_a_recipe_replaces_the_per_project_commands(tmp_path):
    """One recipe covers every project of a role; running it per project would
    run the same suite N times."""
    repo = _repo(task_runner="just", recipes=["test-unit", "build-sln"])
    blocks, _ = _blocks(tmp_path, repo)
    assert blocks["test-unit"].argv == ["just", "test-unit"]
    assert "test-Api.Tests" not in blocks
    assert blocks["build-sln"].argv == ["just", "build-sln"]


def test_a_recipe_that_does_not_exist_falls_back_to_the_raw_command(tmp_path):
    repo = _repo(task_runner="just", recipes=["deploy"])
    blocks, _ = _blocks(tmp_path, repo)
    assert blocks["test-Api.Tests"].argv[0] == "dotnet"


def test_a_missing_role_is_reported_unresolved(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    _, unresolved = dotnet.blocks(dotnet.detect(tmp_path), _repo())
    assert any("unit-tests" in note for note in unresolved)
    assert any("integration-tests" in note for note in unresolved)


def test_no_solution_means_no_build_block_and_a_note(tmp_path):
    blocks, unresolved = dotnet.blocks(dotnet.detect(tmp_path), _repo())
    assert blocks == []
    assert any("sln" in note for note in unresolved)


# ── report and gates ─────────────────────────────────────────────────────────

def test_describe_names_the_solution_and_every_project(tmp_path):
    dotnet_svelte_repo(tmp_path)
    lines = "\n".join(dotnet.describe(dotnet.detect(tmp_path)))
    assert "Fixture.sln" in lines
    assert "Api.IntegrationTests" in lines
    assert "integration-tests" in lines


def test_the_migration_gate_is_always_wired(tmp_path):
    dotnet_svelte_repo(tmp_path)
    wirings = dotnet.gate_wiring(dotnet.detect(tmp_path))
    assert [w.name for w in wirings] == ["ef_migration_triad"]
    assert wirings[0].module == dotnet.GATE_MODULE
    assert wirings[0].call == "ef_migration_triad"


def test_the_framework_declares_no_repository_specific_paths():
    """The design rule, checked on the file most likely to break it."""
    from pathlib import Path
    text = Path(dotnet.__file__).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/api", "Fixture.sln"):
        assert forbidden not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_framework_dotnet.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.frameworks'`.

- [ ] **Step 3: Create the package placeholder**

Create `.claude/skills/sssf/templates/profiles/frameworks/__init__.py` containing exactly:

```python
"""Framework modules: one per technology. The registry lands in Task 9."""
```

- [ ] **Step 4: Write the framework**

Create `.claude/skills/sssf/templates/profiles/frameworks/dotnet.py`:

```python
"""Everything about .NET, in one file.

A framework module answers the same questions for its own technology and
nothing else: is it here, what did I find, what commands does that imply, what
should the report say, and which gates does it bring. It never imports another
framework — shared work goes through `probes` and `emit`, so a profile pairing
.NET with Angular reuses this file untouched.

Nothing here names a path from any repository. Every concrete string it returns
was read out of the tree it was pointed at.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .. import emit, probes
from ..facts import FrameworkFacts, GateWiring, ProfileFacts, QualityBlock

NAME = "dotnet"
GATE_MODULE = "gates_dotnet"        # stamped into adws/adw_modules/
OVERLAY = "dotnet.md"               # fragment under profiles/prompts/

# `Project("{type-guid}") = "Name", "relative\path.csproj", "{project-guid}"`
SLN_PROJECT = re.compile(r'^Project\("\{[0-9A-Fa-f-]+\}"\)\s*=\s*"[^"]*",\s*"([^"]+)"',
                         re.MULTILINE)
SLNX_PROJECT = re.compile(r'<Project\s+[^>]*Path="([^"]+)"')

TEST_SDK_MARKERS = ("xunit", "Microsoft.NET.Test.Sdk", "NUnit", "MSTest")
INTEGRATION_MARKERS = ("Testcontainers",)

# Candidate task-runner names per block, best first. Conventions of the
# ecosystem, not of any repository — and where an Angular module would put its
# own. `{name}` is substituted with a discovered value where one applies.
RECIPES = {
    "unit_tests": ["test-unit", "test-api", "test-dotnet", "test-backend"],
    "integration_tests": ["test-api-integration", "test-integration", "test-e2e-api"],
    "solution_build": ["build-sln", "build-dotnet", "build-api"],
}

ProjectRole = Literal["app", "unit-tests", "integration-tests"]


class DotnetProject(BaseModel):
    """One project in the solution, and what it is for."""

    path: str                       # repo-relative, forward slashes
    name: str                       # the .csproj stem
    role: ProjectRole


class DotnetFacts(FrameworkFacts):
    solution: str = ""              # repo-relative *.sln or *.slnx
    projects: list[DotnetProject] = Field(default_factory=list)

    def by_role(self, role: str) -> list[DotnetProject]:
        return [p for p in self.projects if p.role == role]


# ── detection ────────────────────────────────────────────────────────────────

def find_solution(root: Path) -> str:
    """The solution file, shallowest first so a repo-root one always wins."""
    candidates = [p for p in probes.walk(root) if p.suffix in (".sln", ".slnx")]
    if not candidates:
        return ""
    candidates.sort(key=lambda p: (len(p.relative_to(root).parts), p.name))
    return probes.relative(root, candidates[0])


def solution_projects(root: Path, solution: str) -> list[str]:
    """Repo-relative, forward-slashed paths of every .csproj the solution names."""
    text = (root / solution).read_text(errors="replace")
    pattern = SLNX_PROJECT if solution.endswith(".slnx") else SLN_PROJECT
    solution_dir = Path(solution).parent
    paths = []
    for raw in pattern.findall(text):
        entry = raw.replace("\\", "/")
        if not entry.lower().endswith(".csproj"):
            continue                       # a solution folder, not a project
        paths.append((solution_dir / entry).as_posix().removeprefix("./"))
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


def matches(root) -> bool:
    return bool(find_solution(Path(root)))


def detect(root) -> DotnetFacts:
    root = Path(root)
    solution = find_solution(root)
    if not solution:
        return DotnetFacts()
    projects = []
    for relative in solution_projects(root, solution):
        path = root / relative
        # A solution can name a project that is not on disk. Treat it as an app:
        # the worst case is one block too few, and crashing the installer over a
        # stale solution entry would be a far worse trade.
        text = path.read_text(errors="replace") if path.is_file() else ""
        projects.append(DotnetProject(path=relative, name=Path(relative).stem,
                                      role=classify(text)))
    return DotnetFacts(solution=solution, projects=projects)


# ── generation ───────────────────────────────────────────────────────────────

def blocks(facts: DotnetFacts, repo: ProfileFacts) -> tuple[list[QualityBlock], list[str]]:
    emitted: list[QualityBlock] = []
    unresolved: list[str] = []

    for role, recipe_key, block_name, tier, timeout in (
            ("unit-tests", "unit_tests", "test-unit", "fast", 900),
            ("integration-tests", "integration_tests", "test-integration", "full", 1800)):
        argv, source = emit.recipe(repo, RECIPES[recipe_key])
        projects = facts.by_role(role)
        if argv:
            # One recipe covers every project of this role: a team that wrote
            # `test-unit` meant all of them, and running it once per project
            # would run the same suite N times.
            emitted.append(QualityBlock(name=block_name, area="backend",
                                        operation="test", argv=argv, tier=tier,
                                        timeout_seconds=timeout, source=source))
        elif projects:
            for project in projects:
                emitted.append(QualityBlock(
                    name=f"test-{project.name}", area="backend", operation="test",
                    argv=["dotnet", "test", project.path], tier=tier,
                    timeout_seconds=timeout, source=f"project role {role}"))
        else:
            unresolved.append(
                f"no {role} project in the solution and no task-runner recipe "
                f"for it - nothing verifies that tier")

    if facts.solution:
        argv, source = emit.recipe(repo, RECIPES["solution_build"])
        emitted.append(QualityBlock(
            name="build-sln", area="backend", operation="build",
            argv=argv or ["dotnet", "build", facts.solution],
            tier="fast", timeout_seconds=900,
            source=source or f"solution {facts.solution}"))
    else:
        unresolved.append("no .sln or .slnx found - no backend build block")
    return emitted, unresolved


def describe(facts: DotnetFacts) -> list[str]:
    lines = [f"solution: {facts.solution or '(none)'}"]
    lines += [f"project: {p.path}  [{p.role}]" for p in facts.projects]
    return lines


def gate_wiring(facts: DotnetFacts) -> list[GateWiring]:
    """EF Core's three-file migration rule, wired unconditionally.

    Unconditional because it costs nothing when no migration is in the change:
    the gate records no checks at all, so a repo that never uses EF Core never
    sees it. Gating it on "does this repo reference EF Core" would add a probe
    whose only effect is to skip a no-op.
    """
    return [GateWiring(module=GATE_MODULE, name="ef_migration_triad",
                       call="ef_migration_triad")]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_framework_dotnet.py -v`
Expected: PASS — 20 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/test_framework_dotnet.py .claude/skills/sssf/templates/profiles/frameworks/
git commit -m "feat(profiles): the dotnet framework module"
```

---

## Task 8: The `sveltekit` framework module

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/frameworks/sveltekit.py`
- Test: `tests/test_framework_sveltekit.py`

**Scene:** the second framework, and the one that proves the shape is reusable. Note how small it is: detection is `probes.node_packages` plus one SvelteKit-specific probe, and block generation is a single call to `emit.script_blocks`. An `angular.py` is the same file with a different marker, a different CSP-equivalent, and different gate wiring.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_framework_sveltekit.py`:

```python
"""The sveltekit framework: marker, CSP probe, its blocks and two gates."""

from profile_fixtures import package, write

from profiles.facts import ProfileFacts
from profiles.frameworks import sveltekit


def _repo(**kwargs):
    return ProfileFacts(profile="p", repo_root=".", **kwargs)


def test_matches_only_when_a_package_declares_sveltekit(tmp_path):
    assert not sveltekit.matches(tmp_path)
    package(tmp_path, "ng", {"build": "ng build"}, marker="@angular/core")
    assert not sveltekit.matches(tmp_path)
    package(tmp_path, "web", {"build": "vite build"})
    assert sveltekit.matches(tmp_path)


def test_every_frontend_is_found_independently(tmp_path):
    for directory in ("apps/web", "apps/admin"):
        package(tmp_path, directory, {"check": "svelte-check"})
    assert sorted(f.directory for f in sveltekit.detect(tmp_path).frontends) == \
        ["apps/admin", "apps/web"]


def test_a_hooks_file_is_recorded_only_when_it_mentions_csp(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    package(tmp_path, "apps/admin", {"build": "x"})
    write(tmp_path, "apps/web/src/hooks.server.ts",
          "// content-security-policy is set here\n")
    write(tmp_path, "apps/admin/src/hooks.server.ts", "export const handle = x;\n")

    facts = sveltekit.detect(tmp_path)

    assert facts.csp_files == {"apps/web": "apps/web/src/hooks.server.ts"}
    assert "apps/admin" not in facts.csp_files


def test_scripts_become_blocks_through_the_shared_emitter(tmp_path):
    package(tmp_path, "apps/web", {"check": "svelte-check", "test": "vitest run",
                                   "build": "vite build"})
    blocks, unresolved = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    by_name = {b.name: b for b in blocks}

    assert by_name["check-web"].argv == ["npm", "run", "check"]
    assert by_name["check-web"].cwd == "apps/web"
    assert by_name["check-web"].operation == "typecheck"
    assert by_name["test-web"].argv == ["npm", "run", "test"]
    assert by_name["build-web"].argv == ["npm", "run", "build"]
    assert unresolved == []


def test_a_lint_script_is_picked_up_when_present(tmp_path):
    package(tmp_path, "web", {"lint": "eslint ."})
    blocks, _ = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    assert blocks[0].name == "lint-web"
    assert blocks[0].operation == "lint"


def test_describe_names_every_frontend_and_its_manager(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"}, lockfile="pnpm-lock.yaml")
    lines = "\n".join(sveltekit.describe(sveltekit.detect(tmp_path)))
    assert "apps/web" in lines
    assert "pnpm" in lines


def test_env_example_sync_is_wired_only_when_an_example_exists(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    assert sveltekit.gate_wiring(sveltekit.detect(tmp_path)) == []

    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert [w.name for w in wirings] == ["env_example_sync"]
    assert "apps/web/.env.example" in wirings[0].call
    assert "PUBLIC_" in wirings[0].call


def test_csp_is_wired_only_when_a_policy_was_detected(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/src/hooks.server.ts", "// csp\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert [w.name for w in wirings] == ["sveltekit_csp"]
    assert "hooks.server.ts" in wirings[0].call


def test_the_wired_calls_are_valid_python_expressions(tmp_path):
    import ast
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    write(tmp_path, "apps/web/src/hooks.server.ts", "// csp\n")
    for wiring in sveltekit.gate_wiring(sveltekit.detect(tmp_path)):
        ast.parse(wiring.call, mode="eval")


def test_gates_from_several_frontends_are_wired_in_one_call(tmp_path):
    for directory in ("apps/web", "apps/admin"):
        package(tmp_path, directory, {"build": "x"})
        write(tmp_path, f"{directory}/.env.example", "PUBLIC_X=\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert len(wirings) == 1
    assert "apps/web" in wirings[0].call and "apps/admin" in wirings[0].call


def test_the_framework_declares_no_repository_specific_paths():
    from pathlib import Path
    text = Path(sveltekit.__file__).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/web", "apps/admin"):
        assert forbidden not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_framework_sveltekit.py -v`
Expected: FAIL — `cannot import name 'sveltekit' from 'profiles.frameworks'`.

- [ ] **Step 3: Write the framework**

Create `.claude/skills/sssf/templates/profiles/frameworks/sveltekit.py`:

```python
"""Everything about SvelteKit, in one file.

Deliberately short. Detection is `probes.node_packages` with one marker plus a
single SvelteKit-specific probe; block generation is one call to
`emit.script_blocks`. That is what a frontend framework should cost once the
shared layer exists - and it is the measure to hold a future angular.py to.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from .. import emit, probes
from ..facts import FrameworkFacts, Frontend, GateWiring, ProfileFacts, QualityBlock

NAME = "sveltekit"
GATE_MODULE = "gates_sveltekit"
OVERLAY = "sveltekit.md"

# The dependency that identifies this framework in a package.json.
MARKER = "@sveltejs/kit"

# SvelteKit exposes only PUBLIC_*; Vite, which it builds on, exposes VITE_*.
# Build-tool conventions, not repository conventions.
ENV_PREFIXES = ["PUBLIC_", "VITE_"]

# SvelteKit's server hook, and the words that mean it declares a policy.
HOOKS_RELATIVE = "src/hooks.server.ts"
CSP_MARKERS = ("csp", "content-security-policy")

# (package.json script, candidate recipe names, quality operation, block prefix)
SCRIPTS = [
    ("check", ["check-{name}", "check-frontend"], "typecheck", "check"),
    ("lint", ["lint-{name}", "lint-frontend"], "lint", "lint"),
    ("test", ["test-{name}", "test-frontend"], "test", "test"),
    ("build", ["build-{name}", "build-frontend"], "build", "build"),
]


class SvelteKitFacts(FrameworkFacts):
    frontends: list[Frontend] = Field(default_factory=list)
    # Manifests that did not parse. probes.node_packages skips them, which makes
    # them invisible to matches() too - so a repo whose only SvelteKit
    # package.json has a trailing comma is told "no profile matches", for a
    # reason the installer knew and did not print. Collected here, reported by
    # blocks() as unresolved.
    unreadable: list[str] = Field(default_factory=list)
    # frontend directory -> the file declaring its content-security policy.
    # Lives here rather than on Frontend because only SvelteKit has the
    # concept: a shared type with one empty slot per framework is how "adding
    # a framework touches no core module" stops being true.
    csp_files: dict[str, str] = Field(default_factory=dict)


def _csp_file(root: Path, frontend: Frontend) -> str:
    """The server hook, but only when it actually declares a CSP.

    Opt-in on purpose: the csp gate fires on external origins, and pointing it
    at a repo that has no policy would be noise on every single run.
    """
    hooks = root / frontend.directory / HOOKS_RELATIVE
    if not hooks.is_file():
        return ""
    text = hooks.read_text(errors="replace").lower()
    return probes.relative(root, hooks) if any(m in text for m in CSP_MARKERS) else ""


def matches(root) -> bool:
    return bool(probes.node_packages(Path(root), MARKER))


def detect(root) -> SvelteKitFacts:
    root = Path(root)
    unreadable: list[str] = []
    frontends = probes.node_packages(root, MARKER, unreadable)
    csp_files = {f.directory: _csp_file(root, f) for f in frontends}
    return SvelteKitFacts(frontends=frontends, unreadable=unreadable,
                          csp_files={d: p for d, p in csp_files.items() if p})


def blocks(facts: SvelteKitFacts,
           repo: ProfileFacts) -> tuple[list[QualityBlock], list[str]]:
    emitted, unresolved = emit.script_blocks(facts.frontends, repo, SCRIPTS)
    unresolved += [f"{path} does not parse as JSON - the package it declares is "
                   f"invisible to detection" for path in facts.unreadable]
    return emitted, unresolved


def describe(facts: SvelteKitFacts) -> list[str]:
    """Name the files the gates key off, so --doctor can show them moving.

    A relocated .env.example or hooks.server.ts silently unwires a gate, and
    the gate list alone reports only a name. These lines are what make that
    drift visible in a doctor run.
    """
    lines = []
    for frontend in facts.frontends:
        lines.append(f"frontend: {frontend.directory}  [{frontend.package_manager}] "
                     f"scripts: {', '.join(frontend.scripts) or 'none'}")
        if frontend.env_example:
            lines.append(f"  env example: {frontend.env_example}")
        if facts.csp_files.get(frontend.directory):
            lines.append(f"  csp: {facts.csp_files[frontend.directory]}")
    return lines


def gate_wiring(facts: SvelteKitFacts) -> list[GateWiring]:
    """Wire a gate only when the fact it needs was actually found.

    A gate that cries wolf is deleted along with the ones that do not, so an
    absent fact means an absent gate rather than a disabled one.
    """
    wirings = []

    env_pairs = [(f.directory, f.env_example) for f in facts.frontends if f.env_example]
    if env_pairs:
        wirings.append(GateWiring(
            module=GATE_MODULE, name="env_example_sync",
            call=f"env_example_sync({env_pairs!r}, {ENV_PREFIXES!r})"))

    csp_pairs = sorted(facts.csp_files.items())
    if csp_pairs:
        wirings.append(GateWiring(
            module=GATE_MODULE, name="sveltekit_csp",
            call=f"sveltekit_csp({csp_pairs!r})"))
    return wirings
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_framework_sveltekit.py -v`
Expected: PASS — 11 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_framework_sveltekit.py .claude/skills/sssf/templates/profiles/frameworks/sveltekit.py
git commit -m "feat(profiles): the sveltekit framework module"
```

---

## Task 9: The framework registry and its interface

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/frameworks/__init__.py`
- Test: `tests/test_framework_registry.py`

**Scene:** the contract. Eight names, checked at import, so a half-written framework fails here — naming what is missing — rather than at the moment a profile tries to use it. This is the file a person adding Angular reads first.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_framework_registry.py`:

```python
"""The framework contract: eight names, checked at import."""

import pytest

from profiles import frameworks


def test_both_shipped_frameworks_are_registered():
    assert frameworks.names() == ["dotnet", "sveltekit"]


def test_every_framework_satisfies_the_interface():
    for name in frameworks.names():
        module = frameworks.get(name)
        for attribute in frameworks.FRAMEWORK_INTERFACE:
            assert hasattr(module, attribute), f"{name} is missing {attribute}"


def test_the_interface_is_the_one_documented():
    assert set(frameworks.FRAMEWORK_INTERFACE) == {
        "NAME", "GATE_MODULE", "OVERLAY",
        "matches", "detect", "blocks", "describe", "gate_wiring"}


def test_an_unknown_framework_says_what_is_available():
    with pytest.raises(SystemExit) as error:
        frameworks.get("angular")
    assert "angular" in str(error.value)
    assert "sveltekit" in str(error.value)


def test_a_framework_registers_under_its_own_NAME():
    for name in frameworks.names():
        assert frameworks.get(name).NAME == name


def test_the_interface_check_rejects_an_incomplete_framework():
    """The guarantee itself: a half-written module must fail loudly."""
    from types import SimpleNamespace
    broken = SimpleNamespace(NAME="broken", GATE_MODULE="", OVERLAY="")
    with pytest.raises(ImportError) as error:
        frameworks.verify(broken)
    assert "matches" in str(error.value)


def test_no_framework_imports_another_framework():
    """Frameworks compose through probes and emit, never through each other."""
    from pathlib import Path
    for name in frameworks.names():
        text = Path(frameworks.get(name).__file__).read_text()
        for other in frameworks.names():
            if other != name:
                assert f"import {other}" not in text
                assert f"from .{other}" not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_framework_registry.py -v`
Expected: FAIL — `module 'profiles.frameworks' has no attribute 'names'`.

- [ ] **Step 3: Write the registry**

Replace `.claude/skills/sssf/templates/profiles/frameworks/__init__.py` with:

```python
"""Framework modules: one per technology, all the same shape.

ADDING A FRAMEWORK
------------------
1. Write `frameworks/<name>.py` exposing the eight names in
   FRAMEWORK_INTERFACE. Copy `sveltekit.py` for a frontend or `dotnet.py` for
   a backend - both are deliberately short.
2. If it brings gates, write `gates/<GATE_MODULE>.py`. It is STAMPED into a
   target repo's adw_modules/, so its imports are relative.
3. If it has prompt guidance, write `prompts/<OVERLAY>`.
4. Add it to FRAMEWORKS below.
5. Create `<profile_dir>/profile.yaml` naming it alongside whatever it pairs
   with. No core module changes, and no other framework changes.

A framework must NOT import another framework. Shared work lives in `probes`
(finding things) and `emit` (writing things), which is why pairing .NET with a
second frontend costs one file rather than a fork of this one.
"""

from types import ModuleType

from . import dotnet, sveltekit

# What a profile driver may call on any framework.
FRAMEWORK_INTERFACE = (
    "NAME",           # str: the id it registers under
    "GATE_MODULE",    # str: gate file to stamp, "" for none
    "OVERLAY",        # str: prompt fragment filename, "" for none
    "matches",        # (root) -> bool
    "detect",         # (root) -> FrameworkFacts subclass
    "blocks",         # (facts, repo) -> (list[QualityBlock], list[str])
    "describe",       # (facts) -> list[str], rendered into a generated
                      #   module's DOCSTRING - return normalized paths, because
                      #   a backslash there is a live escape sequence
    "gate_wiring",    # (facts) -> list[GateWiring]
)


def verify(module) -> None:
    """Fail at import, naming what is missing, rather than at first use."""
    missing = [a for a in FRAMEWORK_INTERFACE if not hasattr(module, a)]
    if missing:
        raise ImportError(
            f"framework {getattr(module, 'NAME', module)!r} is missing "
            f"{', '.join(missing)} - see FRAMEWORK_INTERFACE")


FRAMEWORKS: tuple[ModuleType, ...] = (dotnet, sveltekit)

for _framework in FRAMEWORKS:
    verify(_framework)


def names() -> list[str]:
    return sorted(f.NAME for f in FRAMEWORKS)


def get(name: str) -> ModuleType:
    for framework in FRAMEWORKS:
        if framework.NAME == name:
            return framework
    raise SystemExit(f"unknown framework {name!r} - available: {', '.join(names())}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_framework_registry.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_framework_registry.py .claude/skills/sssf/templates/profiles/frameworks/__init__.py
git commit -m "feat(profiles): the framework contract, checked at import"
```

---

## Task 10: The composite driver

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/composite.py`
- Test: `tests/test_composite.py`

**Scene:** the generic half. A profile declares which frameworks a stack is made of; this driver merges them. It matches when every declared framework matches, detects by asking each in turn, and generates by concatenating what each returns. It contains no knowledge of .NET or Svelte — which is what makes `dotnet-angular` a YAML file rather than a package.

One rule it enforces: two frameworks may not emit a block with the same name. A silently dropped block is a check that stopped running, so a collision stops the install.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_composite.py`:

```python
"""The composite driver: profiles are data, frameworks do the work."""

import ast

import pytest
from profile_fixtures import dotnet_svelte_repo, package, write

from profiles.composite import CompositeProfile


def _profile(tmp_path, frameworks="[dotnet, sveltekit]", name="test-stack"):
    """A profile is a YAML file. That is the whole point, so tests write one."""
    path = tmp_path / "profile.yaml"
    path.write_text(f"name: {name}\ndescription: a test stack\n"
                    f"frameworks: {frameworks}\n")
    return CompositeProfile(path)


def test_a_profile_is_built_from_its_yaml(tmp_path):
    profile = _profile(tmp_path)
    assert profile.NAME == "test-stack"
    assert profile.description == "a test stack"
    assert [f.NAME for f in profile.frameworks] == ["dotnet", "sveltekit"]


def test_an_unknown_framework_in_a_profile_fails_loudly(tmp_path):
    with pytest.raises(SystemExit) as error:
        _profile(tmp_path, frameworks="[dotnet, cobol]")
    assert "cobol" in str(error.value)


def test_matching_requires_every_declared_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    profile = _profile(tmp_path)

    package(repo, "web", {"build": "x"})          # sveltekit only
    assert not profile.matches(repo)

    dotnet_svelte_repo(repo)                      # now both
    assert profile.matches(repo)


def test_a_single_framework_profile_matches_on_its_own(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    package(repo, "web", {"build": "x"})
    assert _profile(tmp_path, frameworks="[sveltekit]").matches(repo)


def test_detect_fills_repo_facts_and_every_framework_section(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "CLAUDE.md", "# rules\n")

    facts = _profile(tmp_path).detect(repo)

    assert facts.profile == "test-stack"
    assert facts.conventions == ["CLAUDE.md"]
    assert facts.of("dotnet").solution == "Fixture.sln"
    assert [f.directory for f in facts.of("sveltekit").frontends] == ["apps/web"]


def test_describe_concatenates_every_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    lines = "\n".join(profile.describe(profile.detect(repo)))
    assert "Fixture.sln" in lines
    assert "apps/web" in lines


def test_generate_writes_the_blocks_module(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo)

    generated = repo / "adws" / "adw_modules" / "quality_blocks.py"
    assert generated.is_file()
    assert str(generated) in report.files
    ast.parse(generated.read_text())
    assert "PLACEHOLDER" not in generated.read_text()


def test_the_blocks_come_from_both_frameworks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    names = [b.name for b in profile.generate(profile.detect(repo), repo).blocks]
    assert "build-sln" in names          # dotnet
    assert "check-web" in names          # sveltekit


def test_the_header_records_what_was_detected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    profile.generate(profile.detect(repo), repo)
    text = (repo / "adws" / "adw_modules" / "quality_blocks.py").read_text()
    assert "Fixture.sln" in text
    assert "apps/web" in text


def test_unresolved_notes_are_collected_from_every_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, integration=False, frontends=[])
    package(repo, "web", {"dev": "vite"})          # no check/test/build/lint
    profile = _profile(tmp_path)
    report = profile.generate(profile.detect(repo), repo, write=False)
    joined = " ".join(report.unresolved)
    assert "integration-tests" in joined           # from dotnet
    assert "web" in joined                         # from sveltekit


def test_a_dry_run_writes_nothing_but_still_reports(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo, write=False)

    assert report.files == []
    assert report.blocks
    assert not (repo / "adws" / "adw_modules" / "quality_blocks.py").exists()


def test_two_frameworks_emitting_the_same_block_name_stop_the_install(tmp_path,
                                                                     monkeypatch):
    """A silently dropped block is a check that stopped running."""
    from profiles.facts import QualityBlock
    from profiles.frameworks import sveltekit

    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    monkeypatch.setattr(sveltekit, "blocks", lambda facts, repo_facts: (
        [QualityBlock(name="build-sln", area="frontend", operation="build",
                      argv=["npm", "run", "build"])], []))

    profile = _profile(tmp_path)
    with pytest.raises(SystemExit) as error:
        profile.generate(profile.detect(repo), repo, write=False)
    assert "build-sln" in str(error.value)


def test_gate_modules_lists_what_the_declared_frameworks_need_stamped(tmp_path):
    assert _profile(tmp_path).gate_modules() == ["gates_dotnet", "gates_sveltekit"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_composite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.composite'`.

- [ ] **Step 3: Write the driver**

Create `.claude/skills/sssf/templates/profiles/composite.py`:

```python
"""The generic profile driver.

A profile is a YAML file naming the frameworks a stack is made of. This class
is what turns that list into a working factory: it matches when every declared
framework matches, detects by asking each in turn, and generates by
concatenating what each returns.

It knows nothing about any technology. That is the property that makes adding
a stack cheap - `dotnet-angular` is a four-line YAML file, not a package - and
it is worth protecting: if a `if framework.NAME == "dotnet"` ever appears in
this file, the design has failed and the special case belongs in the framework.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import yaml

from . import emit, probes
from .facts import GenerationReport, ProfileFacts
from .frameworks import get as get_framework

BLOCKS_RELATIVE = "adws/adw_modules/quality_blocks.py"


class CompositeProfile:
    """One profile.yaml, and the frameworks it declares."""

    def __init__(self, path: Path):
        self.path = Path(path)
        config = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        self.NAME: str = config.get("name", self.path.parent.name)
        self.description: str = config.get("description", "")
        # get_framework raises SystemExit naming the unknown one, so a typo in
        # a profile fails at load with a readable message rather than an
        # AttributeError somewhere inside generation.
        self.frameworks = [get_framework(n) for n in (config.get("frameworks") or [])]

    # ── detection ────────────────────────────────────────────────────────
    def matches(self, root) -> bool:
        """Every declared framework must be present.

        A solution alone is a .NET repo; a SvelteKit package alone is a Node
        repo. Only the pair implies the conventions a paired profile's gates
        and blocks are built around.
        """
        root = Path(root)
        return bool(self.frameworks) and all(f.matches(root) for f in self.frameworks)

    def detect(self, root) -> ProfileFacts:
        root = Path(root)
        runner, recipes, recipes_source = probes.task_runner(root)
        facts = ProfileFacts(
            profile=self.NAME,
            repo_root=str(root),
            task_runner=runner,
            recipes=recipes,
            recipes_source=recipes_source,
            default_branch=probes.default_branch(root),
            conventions=probes.conventions(root),
        )
        for framework in self.frameworks:
            facts.frameworks[framework.NAME] = framework.detect(root)
        return facts

    def describe(self, facts: ProfileFacts) -> list[str]:
        lines: list[str] = []
        for framework in self.frameworks:
            lines += framework.describe(facts.of(framework.NAME))
        return lines

    def gate_modules(self) -> list[str]:
        """Gate files to stamp: one per declared framework that has any."""
        return sorted({f.GATE_MODULE for f in self.frameworks if f.GATE_MODULE})

    # ── generation ───────────────────────────────────────────────────────
    def _collect(self, facts: ProfileFacts):
        blocks, unresolved = [], []
        for framework in self.frameworks:
            emitted, notes = framework.blocks(facts.of(framework.NAME), facts)
            blocks += emitted
            unresolved += notes

        clashes = sorted(name for name, count in Counter(b.name for b in blocks).items()
                         if count > 1)
        if clashes:
            raise SystemExit(
                f"profile {self.NAME!r}: two frameworks emitted the same block "
                f"name(s): {', '.join(clashes)}. Block names are how the trace "
                f"tells checks apart, so this is stopped rather than resolved by "
                f"dropping one.")
        return blocks, unresolved

    def generate(self, facts: ProfileFacts, root, write: bool = True) -> GenerationReport:
        """Facts in, files out. `write=False` is the --doctor dry run."""
        blocks, unresolved = self._collect(facts)
        written: list[str] = []
        if write:
            emit.write_file(
                root, BLOCKS_RELATIVE,
                emit.render_blocks_module(
                    facts, blocks, summary=[f"  {line}" for line in self.describe(facts)]),
                written)
        return GenerationReport(profile=self.NAME, files=written, blocks=blocks,
                                unresolved=unresolved)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_composite.py -v`
Expected: PASS — 13 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_composite.py .claude/skills/sssf/templates/profiles/composite.py
git commit -m "feat(profiles): the generic driver that composes frameworks"
```

---

## Task 11: The `dotnet-svelte` profile and the profile registry

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/dotnet_svelte/profile.yaml`
- Create: `.claude/skills/sssf/templates/profiles/registry.py`
- Test: `tests/test_profile_registry.py`

**Scene:** the payoff. The profile is four lines. The registry finds every `*/profile.yaml` beside it, so adding `dotnet_angular/profile.yaml` registers a new stack with no code change anywhere.

Auto-detection must refuse to choose when two profiles both match: silently picking one would wire a repo to the wrong stack, and the operator can always pass `--profile`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_profile_registry.py`:

```python
"""Profile discovery: a directory with a profile.yaml is a profile."""

import pytest
from profile_fixtures import dotnet_svelte_repo, package

from profiles import registry


def test_the_dotnet_svelte_profile_is_discovered():
    assert "dotnet-svelte" in registry.names()


def test_a_profile_is_discovered_from_its_yaml_alone():
    """No __init__.py, no Python: a directory with a profile.yaml is enough."""
    from pathlib import Path
    directory = Path(registry.get("dotnet-svelte").path).parent
    assert sorted(p.name for p in directory.iterdir()) == ["profile.yaml"]


def test_the_profile_declares_its_frameworks():
    profile = registry.get("dotnet-svelte")
    assert [f.NAME for f in profile.frameworks] == ["dotnet", "sveltekit"]


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


def test_half_a_stack_does_not_match(tmp_path):
    package(tmp_path, "web", {"build": "x"})
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


def test_the_profile_yaml_declares_no_repository_specific_paths():
    """The design rule, on the file most likely to break it."""
    from pathlib import Path
    text = Path(registry.get("dotnet-svelte").path).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/web", "apps/admin", "test-api"):
        assert forbidden not in text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_profile_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'profiles.registry'`.

- [ ] **Step 3: Write the profile**

Create `.claude/skills/sssf/templates/profiles/dotnet_svelte/profile.yaml`:

```yaml
# A profile names the frameworks a stack is made of. Nothing else: the
# frameworks own their own markers, recipes, gates and prompt fragments, so
# pairing .NET with a different frontend is a file exactly this size.
name: dotnet-svelte
description: ASP.NET Core + EF Core + SvelteKit repositories.
frameworks: [dotnet, sveltekit]
```

- [ ] **Step 4: Write the registry**

Create `.claude/skills/sssf/templates/profiles/registry.py`:

```python
"""Profile discovery, lookup, and auto-detection.

The one module install.py imports. Profiles are found by scanning for
`*/profile.yaml` next to this file, so adding a stack means adding a directory
with a YAML file in it - no registration, no import, no core change.
"""

from __future__ import annotations

from pathlib import Path

from .composite import CompositeProfile

PROFILES_DIR = Path(__file__).resolve().parent


def _discover() -> list[CompositeProfile]:
    return sorted((CompositeProfile(path)
                   for path in PROFILES_DIR.glob("*/profile.yaml")),
                  key=lambda profile: profile.NAME)


def all_profiles() -> list[CompositeProfile]:
    # Re-read on every call rather than caching at import: an installer runs
    # once, and a stale cache would be a confusing way to lose a profile
    # somebody just added.
    return _discover()


def names() -> list[str]:
    return [profile.NAME for profile in all_profiles()]


def get(name: str) -> CompositeProfile:
    for profile in all_profiles():
        if profile.NAME == name:
            return profile
    raise SystemExit(f"unknown profile {name!r} - available: {', '.join(names())}")


def detect_all(root) -> list[str]:
    """Every profile that claims this repo."""
    root = Path(root)
    return [profile.NAME for profile in all_profiles() if profile.matches(root)]


def select(root) -> CompositeProfile | None:
    """The profile to apply, or None when none matches.

    Refuses to choose between two matches. Wiring a repo to the wrong stack
    produces a factory whose checks all pass because none of them run anything
    real - the exact failure this mechanism exists to prevent - so ambiguity
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
Expected: PASS — 11 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/test_profile_registry.py .claude/skills/sssf/templates/profiles/registry.py .claude/skills/sssf/templates/profiles/dotnet_svelte/
git commit -m "feat(profiles): dotnet-svelte as four lines of YAML, and discovery"
```

---

## Task 12: `gates_dotnet.py` — the EF Core migration triad

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/gates/gates_dotnet.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_gates_dotnet.py`

**Scene:** an EF Core migration is three files, not one: `20260911_AddThing.cs`, its sibling `20260911_AddThing.Designer.cs`, and the folder's `ApplicationDbContextModelSnapshot.cs`. An agent that writes only the first produces something that *compiles* — and `Database.Migrate()` then silently SKIPS it, because the migration has no model metadata. The break surfaces much later as a `PendingModelChangesWarning` in an integration test, pointing at the wrong change.

This is pure EF Core semantics, so it belongs to the `dotnet` framework and is reused by every profile that declares it.

- [ ] **Step 1: Make the stamped gate modules importable in tests**

Append to `tests/conftest.py`:

```python
# A framework's gate module is stamped INTO adw_modules at install time, and it
# imports its siblings relatively (`from .data_types import ...`). Extending the
# package's search path is what lets a test import it under its real stamped
# name, with its real package context, straight from the source - so what the
# tests exercise is the file that ships, not a copy of it.
import adw_modules  # noqa: E402

PROFILE_GATES_SRC = TEMPLATES / "profiles" / "gates"

if str(PROFILE_GATES_SRC) not in adw_modules.__path__:
    adw_modules.__path__.append(str(PROFILE_GATES_SRC))
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_gates_dotnet.py`:

```python
"""ef_migration_triad: a pure function over a changeset."""

from types import SimpleNamespace

from adw_modules.data_types import BuildOutput
from adw_modules.gates_dotnet import ef_migration_triad

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
    assert ef_migration_triad(_envelope([MIGRATION, SNAPSHOT]), _run(tmp_path)).passed


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

Run: `uv run pytest tests/test_gates_dotnet.py -v`
Expected: FAIL — `No module named 'adw_modules.gates_dotnet'`.

- [ ] **Step 4: Write the gate module**

Create `.claude/skills/sssf/templates/profiles/gates/gates_dotnet.py`:

```python
"""Gates that come with .NET.

STAMPED into adws/adw_modules/ by `install.py`, which is why the imports below
are relative: this file is part of that package once it lands.

Every rule here is a fact about a FRAMEWORK, never about a repository. EF Core
writes three files per migration - that is true in every repo that uses it, and
in none that does not.
"""

from __future__ import annotations

from pathlib import Path

from .data_types import EnvelopeBase, GateReport
from .utils import claimed_files

# EF Core's own file convention, and the only thing this gate knows.
MIGRATIONS_DIR = "Migrations"
DESIGNER_SUFFIX = ".Designer.cs"
SNAPSHOT_SUFFIX = "ModelSnapshot.cs"


def ef_migration_triad(envelope: EnvelopeBase, run) -> GateReport:
    """An EF Core migration is three files. Two of them are easy to forget.

    Without the sibling `.Designer.cs`, `Database.Migrate()` SKIPS the migration
    rather than failing - the schema silently does not change. Without an
    updated `*ModelSnapshot.cs`, the next migration is generated against a stale
    model and re-emits changes that are already applied. Both break far from
    where they were caused, which is exactly what a gate is for.

    The designer is checked on DISK, not in the changeset: editing an existing
    migration legitimately leaves its designer untouched. The snapshot is
    checked in the CHANGESET, because a migration that alters the model and
    leaves the snapshot alone is wrong however old the migration is.
    """
    report = GateReport()
    changed = claimed_files(envelope, run)
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
                     f"{name} has no {DESIGNER_SUFFIX} - EF Core skips a migration "
                     f"with no model metadata instead of failing")

        snapshots = [f for f in changed
                     if f.startswith(f"{directory}/") and f.endswith(SNAPSHOT_SUFFIX)]
        report.check(f"{directory}/*{SNAPSHOT_SUFFIX}", bool(snapshots),
                     f"snapshot updated: {snapshots[0]}" if snapshots else
                     f"{name} changes the model but no model snapshot in "
                     f"{directory}/ was updated - the next migration will be "
                     f"generated against a stale model")
    return report
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gates_dotnet.py -v`
Expected: PASS — 11 passed.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_gates_dotnet.py .claude/skills/sssf/templates/profiles/gates/
git commit -m "feat(gates): ef_migration_triad, the three-file EF Core change"
```

---

## Task 13: `gates_sveltekit.py` — public variables and the CSP

**Files:**
- Create: `.claude/skills/sssf/templates/profiles/gates/gates_sveltekit.py`
- Test: `tests/test_gates_sveltekit.py`

**Scene:** two gates, both factories, because *which* directory and *which* example file are discovered facts. SvelteKit exposes only `PUBLIC_`-prefixed variables and Vite only `VITE_`-prefixed ones — a frontend file reading `PUBLIC_API_URL` that no example file declares builds fine on the author's machine and gives everyone else `undefined` at runtime. And a SvelteKit app with a Content-Security-Policy blocks any origin the policy omits, silently, in the browser.

These gates are SvelteKit's, not "the frontend's": an Angular repo configures neither, so `gates_angular.py` will bring an `environment.ts` gate instead. That is the whole reason gates belong to frameworks.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_gates_sveltekit.py`:

```python
"""The SvelteKit gates: public env variables, and the content-security policy."""

from types import SimpleNamespace

from adw_modules.data_types import BuildOutput
from adw_modules.gates_sveltekit import env_example_sync, sveltekit_csp

PREFIXES = ["PUBLIC_", "VITE_"]
HOOKS = "apps/web/src/hooks.server.ts"


def _run(tmp_path):
    return SimpleNamespace(repo_root=str(tmp_path), cfg=SimpleNamespace())


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


def _source(tmp_path, relative, text):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return relative


# ── env_example_sync ─────────────────────────────────────────────────────────

def test_no_frontend_change_means_no_checks(tmp_path):
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path))
    assert report.passed
    assert report.checks == []


def test_a_public_variable_absent_from_the_example_fails(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "PUBLIC_OTHER=\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "PUBLIC_API_URL" in report.violations[0]


def test_a_public_variable_present_in_the_example_passes(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "PUBLIC_API_URL=http://x\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_vite_prefixed_variables_are_checked_too(tmp_path):
    source = _source(tmp_path, "apps/web/src/main.ts",
                     "const key = import.meta.env.VITE_MAP_KEY;\n")
    _source(tmp_path, "apps/web/.env.example", "")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "VITE_MAP_KEY" in gate(_envelope([source]), _run(tmp_path)).violations[0]


def test_a_private_variable_is_not_this_gate_s_business(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/db.ts",
                     "import { DATABASE_URL } from '$env/static/private';\n")
    _source(tmp_path, "apps/web/.env.example", "")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_each_frontend_is_checked_against_its_own_example(tmp_path):
    _source(tmp_path, "apps/web/.env.example", "")
    _source(tmp_path, "apps/admin/.env.example", "")
    source = _source(tmp_path, "apps/admin/src/x.ts", "const u = PUBLIC_ADMIN_URL;\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example"),
                             ("apps/admin", "apps/admin/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    assert len(report.checks) == 1
    assert "apps/admin/.env.example" in report.violations[0]


def test_a_non_source_file_is_not_scanned(tmp_path):
    source = _source(tmp_path, "apps/web/README.md",
                     "set PUBLIC_DOCS_URL before running\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_a_deleted_source_file_does_not_crash_the_gate(tmp_path):
    """changed_files includes deletions; the file is gone from disk."""
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope(["apps/web/src/gone.ts"]), _run(tmp_path)).passed


def test_a_missing_example_file_is_reported_not_raised(tmp_path):
    source = _source(tmp_path, "apps/web/src/a.ts", "const u = PUBLIC_API_URL;\n")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert not gate(_envelope([source]), _run(tmp_path)).passed


def test_the_gate_has_a_readable_name_for_the_trace():
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "env_example_sync" in gate.__name__


# ── sveltekit_csp ────────────────────────────────────────────────────────────

def test_csp_is_silent_when_the_frontend_did_not_change(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path)).checks == []


def test_a_new_external_origin_requires_the_hooks_file_to_change(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")

    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "tiles.example.com" in report.violations[0]


def test_an_origin_already_in_the_policy_is_fine(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"img-src https://tiles.example.com\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_changing_the_hooks_file_satisfies_the_gate(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source, HOOKS]), _run(tmp_path)).passed


def test_localhost_is_not_an_external_origin(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/dev.ts",
                     "fetch('http://localhost:5173/x');\n"
                     "fetch('http://127.0.0.1:8080/y');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_the_hooks_file_itself_is_not_scanned_for_origins(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"connect-src https://api.example.com\";\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([HOOKS]), _run(tmp_path)).checks == []


def test_the_csp_gate_has_a_readable_name_for_the_trace():
    assert "sveltekit_csp" in sveltekit_csp([("apps/web", HOOKS)]).__name__
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_gates_sveltekit.py -v`
Expected: FAIL — `No module named 'adw_modules.gates_sveltekit'`.

- [ ] **Step 3: Write the gate module**

Create `.claude/skills/sssf/templates/profiles/gates/gates_sveltekit.py`:

```python
"""Gates that come with SvelteKit.

STAMPED into adws/adw_modules/, so the imports are relative.

Both are factories: the rules are SvelteKit's, but which directories and files
they apply to is discovered at install time and baked into the generated
wiring. That split is what keeps a framework rule from becoming a repository
rule.
"""

from __future__ import annotations

import re
from pathlib import Path

from .data_types import EnvelopeBase, GateReport
from .utils import claimed_files, read_text

# Files worth scanning for references. A README that mentions a variable is
# documentation, not a dependency on it.
SOURCE_SUFFIXES = {".ts", ".js", ".mjs", ".cjs", ".svelte", ".tsx", ".jsx"}

ORIGIN = re.compile(r"https?://[A-Za-z0-9.\-]+(?::\d+)?")

# A development host is not an origin a production policy has to allow.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


def _sources(changed: list[str], directory: str, exclude: str = "") -> list[str]:
    prefix = directory.rstrip("/") + "/"
    return [f for f in changed
            if f.startswith(prefix) and f != exclude
            and Path(f).suffix in SOURCE_SUFFIXES]


def env_example_sync(pairs: list[tuple[str, str]], prefixes: list[str]):
    """Gate factory: a public variable a frontend reads must be in its example file.

    `pairs` is (frontend directory, its example file) and `prefixes` the build
    tools' public-variable conventions - SvelteKit's `PUBLIC_`, Vite's `VITE_`.
    All three are discovered at install time, which is what keeps this gate a
    framework rule rather than one repository's rule.

    It checks every public variable the changed files reference, not only newly
    added ones. Deriving "newly added" needs a diff and gives a weaker answer:
    a variable that was missing from the example three commits ago is just as
    broken for the next person who clones.
    """
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in prefixes)
                         + r")[A-Z0-9_]+\b")

    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = claimed_files(envelope, run)
        for directory, example in pairs:
            sources = _sources(changed, directory)
            if not sources:
                continue
            declared = read_text(Path(run.repo_root) / example)
            referenced = set()
            for source in sources:
                referenced |= set(pattern.findall(read_text(Path(run.repo_root) / source)))
            for name in sorted(referenced):
                present = name in declared
                report.check(f"{name} in {example}", present,
                             "declared" if present else
                             f"{name} is read by {directory} but {example} does not "
                             f"declare it - the build works here and nowhere else")
        return report

    gate.__name__ = f"env_example_sync({len(pairs)} frontend(s))"
    return gate


def sveltekit_csp(pairs: list[tuple[str, str]]):
    """Gate factory: a new external origin requires the CSP to be updated.

    `pairs` is (frontend directory, the file declaring its policy). Only
    frontends where detection found an actual policy are wired, because a repo
    with no CSP would see this fire on every external URL it ever adds - and a
    gate that cries wolf is deleted along with the ones that do not.

    The failure it prevents is browser-side and silent: the request is blocked,
    nothing throws on the server, and the feature simply does not work.
    """
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = claimed_files(envelope, run)
        for directory, policy_file in pairs:
            sources = _sources(changed, directory, exclude=policy_file)
            if not sources:
                continue
            policy = read_text(Path(run.repo_root) / policy_file)
            origins = set()
            for source in sources:
                origins |= set(ORIGIN.findall(read_text(Path(run.repo_root) / source)))
            unknown = sorted(o for o in origins
                             if not any(host in o for host in LOCAL_HOSTS)
                             and o not in policy)
            if not unknown:
                continue
            report.check(policy_file, policy_file in changed,
                         "updated alongside the new origin(s)"
                         if policy_file in changed else
                         f"{len(unknown)} origin(s) not in the CSP and {policy_file} "
                         f"was not changed: {', '.join(unknown[:3])} - the browser "
                         f"will block these and nothing will throw on the server")
        return report

    gate.__name__ = f"sveltekit_csp({len(pairs)} frontend(s))"
    return gate
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_gates_sveltekit.py -v`
Expected: PASS — 17 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_gates_sveltekit.py .claude/skills/sssf/templates/profiles/gates/gates_sveltekit.py
git commit -m "feat(gates): sveltekit public-variable and CSP gates"
```

---

## Task 14: Generate the gate wiring, and load it from core

**Files:**
- Modify: `.claude/skills/sssf/templates/profiles/composite.py`
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/gates.py`
- Test: `tests/test_composite.py` (append), `tests/test_gates_doc_policy.py` (append)

**Scene:** the gates from Tasks 12 and 13 are dead code until something puts them in a gate list. Two of them are factories needing discovered facts, so the wiring itself is generated — and core has to load it without knowing any framework exists.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_composite.py`:

```python
def test_generate_writes_the_gates_module(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "apps/web/.env.example", "PUBLIC_X=\n")
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo)

    generated = repo / "adws" / "adw_modules" / "profile_gates.py"
    assert generated.is_file()
    assert str(generated) in report.files
    ast.parse(generated.read_text())


def test_the_wired_gates_come_from_every_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "apps/web/.env.example", "PUBLIC_X=\n")
    write(repo, "apps/web/src/hooks.server.ts", "// csp\n")
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo, write=False)

    assert report.gates == ["ef_migration_triad", "env_example_sync", "sveltekit_csp"]


def test_a_gate_whose_fact_is_absent_is_not_wired(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    report = profile.generate(profile.detect(repo), repo, write=False)
    assert report.gates == ["ef_migration_triad"]


def test_the_generated_wiring_builds_real_callables(tmp_path):
    """Execute the generated module against the real gate factories."""
    from adw_modules import gates_dotnet, gates_sveltekit

    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "apps/web/.env.example", "PUBLIC_X=\n")
    profile = _profile(tmp_path)
    profile.generate(profile.detect(repo), repo)

    text = (repo / "adws" / "adw_modules" / "profile_gates.py").read_text()
    namespace = {"ef_migration_triad": gates_dotnet.ef_migration_triad,
                 "env_example_sync": gates_sveltekit.env_example_sync,
                 "sveltekit_csp": gates_sveltekit.sveltekit_csp}
    body = "\n".join(line for line in text.splitlines()
                     if not line.startswith("from ."))
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
    def raise_unrelated():
        raise ModuleNotFoundError("No module named 'missing_thing'", name="missing_thing")

    monkeypatch.setattr(gates, "_import_profile_gates", raise_unrelated)
    with pytest.raises(ModuleNotFoundError):
        gates.profile_gates()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_composite.py tests/test_gates_doc_policy.py -v`
Expected: FAIL — `report.gates` is empty and `gates._import_profile_gates` does not exist.

- [ ] **Step 3: Add the loader to core `gates.py`**

Append to `.claude/skills/sssf/templates/adws/adw_modules/gates.py`:

```python
def _import_profile_gates() -> list | None:
    """The generated gate list, or None when no profile wrote one.

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

In `composite.py`, add the constant beside `BLOCKS_RELATIVE`:

```python
GATES_RELATIVE = "adws/adw_modules/profile_gates.py"
```

Add the collection method beside `_collect`:

```python
    def _wirings(self, facts: ProfileFacts):
        wirings = []
        for framework in self.frameworks:
            wirings += framework.gate_wiring(facts.of(framework.NAME))
        return wirings
```

and extend `generate` to write the second file:

```python
    def generate(self, facts: ProfileFacts, root, write: bool = True) -> GenerationReport:
        """Facts in, files out. `write=False` is the --doctor dry run."""
        blocks, unresolved = self._collect(facts)
        wirings = self._wirings(facts)
        # Rendered unconditionally, written only when asked. render_* runs an
        # ast.parse self-check, so a dry run PROVES the generated modules would
        # import - which is the single most useful thing --doctor can do, and
        # it could not do it while rendering lived inside `if write:`.
        blocks_text = emit.render_blocks_module(
            facts, blocks, summary=[f"  {line}" for line in self.describe(facts)])
        gates_text = emit.render_gates_module(facts, wirings)
        written: list[str] = []
        if write:
            emit.write_file(root, BLOCKS_RELATIVE, blocks_text, written)
            emit.write_file(root, GATES_RELATIVE, gates_text, written)
        return GenerationReport(profile=self.NAME, files=written, blocks=blocks,
                                gates=[w.name for w in wirings], unresolved=unresolved)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_composite.py tests/test_gates_doc_policy.py -v`
Expected: PASS — 17 in test_composite.py and 19 in test_gates_doc_policy.py.

- [ ] **Step 6: Commit**

```bash
git add tests/test_composite.py tests/test_gates_doc_policy.py .claude/skills/sssf/templates/profiles/composite.py .claude/skills/sssf/templates/adws/adw_modules/gates.py
git commit -m "feat(profiles): generate gate wiring and load it from core gates"
```

---

## Task 15: Wire the gates into every build phase

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_build.py`, `adw_build_review.py`, `adw_build_test.py`, `adw_plan_build.py`, `adw_plan_build_test.py`, `adw_plan_build_test_quality.py`, `adw_simple_sdlc.py`
- Test: `tests/test_gate_wiring.py`

**Scene:** a gate nobody calls is a comment. The rule that decides where these belong is simple and checkable: **every agent call whose `output_type` is `BuildOutput` is a phase that changed code**, and those are exactly the phases whose claims `doc_policy` and the stack gates check. A test enforces the rule across the whole ADW directory, so an ADW written next month cannot quietly skip it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gate_wiring.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_gate_wiring.py -v`
Expected: FAIL — every build phase is listed as missing both gates.

- [ ] **Step 3: Wire the gates**

In each of the seven ADW scripts, find every `AgentCall(output_type=BuildOutput, ...)` and extend its `gates=` list. There are two existing shapes:

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

There are **13** such calls today: `adw_build.py` 1, `adw_build_review.py` 2, `adw_build_test.py` 2, `adw_plan_build.py` 1, `adw_plan_build_test.py` 2, `adw_plan_build_test_quality.py` 2, `adw_simple_sdlc.py` 3. Use the test to find them rather than trusting that tally — run it after each file and watch the `missing` set shrink.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_gate_wiring.py -v`
Expected: PASS — 5 passed.

- [ ] **Step 5: Confirm nothing else broke**

Run: `uv run pytest tests/ -v`
Expected: PASS — 0 failures.

- [ ] **Step 6: Commit**

```bash
git add tests/test_gate_wiring.py .claude/skills/sssf/templates/adws/adw_build.py .claude/skills/sssf/templates/adws/adw_build_review.py .claude/skills/sssf/templates/adws/adw_build_test.py .claude/skills/sssf/templates/adws/adw_plan_build.py .claude/skills/sssf/templates/adws/adw_plan_build_test.py .claude/skills/sssf/templates/adws/adw_plan_build_test_quality.py .claude/skills/sssf/templates/adws/adw_simple_sdlc.py
git commit -m "feat(adws): every code-changing phase runs doc_policy and profile gates"
```

---

## Task 16: The prompt overlay

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/agents.py`
- Modify: `.claude/skills/sssf/templates/prompt_engineering/builder/system.md`
- Modify: `.claude/skills/sssf/templates/profiles/composite.py`
- Create: `.claude/skills/sssf/templates/profiles/prompts/dotnet.md`
- Create: `.claude/skills/sssf/templates/profiles/prompts/sveltekit.md`
- Test: `tests/test_prompt_overlay.py`

**Scene:** the shipped builder prompt tells agents to call `bun`, `uv`, and `pytest` — right for the repo SSSF was written in, wrong for this stack. The overlay replaces that with one fragment per declared framework, plus the list of convention files detection actually found.

Repository standards are **referenced, never restated**: copying `CLAUDE.md` into a prompt duplicates it and then drifts from it, and .NET 10 / C# 14 and Svelte 5 runes post-date most model priors, so pointing at the live file is also the more accurate answer.

Fragments per framework is the same reuse story again — `angular.md` drops in beside `sveltekit.md` and a `dotnet-angular` profile gets the .NET half for free.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_prompt_overlay.py`:

```python
"""The profile overlay: framework fragments, composed per profile."""

from pathlib import Path
from types import SimpleNamespace

from profile_fixtures import dotnet_svelte_repo, write

from adw_modules import agents
from profiles import registry

TEMPLATES = (Path(__file__).resolve().parent.parent
             / ".claude" / "skills" / "sssf" / "templates")
OVERLAY = "adws/adw_data/prompt_engineering/profile_overlay.md"


def _generate(tmp_path, **kwargs):
    dotnet_svelte_repo(tmp_path, **kwargs)
    profile = registry.get("dotnet-svelte")
    profile.generate(profile.detect(tmp_path), tmp_path)
    return (tmp_path / OVERLAY).read_text()


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


def test_every_framework_that_declares_an_overlay_has_the_file():
    from profiles import frameworks
    for name in frameworks.names():
        overlay = frameworks.get(name).OVERLAY
        if overlay:
            assert (TEMPLATES / "profiles" / "prompts" / overlay).is_file(), name


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
    profile = registry.get("dotnet-svelte")
    report = profile.generate(profile.detect(tmp_path), tmp_path)
    assert str(tmp_path / OVERLAY) in [str(Path(f)) for f in report.files]


def test_the_overlay_contains_a_fragment_per_declared_framework(tmp_path):
    text = _generate(tmp_path)
    assert "EF Core" in text           # from dotnet.md
    assert "runes" in text             # from sveltekit.md


def test_the_overlay_references_conventions_rather_than_restating_them(tmp_path):
    dotnet_svelte_repo(tmp_path)
    write(tmp_path, "CLAUDE.md", "NEVER use var in C#.\n")
    write(tmp_path, ".github/instructions/csharp.instructions.md", "# c#\n")
    profile = registry.get("dotnet-svelte")
    profile.generate(profile.detect(tmp_path), tmp_path)

    text = (tmp_path / OVERLAY).read_text()

    assert "CLAUDE.md" in text
    assert ".github/instructions/" in text
    assert "NEVER use var" not in text        # the CONTENT is never copied in


def test_the_overlay_names_the_detected_task_runner(tmp_path, monkeypatch):
    from profiles import probes
    monkeypatch.setattr(probes, "_summary", lambda runner, root: None)
    text = _generate(tmp_path, justfile_text="test-unit:\n    dotnet test\n")
    assert "just" in text


def test_the_overlay_says_so_when_there_are_no_conventions(tmp_path):
    text = _generate(tmp_path)
    assert "no convention files" in text.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_prompt_overlay.py -v`
Expected: FAIL — the placeholder is absent and `agents.profile_overlay` does not exist.

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

- [ ] **Step 5: Write the framework fragments**

Create `.claude/skills/sssf/templates/profiles/prompts/dotnet.md`:

```markdown
### .NET

- **An EF Core migration is three files, not one.** The migration, its sibling
  `.Designer.cs`, and the folder's `*ModelSnapshot.cs`. Generate migrations with
  the EF tooling rather than writing the file by hand — a migration with no
  Designer file is silently SKIPPED by `Database.Migrate()`, so the schema does
  not change and nothing errors.
- **Judge success by exit status**, never by scanning output for the word
  "error". A build that prints warnings and exits 0 succeeded.
```

Create `.claude/skills/sssf/templates/profiles/prompts/sveltekit.md`:

```markdown
### SvelteKit

- **Svelte 5 uses runes.** `$state`, `$derived`, `$effect`, `$props` — not
  `writable`/`readable` stores and not `export let`. Both spellings still work,
  which is why this is worth saying: a legacy-style component will run, and will
  be the odd one out forever.
- **Only prefixed environment variables reach the browser.** SvelteKit exposes
  `PUBLIC_*` and Vite exposes `VITE_*`. Adding one means adding it to the
  frontend's example env file in the same change.
```

- [ ] **Step 6: Compose and write the overlay**

In `composite.py`, add beside the other constants:

```python
OVERLAY_RELATIVE = "adws/adw_data/prompt_engineering/profile_overlay.md"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

NO_CONVENTIONS = (
    "This repository has no convention files (no CLAUDE.md, AGENTS.md, or\n"
    "instructions directory were found), so there is nothing extra to read.\n"
    "Follow the patterns in the code you are editing.")
```

and this method:

```python
    def render_overlay(self, facts: ProfileFacts) -> str:
        """One fragment per declared framework, plus what is true of this repo.

        Convention files are LISTED, never inlined. Copying a repo's standards
        into a prompt duplicates them and then drifts from them - and the live
        file is the one the humans keep correct.
        """
        parts = ["## Stack notes", ""]
        for framework in self.frameworks:
            if not framework.OVERLAY:
                continue
            fragment = PROMPTS_DIR / framework.OVERLAY
            if fragment.is_file():
                parts += [fragment.read_text(encoding="utf-8").strip(), ""]

        parts += ["### Commands", ""]
        if facts.task_runner:
            parts.append(
                f"This repository drives its commands through `{facts.task_runner}`. "
                f"Prefer a recipe over a raw command when one exists - "
                f"`{facts.task_runner} --list` shows them.")
        else:
            parts.append("This repository has no task runner. Use each toolchain "
                         "directly, as the generated quality blocks do.")

        parts += ["", "### This repository's own standards", ""]
        if facts.conventions:
            parts.append("Read these before you change anything. They are the rules "
                         "this team already agreed on, and they win over anything "
                         "above:")
            parts.append("")
            parts += [f"- `{c}`" for c in facts.conventions]
        else:
            parts.append(NO_CONVENTIONS)
        return "\n".join(parts) + "\n"
```

and add the third write inside `generate`, after the gates write:

```python
            emit.write_file(root, OVERLAY_RELATIVE, self.render_overlay(facts), written)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_prompt_overlay.py -v`
Expected: PASS — 10 passed.

- [ ] **Step 8: Commit**

```bash
git add tests/test_prompt_overlay.py .claude/skills/sssf/templates/adws/adw_modules/agents.py .claude/skills/sssf/templates/prompt_engineering/builder/system.md .claude/skills/sssf/templates/profiles/prompts/ .claude/skills/sssf/templates/profiles/composite.py
git commit -m "feat(prompts): a per-framework overlay that references, never restates"
```

---

## Task 17: `install.py --profile`

**Files:**
- Modify: `.claude/skills/sssf/scripts/install.py`
- Test: `tests/test_install_profile.py`

**Scene:** everything so far is inert until the installer runs it. `install.py` gains three flags and one new stage: after stamping the base factory, select a profile (explicitly, or by unambiguous detection), stamp the gate modules its frameworks declare, generate the three files, and print what it wired.

Two constraints carried over from Part A: **every line this file prints must be ASCII**, because the console it prints to may be cp1252 and a `UnicodeEncodeError` here would kill the install; and the report must say what it could *not* resolve as loudly as what it could.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_install_profile.py`:

```python
"""install.py --profile: stamp a factory that is wired to this repo."""

import subprocess
import sys
from pathlib import Path

from profile_fixtures import CSPROJ_APP, dotnet_svelte_repo, package, sln, write

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
        "dotnet_gates": modules / "gates_dotnet.py",
        "sveltekit_gates": modules / "gates_sveltekit.py",
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


def test_a_gate_module_is_stamped_per_declared_framework(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    assert "ef_migration_triad" in _generated(tmp_path)["dotnet_gates"].read_text()
    assert "sveltekit_csp" in _generated(tmp_path)["sveltekit_gates"].read_text()


def test_no_profile_leaves_the_factory_unwired(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path, "--no-profile")
    assert result.returncode == 0, result.stderr
    for path in _generated(tmp_path).values():
        assert not path.exists(), path
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
    assert _install(tmp_path, "--profile", "dotnet-svelte", "--no-profile").returncode != 0


def test_the_report_names_what_it_could_not_resolve(tmp_path):
    """A repo with no test project must say so at install time."""
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    package(tmp_path, "web", {"build": "vite build"})
    result = _install(tmp_path)
    assert "unresolved" in result.stdout.lower()
    assert "unit-tests" in result.stdout


def test_the_report_lists_the_blocks_with_their_tiers(tmp_path):
    dotnet_svelte_repo(tmp_path)
    result = _install(tmp_path)
    assert "fast" in result.stdout
    assert "full" in result.stdout
    assert "build-sln" in result.stdout


def test_every_line_of_output_is_ascii(tmp_path):
    """The console this prints to may be cp1252; a crash here kills the install."""
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path).stdout.encode("ascii")


def test_installing_twice_is_idempotent(tmp_path):
    dotnet_svelte_repo(tmp_path)
    _install(tmp_path)
    first = _generated(tmp_path)["blocks"].read_text()
    assert _install(tmp_path).returncode == 0
    second = _generated(tmp_path)["blocks"].read_text()
    # the generated file is rewritten from facts, so its blocks are identical
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

PROFILE_GATES_SRC = TEMPLATES / "profiles" / "gates"
```

Add these functions above `main`:

```python
def stamp_profile_gates(profile, root: Path, force: bool,
                        stamped: list, skipped: list) -> None:
    """Stamp one gate module per framework the profile declares.

    Stamped like every other shipped module, which means an existing copy is
    left alone without --force. A gate is code an operator is invited to edit;
    silently overwriting their edit on a re-install would be the one thing this
    installer has never done.
    """
    for module in profile.gate_modules():
        source = PROFILE_GATES_SRC / f"{module}.py"
        if source.is_file():
            stamp(source, root / "adws" / "adw_modules" / f"{module}.py",
                  force, stamped, skipped)


def print_profile_report(profile, facts, report) -> None:
    """What was detected, what was wired, and what could not be.

    ASCII only, deliberately, like the Windows warning below: this is the
    output most likely to be read on a fresh machine with a cp1252 console,
    and a UnicodeEncodeError here would take the install down with it.
    """
    print(f"\nprofile: {report.profile}"
          f"  (frameworks: {', '.join(f.NAME for f in profile.frameworks)})")
    for line in profile.describe(facts):
        print(f"  {line}")
    print(f"  task runner: {facts.task_runner or '(none)'}"
          f"{f' ({len(facts.recipes)} recipes)' if facts.recipes else ''}")
    if facts.recipes_source:
        # A runner that RAN and refused is not the same as one that is absent:
        # the offline parser is then reading a file the runner itself rejects,
        # so every recipe it found may be a command that cannot run.
        print(f"    recipes from: {facts.recipes_source}")
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
        print(f"\nno profile matches this repo (tried: {', '.join(registry.names())})."
              f"\n  quality.py keeps its placeholder blocks - wire them by hand, or "
              f"add a profile.")
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
        print_profile_report(profile, facts, report)

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

- [ ] **Step 4: Update the module docstring**

Replace the `Usage:` and `Stamps:` paragraphs of `install.py`'s docstring with:

```
Usage:
    uv run <skill>/scripts/install.py [--force] [--profile NAME | --no-profile]
    uv run <skill>/scripts/install.py --doctor

Stamps: adws/ (modules + starter ADWs), adws/adw_data/prompt_engineering/
(4 starter agents), adws/adw_sssf_config/sssf.config.yaml, .env.sample,
.gitignore entries. Existing files are skipped unless --force.

Then applies a stack PROFILE: probes the repo, stamps the gate module of every
framework the profile declares, and GENERATES this repo's real quality blocks,
gate wiring, and prompt overlay. With no --profile, the profile whose
frameworks all match is applied; an ambiguous match stops and asks. --doctor
re-probes and reports without writing anything, which is what to run after the
repo's layout changes.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_install_profile.py -v`
Expected: PASS — 11 passed. (`--doctor` gets its own tests in Task 18.)

- [ ] **Step 6: Commit**

```bash
git add tests/test_install_profile.py .claude/skills/sssf/scripts/install.py
git commit -m "feat(install): apply a stack profile and report what it wired"
```

---

## Task 18: `install.py --doctor`

**Files:**
- Modify: `.claude/skills/sssf/scripts/install.py` (only if Task 17's implementation needs correcting)
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
Expected: PASS — 16 passed. Task 17's `main` already implements `--doctor`; these tests exist to hold it to the "writes nothing" contract, which is the only property that makes doctor safe to point at a repository you do not own.

If any fail, the most likely cause is `stamp_profile_gates` or `ensure_gitignore` running on the doctor path. Both must be inside `if not args.doctor:`.

- [ ] **Step 3: Commit**

```bash
git add tests/test_install_profile.py
git commit -m "test(install): doctor re-probes and writes nothing"
```

---

## Task 19: Prove a third framework is cheap

**Files:**
- Create: `tests/fake_framework.py`
- Test: `tests/test_framework_reuse.py`

**Scene:** the acceptance test for this whole architecture. Everything before this point *claims* that adding Angular means one framework module plus a YAML file; this task makes the claim falsifiable.

The test builds a third framework — a pretend `vue` — out of nothing but the public shared pieces (`probes`, `emit`, `facts`), registers it, composes it into a new profile against a fixture repo, and asserts that detection, blocks, gate wiring, and the overlay all work. It must not import `dotnet.py` or `sveltekit.py`, and it must not require an edit to any shared file. If either becomes necessary, the seams are in the wrong place and this task has done its job by saying so.

It is a *test* framework rather than a shipped Angular profile on purpose: shipping a half-tested Angular profile would be worse than shipping none, and the thing under test here is the interface, not Angular.

- [ ] **Step 1: Write the third framework**

Create `tests/fake_framework.py`:

```python
"""A third framework, built from the shared pieces alone.

This is the acceptance test for the framework interface. It imports `probes`,
`emit`, and `facts` - never `dotnet` or `sveltekit` - and it required no change
to any of them. If a future change to the shared layer breaks this file, the
shared layer has grown a framework-specific assumption.

It pretends to be Vue rather than Angular deliberately: Angular is the real
next profile and deserves real detection written against a real repo, not a
stub that makes the tests pass.
"""

from pydantic import Field

from profiles import emit, probes
from profiles.facts import FrameworkFacts, Frontend, GateWiring, ProfileFacts, QualityBlock

NAME = "vue"
GATE_MODULE = ""            # this framework brings no gates
OVERLAY = ""                # nor any prompt guidance

MARKER = "vue"

SCRIPTS = [
    ("test", ["test-{name}"], "test", "test"),
    ("build", ["build-{name}"], "build", "build"),
]


class VueFacts(FrameworkFacts):
    frontends: list[Frontend] = Field(default_factory=list)


def matches(root) -> bool:
    return bool(probes.node_packages(root, MARKER))


def detect(root) -> VueFacts:
    return VueFacts(frontends=probes.node_packages(root, MARKER))


def blocks(facts: VueFacts, repo: ProfileFacts) -> tuple[list[QualityBlock], list[str]]:
    return emit.script_blocks(facts.frontends, repo, SCRIPTS)


def describe(facts: VueFacts) -> list[str]:
    return [f"vue app: {f.directory}" for f in facts.frontends]


def gate_wiring(facts: VueFacts) -> list[GateWiring]:
    return []
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_framework_reuse.py`:

```python
"""Adding a framework must not require touching a shared file."""

import ast
from pathlib import Path

import fake_framework
from profile_fixtures import dotnet_svelte_repo, package

from profiles import frameworks
from profiles.composite import CompositeProfile


def _profile(tmp_path, monkeypatch, frameworks_list="[dotnet, vue]"):
    """Register the third framework and build a profile that declares it."""
    real_get = frameworks.get
    monkeypatch.setattr(
        "profiles.composite.get_framework",
        lambda name: fake_framework if name == "vue" else real_get(name))
    path = tmp_path / "profile.yaml"
    path.write_text(f"name: dotnet-vue\ndescription: a third stack\n"
                    f"frameworks: {frameworks_list}\n")
    return CompositeProfile(path)


def test_the_third_framework_satisfies_the_published_interface():
    frameworks.verify(fake_framework)
    for attribute in frameworks.FRAMEWORK_INTERFACE:
        assert hasattr(fake_framework, attribute), attribute


def test_it_imports_only_the_shared_layer():
    """The claim: a framework composes through probes and emit, not siblings."""
    text = Path(fake_framework.__file__).read_text()
    assert "from profiles import emit, probes" in text
    for sibling in ("dotnet", "sveltekit"):
        assert f"import {sibling}" not in text


def test_a_profile_declaring_it_detects_a_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"test": "vitest run", "build": "vite build"},
            marker="vue")

    profile = _profile(tmp_path, monkeypatch)
    assert profile.matches(repo)

    facts = profile.detect(repo)
    assert facts.of("dotnet").solution == "Fixture.sln"
    assert [f.directory for f in facts.of("vue").frontends] == ["apps/store"]


def test_its_blocks_are_generated_beside_the_other_framework_s(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")

    profile = _profile(tmp_path, monkeypatch)
    report = profile.generate(profile.detect(repo), repo)

    names = [b.name for b in report.blocks]
    assert "build-sln" in names          # from dotnet, unchanged
    assert "build-store" in names        # from the third framework
    ast.parse((repo / "adws" / "adw_modules" / "quality_blocks.py").read_text())


def test_a_framework_with_no_gates_and_no_overlay_composes_cleanly(tmp_path,
                                                                   monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")

    profile = _profile(tmp_path, monkeypatch)
    facts = profile.detect(repo)
    report = profile.generate(facts, repo)

    # only the framework that HAS gates contributes any
    assert report.gates == ["ef_migration_triad"]
    assert profile.gate_modules() == ["gates_dotnet"]
    # and the overlay carries only the fragments that exist
    overlay = (repo / "adws" / "adw_data" / "prompt_engineering"
               / "profile_overlay.md").read_text()
    assert "EF Core" in overlay
    assert "runes" not in overlay


def test_the_describe_lines_reach_the_report(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")
    profile = _profile(tmp_path, monkeypatch)
    assert "vue app: apps/store" in profile.describe(profile.detect(repo))


def test_no_shared_file_needed_a_change_for_this_framework():
    """Recorded as an assertion so a future reviewer sees the claim being made.

    fake_framework.py uses only names that existed before it was written:
    probes.node_packages, emit.script_blocks, and the facts vocabulary. If
    adding it had required a new parameter on any of those, this whole task
    would have failed to prove what it set out to prove.
    """
    from profiles import emit, probes
    assert callable(probes.node_packages)
    assert callable(emit.script_blocks)
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_framework_reuse.py -v`
Expected: PASS — 7 passed, with no change to any file under `templates/profiles/`.

If a change to a shared file IS required, stop and report it before making it. That is the signal this task exists to produce, and the fix belongs in the shared layer's design rather than in this test.

- [ ] **Step 4: Commit**

```bash
git add tests/fake_framework.py tests/test_framework_reuse.py
git commit -m "test(profiles): a third framework composes with no shared-file change"
```

---

## Task 20: Documentation

**Files:**
- Modify: `.claude/skills/sssf/references/config.md`
- Modify: `.claude/skills/sssf/cookbooks/install.md`
- Modify: `.claude/skills/sssf/SKILL.md`
- Modify: `README.md`
- Test: `tests/test_docs_accurate.py`

**Scene:** SSSF's docs are part of the product — the cookbooks are what an agent reads to operate the factory. Three shipped claims are now false: that `quality.py` ships placeholders you must edit by hand, that the test phase is theatre until you do, and that `install.py` takes only `--force`. And one thing is missing entirely: how to add a framework, which is the question this architecture exists to answer.

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


def test_the_install_cookbook_explains_how_to_add_a_framework():
    text = _text("cookbooks", "install.md")
    assert "Adding a framework" in text
    for path in ("frameworks/", "gates/", "prompts/", "profile.yaml"):
        assert path in text, path


def test_the_documented_framework_interface_matches_the_code():
    """The doc lists the names a framework must expose; drift here is a trap."""
    import sys
    sys.path.insert(0, str(SKILL / "templates"))
    from profiles import frameworks

    text = _text("cookbooks", "install.md")
    for name in frameworks.FRAMEWORK_INTERFACE:
        assert name in text, name


def test_the_config_reference_documents_doc_policy():
    text = _text("references", "config.md")
    assert "doc_policy" in text
    assert "require" in text


def test_the_config_reference_documents_the_block_tiers():
    text = _text("references", "config.md")
    assert "quality_blocks.py" in text
    assert "tier" in text


def test_no_document_still_tells_operators_to_edit_quality_py_by_hand():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "replace this echo" not in readme
    assert "quality_blocks.py" in readme


def test_the_skill_describes_profiles_and_frameworks():
    text = _text("SKILL.md").lower()
    assert "profile" in text
    assert "framework" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_docs_accurate.py -v`
Expected: FAIL — none of these strings are in the docs yet.

- [ ] **Step 3: Update `cookbooks/install.md`**

Add these sections after the existing install instructions:

````markdown
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

With no flag, every profile is evaluated. Exactly one match is applied; none
leaves the placeholders in place and says so; more than one stops and asks for
`--profile`, because wiring a repo to the wrong stack produces a factory whose
checks all pass without running anything real.

Applying a profile generates three files and stamps one per framework:

| Path | What it is |
|---|---|
| `adws/adw_modules/quality_blocks.py` | generated: this repo's commands, each with a `fast` or `full` tier |
| `adws/adw_modules/profile_gates.py` | generated: the stack gates, parameterized with what was found |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | generated: stack guidance, injected into prompts that include `{{profile_overlay}}` |
| `adws/adw_modules/gates_<framework>.py` | stamped: the gate implementations, skipped if already present |

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
declaring `@sveltejs/kit`. It is four lines of YAML:

```yaml
name: dotnet-svelte
description: ASP.NET Core + EF Core + SvelteKit repositories.
frameworks: [dotnet, sveltekit]
```

Everything else lives in the two frameworks it names.

## Adding a framework

A **framework** owns one technology; a **profile** names the frameworks a stack
is made of. That split is why pairing .NET with a different frontend costs one
file rather than a fork of the existing profile.

To add one — Angular, React, Django, whatever:

1. **`templates/profiles/frameworks/<name>.py`** — expose the eight names in
   `FRAMEWORK_INTERFACE`: `NAME`, `GATE_MODULE`, `OVERLAY`, `matches`,
   `detect`, `blocks`, `describe`, `gate_wiring`. Copy `sveltekit.py` for a
   frontend or `dotnet.py` for a backend; both are deliberately short, because
   the shared work is already done by `probes` (finding things) and `emit`
   (writing them). A frontend framework is usually `probes.node_packages(root,
   "<its marker dependency>")` for detection and `emit.script_blocks(...)` for
   commands.
2. **`templates/profiles/gates/<GATE_MODULE>.py`** — if it brings gates. This
   file is STAMPED into a target repo's `adw_modules/`, so its imports are
   relative (`from .data_types import ...`). Set `GATE_MODULE = ""` if it
   brings none.
3. **`templates/profiles/prompts/<OVERLAY>`** — if an agent should know
   something about it. Set `OVERLAY = ""` if not.
4. **Register it** in `FRAMEWORKS` in `templates/profiles/frameworks/__init__.py`.
5. **`templates/profiles/<profile_dir>/profile.yaml`** — name it alongside
   whatever it pairs with.

No core module changes, and no other framework changes. A framework must never
import another framework: shared work goes through `probes` and `emit`.

`tests/fake_framework.py` is a worked example — a third framework built from
the shared pieces alone, with `tests/test_framework_reuse.py` asserting that it
needed no change to any shared file.
````

- [ ] **Step 4: Update `references/config.md`**

Add these two sections:

````markdown
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
````

- [ ] **Step 5: Update `SKILL.md`**

Add, in the section describing what an install produces:

```markdown
## Stack profiles

`install.py` probes the repo and generates its quality blocks, gate wiring, and
a prompt overlay from what it finds — so a fresh install runs the repo's real
commands instead of placeholders. `--profile <name>` picks one, `--no-profile`
skips the step, `--doctor` re-probes and reports without writing.

A **framework** module owns one technology (its detection, its commands, its
gates, its prompt guidance); a **profile** is a YAML file naming the frameworks
a stack is made of. Adding a stack is one YAML file; adding a technology is one
framework module. Neither touches a core module. See
`cookbooks/install.md` → "Adding a framework".

A framework may only encode **stack** facts (EF Core writes three files per
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
Expected: PASS — 7 passed.

- [ ] **Step 8: Commit**

```bash
git add tests/test_docs_accurate.py .claude/skills/sssf/references/config.md .claude/skills/sssf/cookbooks/install.md .claude/skills/sssf/SKILL.md README.md
git commit -m "docs: profiles, frameworks, doc_policy, and generated blocks"
```

---

## Task 21: Live verification

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
declaring them), `gates wired: ef_migration_triad, ...`, and the generated and
stamped files listed.

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

- [ ] **Step 4: Measure the overlay against the argv ceiling**

The Part A plan recorded that prompts ride on argv against a ~32KB Windows
limit. The overlay adds to the system prompt, so measure it rather than assume:

```bash
wc -c "$SCRATCH/codec-chat/adws/adw_data/prompt_engineering/profile_overlay.md"
```

Record the number. If the overlay is more than a couple of KB, say so in the
spec note — it moves the deferred argv-ceiling item from theoretical to
scheduled.

- [ ] **Step 5: Confirm the reference repo is still untouched**

```bash
git -C /c/Source/Repos/codec-chat status --porcelain
```

Expected: no output.

- [ ] **Step 6: Append the evidence to the spec**

Add a `## 8b. Verified (Part B)` section to
`docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md` with a
table of the blocks that were wired, their commands and exit codes, the gates
wired, anything reported unresolved, the overlay size, and — if the live run
found a defect the unit tests missed — what it was and what test now encodes it.

- [ ] **Step 7: Write the worked example**

Spec §7 asks for a worked example that walks one install end to end. Append it
to `.claude/skills/sssf/cookbooks/install.md`, under
`## Worked example: an ASP.NET Core + SvelteKit monorepo`, using the **real**
output captured in Steps 1–3 rather than invented output — a worked example
whose numbers nobody ever saw is worth less than none.

It must be documentation, not configuration: it is the one place in this change
allowed to name a specific repository, and no shipped file may reference it.
State that in the section's first line, so the next person reading
`templates/profiles/` does not take the example as a licence.

Structure it as: the command, the abridged report (detection, blocks, gates,
unresolved), a sentence on which blocks came from recipes and which were
composed, and what `--doctor` prints after a frontend is moved.

- [ ] **Step 8: Clean up and commit**

```bash
rm -rf "$SCRATCH"
git add docs/superpowers/specs/2026-09-10-sssf-dotnet-svelte-profile-design.md .claude/skills/sssf/cookbooks/install.md
git commit -m "docs: record Part B live verification and the worked example"
```

---

## Done criteria

- [ ] `uv run pytest tests/ -v` passes with 0 failures (~300 tests: the 85 that
      existed before this plan, plus the per-file counts each task states).
- [ ] `install.py` into a fixture repo produces a `quality_blocks.py` containing
      no `PLACEHOLDER`, and `run_tests` runs only its `fast` blocks.
- [ ] `install.py --doctor` against `codec-chat` reports its real layout and
      leaves `git status --porcelain` empty.
- [ ] `grep -rnE "codec|Codec|apps/web|apps/admin" .claude/skills/sssf/templates/profiles/`
      returns nothing — no repository-specific path in profile or framework source.
- [ ] `grep -rn "replace this echo\|placeholder commands that exit 0" README.md .claude/skills/sssf/`
      returns nothing.
- [ ] Every `AgentCall(output_type=BuildOutput, ...)` in the shipped ADWs runs
      `gates.doc_policy` and `*gates.profile_gates()` (enforced by
      `tests/test_gate_wiring.py`).
- [ ] A third framework composes with **no change to any shared file**
      (enforced by `tests/test_framework_reuse.py`).
- [ ] No framework imports another framework (enforced by
      `tests/test_framework_registry.py`).
- [ ] No file in `C:\Source\Repos\codec-chat` is modified.

## Deferred, deliberately

Recorded so they are not lost, and so a reviewer does not read their absence as an oversight.

- **Angular itself.** This plan builds the seams that make Angular cheap and proves them with a test framework; it does not ship an Angular profile. Angular enumerates build targets from `angular.json` as well as from `package.json` scripts, so its `blocks()` may do more than call `emit.script_blocks` — the interface allows that, and the right time to find out is against a real Angular repo, not a stub.

- **A second task runner.** `probes.RUNNERS` is a table with one row. The shape — marker files, a list command, a parser, an offline fallback parser — is forced by what recognising a runner takes, but it has been filled in once. nx is the likely second entry and does not fit cleanly: its task list is per-project (`nx show projects`, then each project's targets), not a flat summary. Expect the table to gain a row and possibly a field.

- **Part C is not in this plan.** Branch per run, `git_helper.default_branch/create_run_branch/push_branch/open_pr`, and `adw_plan_build_test_pr.py` are spec §6 and get their own plan. `probes.default_branch` lands here because the report needs it; nothing consumes it yet.

- **A framework cannot add an ADW.** A stack wanting its own workflow has no way to ship one. Nothing needs it yet, and a generated ADW would be the first generated file an operator is likely to want to edit heavily — which is exactly the file you do not want regenerated out from under them.

- **`UsageBreakdown.merge` reads `self.model_fields` on an instance**, which pydantic 2.11 deprecates and 3.0 removes. Pre-existing, unrelated to this change, and noticed while verifying the facts model. One-line fix (`type(self).model_fields`) whenever someone is next in that file.

- **The four deferred items from the Part A plan still stand**, unchanged: the cp1252 console crash that leaves a trace row stuck at `running`; prompts riding on argv against a ~32KB Windows ceiling (Task 21 Step 4 now measures the overlay's contribution); `agent_pi`'s `tools: []` inversion; and the trace recording a bare command while executing a resolved path.

- **Detection does not read `dotnet sln list`, `just --evaluate`, or npm workspaces.** A repo whose frontends are declared only as workspace globs and whose solution is assembled by a generator would be under-detected. `--doctor` makes that visible, and the generated file is editable Python — which is the intended escape hatch for anything a probe cannot see.
