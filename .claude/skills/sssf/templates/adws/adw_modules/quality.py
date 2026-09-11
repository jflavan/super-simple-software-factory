"""Deterministic lint, typecheck, build, and test blocks.

A known command is not a judgement call. Anything whose invocation you can write
down belongs here as code — it runs in milliseconds, costs nothing, and returns
the same answer every time. Agents are for the parts that need reading and
deciding.

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
"""

from __future__ import annotations

import importlib.util
import shlex
import subprocess
import time
from pathlib import Path

from pydantic import TypeAdapter

from .data_types import (EventRecord, QualityCheckResult, QualityCheckSpec, QualityResult,
                         QualityTier, VerifyOutput)
from .utils import now_iso, operator_env, resolve_argv

# How much of a failing command's output rides back inside the envelope. Enough
# for a builder to act on without opening the artifact; bounded so a runaway
# stack trace can't swamp the next agent's context.
TAIL_CHARS = 4_000


def _check_dir(run, name: str) -> Path:
    seq = run.phases[-1].seq if run.phases else 0
    path = run.context_handoff_dir / "quality" / f"{seq:02d}_{name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run(spec: QualityCheckSpec, run) -> QualityCheckResult:
    phase = run.phases[-1]
    output_dir = _check_dir(run, spec.name)
    output_artifact = output_dir / "command.log"
    command = shlex.join(spec.argv)
    env = operator_env()             # the engineer's own shell environment
    workdir = Path(run.repo_root) / spec.cwd

    run.console.note(f"quality {spec.name}: {command}")
    started_at = now_iso()
    clock = time.monotonic()
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            resolve_argv(spec.argv),
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        returncode = 124
        stdout = error.stdout or ""
        stderr = (error.stderr or "") + f"\nTimed out after {spec.timeout_seconds}s."
    except OSError as error:
        # A missing binary lands here as exit 127 with the real message — no
        # pre-flight probe needed, and none wanted.
        returncode = 127
        stderr = str(error)

    duration = time.monotonic() - clock
    output_artifact.write_text(
        f"$ {command}\ncwd: {workdir}\nexit: {returncode}\n"
        f"duration_seconds: {duration:.3f}\n"
        f"\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n"
    )
    passed = returncode == 0
    run.tracer.event(EventRecord(
        adw_id=run.adw_id,
        phase_id=phase.phase_id,
        type="tool_call",
        name=f"quality:{spec.name}",
        payload={
            "area": spec.area,
            "operation": spec.operation,
            "cwd": spec.cwd,
            "tier": spec.tier,
            "command": command,
            "returncode": returncode,
            "passed": passed,
            "output_artifact": str(output_artifact),
        },
        started_at=started_at,
        ended_at=now_iso(),
    ))
    run.console.note(
        f"quality {spec.name}: {'passed' if passed else 'failed'} "
        f"(exit {returncode}, {duration:.1f}s)"
    )
    return QualityCheckResult(
        name=spec.name,
        area=spec.area,
        operation=spec.operation,
        command=command,
        returncode=returncode,
        passed=passed,
        duration_seconds=duration,
        output_artifact=str(output_artifact),
        output_tail=(stdout + stderr)[-TAIL_CHARS:],
    )


# ── Blocks ────────────────────────────────────────────────────────────────────

def _placeholder(name: str) -> QualityCheckSpec:
    """A command that does nothing and admits it."""
    return QualityCheckSpec(
        name=name,
        area="backend",
        operation=name,
        argv=["echo", f"PLACEHOLDER {name}: no profile generated "
                      f"adws/adw_modules/quality_blocks.py, and nobody wrote the "
                      f"real {name} command by hand"],
        timeout_seconds=600 if name == "test" else 120,
    )


PLACEHOLDER_BLOCKS = [_placeholder(n) for n in ("test", "lint", "typecheck", "build")]


def _import_generated_blocks() -> list[QualityCheckSpec] | None:
    """The generated block list, or None when no profile ever wrote one.

    Existence is decided by `find_spec`, BEFORE importing, so that every error
    raised *by* the generated file stays fatal regardless of what it names.
    Matching on `ModuleNotFoundError.name` could not tell "quality_blocks is
    absent" from "quality_blocks imports something else that is absent and
    happens to share its name" — and the second case swallowed the error and
    fell back to `echo` placeholders that exit 0, which is the exact failure
    this whole mechanism exists to remove.

    The list is validated rather than trusted. A generator that emits dicts, or
    a spec with a bad operation, should fail HERE with a pydantic error naming
    the field, not later inside _run_tier with an AttributeError far from the
    cause.
    """
    if importlib.util.find_spec(f"{__package__}.quality_blocks") is None:
        return None
    from .quality_blocks import BLOCKS
    return TypeAdapter(list[QualityCheckSpec]).validate_python(BLOCKS)


def blocks() -> list[QualityCheckSpec]:
    """This repo's quality blocks: generated if a profile wrote them, else fakes.

    Names must be unique because a block's name IS its artifact directory
    (`_check_dir`), and every block in one tier shares a phase sequence number.
    Two blocks called `test` would overwrite each other's command.log and both
    report the same path, so the first one's evidence would be gone by the time
    anyone read it.
    """
    generated = _import_generated_blocks()
    resolved = generated if generated is not None else list(PLACEHOLDER_BLOCKS)
    names = [block.name for block in resolved]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate quality block name(s): {duplicates}. "
                         f"A block's name is its artifact directory.")
    return resolved


def _run_tier(run, tiers: set[QualityTier]) -> QualityResult:
    """Run every block in the given tiers and collect ALL failures.

    Ordering contract for the caller: a failing block does NOT fail the phase.
    The runner did its job; the CODE is what failed. Hand this result to the
    builder and let the bounded repair loop decide the run's fate.

    An EMPTY selection is different in kind, and raises. A green result from
    zero executed commands is the one failure this whole mechanism exists to
    remove, and it is reachable two ways: a `BLOCKS = []` that a generator
    wrote, and a block list where every entry is `full` so the fast tier
    selects nothing. Neither is something a builder can repair, so neither
    belongs in the repair loop.
    """
    defined = blocks()
    selected = [spec for spec in defined if spec.tier in tiers]
    if not selected:
        raise RuntimeError(
            f"no quality blocks in tier(s) {sorted(tiers)}: "
            f"{len(defined)} block(s) defined, none selected. Check "
            f"adws/adw_modules/quality_blocks.py, or re-run `install.py --doctor`.")
    checks = [_run(spec, run) for spec in selected]
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


def as_envelope(result: QualityResult, what: str) -> VerifyOutput:
    """Wrap a deterministic result so an agent can be handed it directly.

    Agents hand each other typed envelopes; code blocks return QualityResult.
    This is the adapter, so a failing lint or test run flows back into the
    builder through exactly the same door an agent's report would — the ADW
    script is the only thing that knows the difference.
    """
    return VerifyOutput(
        status="success" if result.passed else "fail",
        summary=(f"{what}: all {len(result.checks)} check(s) passed" if result.passed
                 else f"{what}: {len(result.failures)} of {len(result.checks)} check(s) failed"),
        artifacts=result.artifacts,
        notes_for_next_agent=("" if result.passed else
                              "Fix every failure below. The output is verbatim from the "
                              "command — trust it over any summary."),
        passed=result.passed,
        failures=result.failures,
    )


def run_quality(run) -> QualityResult:
    """Every tier — final verification, run once."""
    return _run_tier(run, {"fast", "full"})
