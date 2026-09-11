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
