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
