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

import ast
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    # Where `recipes` came from. A runner that REFUSED the file is not the same
    # as one that is not installed: the first means the offline parser is
    # reading a file the runner itself rejects, so every recipe it finds may be
    # a command that cannot run. --doctor prints this.
    recipes_source: str = ""
    default_branch: str = "main"
    conventions: list[str] = Field(default_factory=list)  # CLAUDE.md, AGENTS.md, dirs...
    frameworks: dict[str, FrameworkFacts] = Field(default_factory=dict)

    def of(self, name: str) -> FrameworkFacts:
        """This framework's section, or a KeyError that says what is there."""
        try:
            return self.frameworks[name]
        except KeyError:
            raise KeyError(
                f"profile {self.profile!r} has no {name!r} section - "
                f"has: {sorted(self.frameworks)}") from None


QualityArea = Literal["frontend", "backend"]
QualityOperation = Literal["lint", "typecheck", "build", "test"]
QualityTier = Literal["fast", "full"]


class QualityBlock(BaseModel):
    """One block the generator decided to emit, plus WHY it chose that command.

    `source` never reaches the generated file — it exists for the install
    report, so "just test-api" and "dotnet test apps/api/X.csproj" are
    distinguishable at a glance from a preference the operator can override.
    """

    name: str
    area: QualityArea
    # Typed against the same values QualityCheckSpec accepts. An untyped string
    # here would let a framework emit a bad operation that nothing rejects until
    # the GENERATED file is imported at ADW runtime, a whole install later.
    operation: QualityOperation
    argv: list[str]
    cwd: str = "."
    tier: QualityTier = "fast"
    timeout_seconds: int = 120
    source: str = ""

    @field_validator("cwd")
    @classmethod
    def _cwd_stays_inside_the_repo(cls, value: str) -> str:
        """Mirrors QualityCheckSpec.cwd's validator in the stamped runtime.

        This is the generation-time half of that check: a framework building a
        bad `cwd` is caught HERE, while the framework that produced it is still
        on the stack, rather than when the GENERATED module is imported at ADW
        runtime and the failure has nothing left pointing back to its cause.
        """
        text = value.replace("\\", "/")
        if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
            raise ValueError(f"cwd must be relative to the repo root, got {value!r}")
        if ".." in text.split("/"):
            raise ValueError(f"cwd must not climb out of the repo, got {value!r}")
        return text


class GateWiring(BaseModel):
    """One gate a framework wants wired, ready to render into a generated file.

    `call` is a rendered Python expression rather than a callable, because it
    has to survive being written to disk and imported by a different process.
    """

    module: str                     # stamped module it comes from, e.g. "gates_dotnet"
    name: str                       # the symbol to import
    call: str                       # the expression, e.g. "env_example_sync([...], [...])"

    @field_validator("call")
    @classmethod
    def _call_is_an_expression(cls, value: str) -> str:
        """Parse it here, where the framework that wrote it is still on the stack.

        This string is interpolated into a generated module that a DIFFERENT
        process imports, an install later. A framework that builds it by
        concatenation rather than repr() would otherwise surface as a
        SyntaxError inside an ADW run, with nothing pointing back here.
        """
        try:
            ast.parse(value, mode="eval")
        except SyntaxError as error:
            raise ValueError(
                f"gate call must be a Python expression, got {value!r}") from error
        return value


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
