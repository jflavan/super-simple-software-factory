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
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .facts import Frontend

# Directories never worth walking: a vendored tree can contain anything,
# including another repo's solution file and a thousand package.json files.
#
# `vendor`, `out`, `target` and `packages` are all plausible real source
# directories, and an over-eager skip hides a real package silently - the
# expensive direction. The fixture's own `packages/kiosk` is the example.
#
# .gitignore is deliberately not consulted: detection must work on trees that
# are not git repos, correct semantics need a dependency or a wrong
# reimplementation, and an over-broad ignore file hides real packages.
SKIP_DIRS = {"node_modules", "bin", "obj", ".git", ".svelte-kit", "dist", "build",
             "artifacts", ".venv", "venv", "__pycache__", ".next", ".nuxt",
             ".angular", ".output", ".turbo", ".nx", "TestResults"}

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
    """Every file under root, skipping vendored and build-output directories.

    os.walk and not rglob: pruning `dirnames` in place stops the DESCENT,
    where rglob enumerates every file in node_modules and .git and then throws
    them away. Measured on a 25k-file repo: 4.0s against 0.017s, and an
    install walks four times.

    os.walk defaults to followlinks=False, matching pathlib's `**`, so this is
    behaviour-preserving apart from the speed.
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


# ── Node packages ────────────────────────────────────────────────────────────

def package_manager(root: Path, directory: Path) -> str:
    """The lockfile nearest this package, walking up to the repo root.

    Stops at the repo root, or at the filesystem root if it is ever called
    with a directory outside the repo - a walk-up with no floor is a hang,
    not an error.
    """
    current = directory
    while True:
        for lockfile, manager in LOCKFILES:
            if (current / lockfile).is_file():
                return manager
        if current == root or current == current.parent:
            return "npm"
        current = current.parent


def _env_example(directory: Path) -> Path | None:
    for name in ENV_EXAMPLE_NAMES:
        if (directory / name).is_file():
            return directory / name
    return None


def node_packages(root: Path, marker: str,
                  unreadable: list[str] | None = None) -> list[Frontend]:
    """Every package.json declaring `marker`, wherever it lives.

    `marker` is the dependency that identifies a framework — `@sveltejs/kit`,
    `@angular/core`, `react`. Everything else about a JavaScript package is
    the same whichever of those it is, which is why this function is here and
    not in a framework module.

    A manifest that does not parse is invisible to detection, including to
    matches(), so a caller that wants to explain itself passes a list to
    collect them.
    """
    root = Path(root)
    found = []
    for manifest in sorted(p for p in walk(root) if p.name == "package.json"):
        try:
            package = json.loads(manifest.read_text(errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # A broken manifest is the repo's problem, not a reason to abort an
            # install. A caller that passed `unreadable` finds out why a
            # package it expected is missing.
            if unreadable is not None:
                unreadable.append(relative(root, manifest))
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
            directory=relative(root, directory),
            package_manager=package_manager(root, directory),
            scripts=package.get("scripts") or {},
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


def _summary(runner: RunnerProbe, root: Path) -> tuple[list[str] | None, str]:
    """The runner's own task list, and where it came from.

    Returns (None, reason) on every failure, but the reason distinguishes the
    two cases that matter: the runner is not installed, versus the runner ran
    and refused. Only the first makes the offline parser a reasonable fallback.

    shutil.which is what makes this work on Windows, where a runner may be a
    shim with an extension PATHEXT knows about and bare-name argv does not.
    """
    binary = shutil.which(runner.summary[0])
    if not binary:
        return None, f"{runner.name} is not installed"
    try:
        completed = subprocess.run([binary, *runner.summary[1:]], cwd=root,
                                   text=True, capture_output=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None, f"{' '.join(runner.summary)} timed out"
    except (OSError, subprocess.SubprocessError) as error:
        return None, f"{' '.join(runner.summary)} failed: {error}"
    if completed.returncode != 0:
        return None, (f"{' '.join(runner.summary)} exited {completed.returncode} - "
                      f"the parsed recipes may not be runnable")
    return runner.parse_summary(completed.stdout), " ".join(runner.summary)


def task_runner(root: Path) -> tuple[str, list[str], str]:
    """The runner this repo uses, the task names it knows, and where they came from.

    The source is the summary command when it worked, or
    `f"{marker.name} ({reason})"` when it fell back to the offline parser -
    the distinction --doctor needs between "not installed" and "installed and
    refused this file".
    """
    root = Path(root)
    for runner in RUNNERS:
        marker = next((root / name for name in runner.markers
                       if (root / name).is_file()), None)
        if marker is None:
            continue
        recipes, reason = _summary(runner, root)
        if recipes is not None:
            return runner.name, recipes, reason
        return (runner.name, runner.parse_marker(marker.read_text(errors="replace")),
                f"{marker.name} ({reason})")
    return "", [], ""


# ── git and conventions ──────────────────────────────────────────────────────

def default_branch(root: Path) -> str:
    """What this repo merges INTO, asked of git rather than assumed.

    `rev-parse --abbrev-ref HEAD` is deliberately not a rung. In a repo made
    with `git init` rather than `git clone` there is no origin/HEAD, and HEAD
    is whatever branch you happen to be standing on — so it would answer
    "the feature branch" for every run started from one. Falling back to
    "main" is wrong loudly (a PR against a branch that does not exist fails
    and says so) instead of wrong quietly.
    """
    for args in (["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                 ["rev-parse", "--abbrev-ref", "origin/main"],
                 ["rev-parse", "--abbrev-ref", "origin/master"]):
        try:
            completed = subprocess.run(["git", *args], cwd=root, text=True,
                                       capture_output=True, timeout=5)
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

    A directory entry carries a trailing slash; that is the only thing
    distinguishing "read this file" from "read everything in here".
    """
    root = Path(root)
    found = [name for name in CONVENTION_FILES if (root / name).is_file()]
    for directory in CONVENTION_DIRS:
        path = root / directory
        if path.is_dir() and any(child.is_file() for child in path.iterdir()):
            found.append(directory + "/")
    return found
