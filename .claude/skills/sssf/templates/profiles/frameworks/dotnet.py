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

import os
import re
from pathlib import Path, PurePosixPath
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

# .NET solutions name projects of several languages. Everything else in a
# `Project(...)` line is a solution FOLDER, whose "path" is just its display
# name.
PROJECT_SUFFIXES = (".csproj", ".fsproj", ".vbproj")

# Matched as `Include="<marker>` (no closing quote - a real Testcontainers
# reference is `Testcontainers.PostgreSql` or similar, so the match has to be
# a prefix of the attribute value, not the whole thing) rather than a bare
# substring: raw XML also contains comments and `<None Include="...">`
# entries, and a bare substring match on either produces a false
# "integration-tests", which is the dangerous direction - it moves a real
# unit suite out of the fast loop. This is a heuristic; its failures show up
# in `describe()`.
TEST_SDK_MARKERS = tuple(f'Include="{m}' for m in
                         ("xunit", "Microsoft.NET.Test.Sdk", "NUnit", "MSTest"))
INTEGRATION_MARKERS = tuple(f'Include="{m}' for m in ("Testcontainers",))

# Fast tier must stay fast: a recipe here is trusted to be "the quick suite"
# without `classify` ever looking at the projects it covers, so only names
# that claim to BE the fast subset belong on this list. Nothing "backend" or
# "api" shaped - a team's `test-api` recipe may well run the full
# Testcontainers suite, and that must not land in the fast tier.
RECIPES = {
    "unit_tests": ["test-unit", "test-fast", "test-dotnet-unit"],
    "integration_tests": ["test-api-integration", "test-integration", "test-e2e-api"],
    "solution_build": ["build-sln", "build-dotnet", "build-api"],
}

# Named once so three more frameworks copy a name, not a bare number: fast is
# for the tier that runs inside a bounded fix loop, full is for the tier that
# does not.
FAST_TIMEOUT = 900
FULL_TIMEOUT = 1800

ProjectRole = Literal["app", "unit-tests", "integration-tests"]


class DotnetProject(BaseModel):
    """One project in the solution, and what it is for."""

    path: str                       # repo-relative, forward slashes
    name: str                       # the .csproj stem
    role: ProjectRole


class DotnetFacts(FrameworkFacts):
    solution: str = ""              # repo-relative *.sln or *.slnx
    projects: list[DotnetProject] = Field(default_factory=list)
    # Named in the solution, not usable: a project file we could not read, or
    # a solution entry that pointed outside the repo. A project we cannot
    # read is classified `app` and gets no block, so a test suite can vanish
    # from the factory for a reason detection knew and did not print.
    unreadable: list[str] = Field(default_factory=list)
    # Other root-level-tied solutions that lost the alphabetical tie-break in
    # `find_solution`. Two root solutions is a real .NET pattern (a product
    # solution and a tooling one, say); the loser is silently skipped, so this
    # is the only trace that a choice was even made.
    other_solutions: list[str] = Field(default_factory=list)

    def by_role(self, role: str) -> list[DotnetProject]:
        return [p for p in self.projects if p.role == role]


# ── detection ────────────────────────────────────────────────────────────────

def find_solution(root: Path, ties: list[str] | None = None) -> str:
    """The solution file, shallowest first so a repo-root one always wins.

    A tie at the shallowest depth is broken alphabetically with no other
    signal - two root-level solutions is a real .NET pattern, and picking
    `Alpha.sln` over `Zeta.sln` silently is worse than picking it loudly.
    When `ties` is given, the runners-up at that same depth are appended to it.
    """
    candidates = [p for p in probes.walk(root) if p.suffix in (".sln", ".slnx")]
    if not candidates:
        return ""
    candidates.sort(key=lambda p: (len(p.relative_to(root).parts), p.name))
    if ties is not None:
        min_depth = len(candidates[0].relative_to(root).parts)
        ties.extend(probes.relative(root, p) for p in candidates[1:]
                    if len(p.relative_to(root).parts) == min_depth)
    return probes.relative(root, candidates[0])


def solution_projects(root: Path, solution: str,
                      dropped: list[str] | None = None) -> list[str]:
    """Repo-relative, forward-slashed paths of every project the solution names.

    An entry that resolves outside the repo (a `..`-laden path, or an
    absolute one) is dropped rather than returned: `DotnetProject.path` is
    documented repo-relative, and `QualityBlock` validates `cwd` against `..`
    but not `argv` - so a project path that escapes here would sidestep that
    guard and write a path outside the repo into the generated module. Dropped
    entries are appended to `dropped` (raw, pre-normalization) so callers can
    report them instead of letting them vanish.
    """
    text = (root / solution).read_text(encoding="utf-8", errors="replace")
    pattern = SLNX_PROJECT if solution.endswith(".slnx") else SLN_PROJECT
    solution_dir = Path(solution).parent
    paths = []
    for raw in pattern.findall(text):
        entry = raw.replace("\\", "/")
        if not entry.lower().endswith(PROJECT_SUFFIXES):
            continue                       # a solution folder, not a project
        joined = os.path.normpath((solution_dir / entry).as_posix()).replace("\\", "/")
        if joined == ".." or joined.startswith("../") or os.path.isabs(joined):
            if dropped is not None:
                dropped.append(entry)
            continue        # names something outside the repo; not ours to run
        paths.append(joined.removeprefix("./"))
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
    other_solutions: list[str] = []
    solution = find_solution(root, other_solutions)
    if not solution:
        return DotnetFacts()
    unreadable: list[str] = []
    projects = []
    for relative in solution_projects(root, solution, unreadable):
        path = root / relative
        # A solution can name a project that is not on disk, or one that
        # exists but cannot be opened. Either way, treat it as an app rather
        # than crash the installer over it - but record it, so the missing
        # suite is reported rather than silently invisible.
        try:
            text = (path.read_text(encoding="utf-8", errors="replace")
                    if path.is_file() else "")
            if not path.is_file():
                unreadable.append(relative)
        except OSError:
            text = ""
            unreadable.append(relative)
        projects.append(DotnetProject(path=relative, name=Path(relative).stem,
                                      role=classify(text)))
    return DotnetFacts(solution=solution, projects=projects, unreadable=unreadable,
                       other_solutions=other_solutions)


# ── generation ───────────────────────────────────────────────────────────────

def blocks(facts: DotnetFacts, repo: ProfileFacts) -> tuple[list[QualityBlock], list[str]]:
    emitted: list[QualityBlock] = []
    unresolved: list[str] = []

    for role, recipe_key, block_name, tier, timeout in (
            ("unit-tests", "unit_tests", "test-unit", "fast", FAST_TIMEOUT),
            ("integration-tests", "integration_tests", "test-integration", "full",
             FULL_TIMEOUT)):
        argv, source = emit.recipe(repo, RECIPES[recipe_key])
        projects = facts.by_role(role)
        if argv:
            # One recipe covers every project of this role: a team that wrote
            # `test-unit` meant all of them, and running it once per project
            # would run the same suite N times.
            if projects:
                source = f"{source} (replaces {len(projects)} per-project command(s))"
            else:
                # The recipe is authoritative about what the team runs, so
                # still emit it - but a recipe with no matching project on
                # this role is a mismatch worth a human's eyes.
                unresolved.append(
                    f"{block_name} is wired from a task-runner recipe, but no "
                    f"{role} project was detected - verify it runs what you expect")
                source = f"{source} (no {role} project detected)"
            emitted.append(QualityBlock(name=block_name, area="backend",
                                        operation="test", argv=argv, tier=tier,
                                        timeout_seconds=timeout, source=source))
        elif projects:
            # Names go through emit.labels for the same reason sveltekit's do:
            # two projects can share a .csproj stem (`modules/*/Tests/Tests.csproj`),
            # and a block's name is its artifact directory.
            label_of = emit.labels([PurePosixPath(p.path).parent.as_posix()
                                    for p in projects])
            for project in projects:
                key = PurePosixPath(project.path).parent.as_posix()
                emitted.append(QualityBlock(
                    name=f"test-{label_of[key]}", area="backend", operation="test",
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
            tier="fast", timeout_seconds=FAST_TIMEOUT,
            source=source or f"solution {facts.solution}"))
    else:
        unresolved.append("no .sln or .slnx found - no backend build block")

    if facts.other_solutions:
        unresolved.append(
            f"{facts.solution} was picked over {', '.join(facts.other_solutions)} "
            f"by an alphabetical tie-break at the same depth - verify that is the "
            f"solution you want built and tested")

    for entry in facts.unreadable:
        if entry == ".." or entry.startswith("../") or "/../" in entry:
            unresolved.append(
                f"{entry} is named in the solution but escapes the repository - "
                f"it was dropped and nothing verifies it")
        else:
            unresolved.append(
                f"{entry} is named in the solution but could not be read - it is "
                f"classified `app` and nothing verifies it")
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
