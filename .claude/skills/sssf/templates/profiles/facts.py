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
    Angular or React tomorrow. The framework-specific slots at the bottom are
    filled by whichever framework found this package, and left empty by the
    ones that have no such concept.
    """

    directory: str                  # repo-relative, forward slashes; "." for the root
    package_manager: str = "npm"    # npm | pnpm | yarn | bun, from the lockfile
    scripts: list[str] = Field(default_factory=list)   # keys of package.json "scripts"
    env_example: str = ""           # the .env.example that governs it, if one exists
    csp_file: str = ""              # the file declaring its content-security policy,
                                    # for frameworks that have one (SvelteKit:
                                    # src/hooks.server.ts). Empty when there is none.

    def has(self, script: str) -> bool:
        return script in self.scripts

    @property
    def label(self) -> str:
        """A short, stable name for this package — used in block names."""
        name = PurePosixPath(self.directory).name
        return name or "root"


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
