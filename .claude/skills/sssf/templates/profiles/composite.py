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

        # Folded, because a block name IS an artifact directory, and Windows
        # and default macOS filesystems are case-insensitive: `test-Web` from
        # one framework and `test-web` from another resolve to one directory
        # and overwrite each other's log, past an exact-match guard.
        clashes = sorted(name for name, count
                         in Counter(b.name.casefold() for b in blocks).items()
                         if count > 1)
        if clashes:
            raise SystemExit(
                f"profile {self.NAME!r}: two frameworks emitted the same block "
                f"name(s): {', '.join(clashes)}. Block names are how the trace "
                f"tells checks apart, so this is stopped rather than resolved by "
                f"dropping one.")
        return blocks, unresolved

    def generate(self, facts: ProfileFacts, root, write: bool = True) -> GenerationReport:
        """Facts in, files out. `write=False` is the --doctor dry run.

        The blocks module is rendered unconditionally - even on a dry run -
        because `render_blocks_module` ast.parses what it produces. That is
        the only thing standing between --doctor and a broken generated
        module: rendering it is how a dry run proves the file WOULD import,
        not just that facts were collected. Only the write to disk is gated.
        """
        blocks, unresolved = self._collect(facts)
        text = emit.render_blocks_module(
            facts, blocks, summary=[f"  {line}" for line in self.describe(facts)])
        written: list[str] = []
        if write:
            emit.write_file(root, BLOCKS_RELATIVE, text, written)
        return GenerationReport(profile=self.NAME, files=written, blocks=blocks,
                                unresolved=unresolved)
