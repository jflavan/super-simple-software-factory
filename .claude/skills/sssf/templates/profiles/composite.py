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

from pathlib import Path

import yaml

from . import emit, probes
from .facts import GenerationReport, ProfileFacts
from .frameworks import get as get_framework

BLOCKS_RELATIVE = "adws/adw_modules/quality_blocks.py"
GATES_RELATIVE = "adws/adw_modules/profile_gates.py"
OVERLAY_RELATIVE = "adws/adw_data/prompt_engineering/profile_overlay.md"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

NO_CONVENTIONS = (
    "This repository has no convention files (no CLAUDE.md, AGENTS.md, or\n"
    "instructions directory were found), so there is nothing extra to read.\n"
    "Follow the patterns in the code you are editing.")


class CompositeProfile:
    """One profile.yaml, and the frameworks it declares.

    Order follows the profile's `frameworks:` list everywhere except
    `gate_modules()`, which sorts: reports and blocks read in the order the
    profile declared, while the stamped-module set is order-free.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        try:
            config = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            # Named, because registry._discover builds one of these per
            # profile directory: without the path, one bad file reads as
            # "every profile is broken".
            raise SystemExit(f"{self.path}: not valid YAML - {error}") from error
        if not isinstance(config, dict):
            raise SystemExit(f"{self.path}: a profile is a mapping with `name` "
                             f"and `frameworks`, got {type(config).__name__}")

        self.NAME: str = config.get("name") or self.path.parent.name.replace("_", "-")
        self.description: str = config.get("description", "")

        declared = config.get("frameworks")
        if not isinstance(declared, list) or not declared:
            raise SystemExit(
                f"{self.path}: `frameworks` must be a non-empty list, got "
                f"{declared!r}. A profile with no frameworks matches nothing "
                f"and would generate a factory that checks nothing.")
        if not all(isinstance(name, str) for name in declared):
            raise SystemExit(f"{self.path}: `frameworks` must be a list of names, "
                             f"got {declared!r}")
        # get_framework raises SystemExit naming the unknown one, so a typo in
        # a profile fails at load with a readable message rather than an
        # AttributeError somewhere inside generation.
        self.frameworks = [get_framework(name) for name in declared]

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
        return ProfileFacts(
            profile=self.NAME,
            repo_root=str(root),
            task_runner=runner,
            recipes=recipes,
            recipes_source=recipes_source,
            default_branch=probes.default_branch(root),
            conventions=probes.conventions(root),
            frameworks={f.NAME: f.detect(root) for f in self.frameworks},
        )

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
        origin: dict[str, list[str]] = {}
        for framework in self.frameworks:
            emitted, notes = framework.blocks(facts.of(framework.NAME), facts)
            for block in emitted:
                origin.setdefault(block.name.casefold(), []).append(
                    f"{block.name} (from {framework.NAME})")
            blocks += emitted
            unresolved += notes

        # Folded, because a block name IS an artifact directory, and Windows
        # and default macOS filesystems are case-insensitive: `test-Web` from
        # one framework and `test-web` from another resolve to one directory
        # and overwrite each other's log, past an exact-match guard.
        clashes = {folded: names for folded, names in origin.items() if len(names) > 1}
        if clashes:
            detail = "; ".join(f"{folded}: {', '.join(names)}"
                               for folded, names in sorted(clashes.items()))
            raise SystemExit(
                f"profile {self.NAME!r}: two blocks share one name (and a block "
                f"name is its artifact directory, so they would overwrite each "
                f"other's evidence): {detail}")
        return blocks, unresolved

    def _wirings(self, facts: ProfileFacts):
        wirings = []
        for framework in self.frameworks:
            wirings += framework.gate_wiring(facts.of(framework.NAME))
        return wirings

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

    def generate(self, facts: ProfileFacts, root, write: bool = True) -> GenerationReport:
        """Facts in, files out. `write=False` is the --doctor dry run.

        KEEP this docstring and the comment below — Task 10 earned them and an
        earlier draft of this task reverted both.

        Write ORDER is load-bearing. `quality_blocks.py` is what `quality.py`
        treats as "a profile generated this repo", and `gates.profile_gates()`
        treats a missing `profile_gates.py` as "no profile, no stack gates" and
        returns []. So if blocks landed first and the gates write then failed,
        the repo would run its quality blocks green with every stack gate
        silently unenforced — a factory that looks installed and checks less
        than it says. Gates first means a half-written install has no blocks
        either, which reads as "not installed" rather than "installed and
        quietly weaker".
        """
        blocks, unresolved = self._collect(facts)
        wirings = self._wirings(facts)
        # Rendered unconditionally, written only when asked. render_* runs an
        # ast.parse self-check, so a dry run PROVES the generated modules would
        # import - which is the single most useful thing --doctor can do, and
        # it could not do it while rendering lived inside `if write:`.
        blocks_text = emit.render_blocks_module(
            facts, blocks, summary=[f"  {line}" for line in self.describe(facts)])
        gates_text = emit.render_gates_module(facts, wirings)
        overlay_text = self.render_overlay(facts)
        written: list[str] = []
        if write:
            # Gates BEFORE blocks. See the docstring: blocks are the marker
            # that a profile ran, gates are silently optional to the loader,
            # so a failure between the two must leave the weaker-looking state,
            # not the quieter one.
            emit.write_file(root, GATES_RELATIVE, gates_text, written)
            emit.write_file(root, BLOCKS_RELATIVE, blocks_text, written)
            # Last, because unlike the other two the overlay is not load-bearing
            # for either loader above - it is read through a prompt variable
            # (agents.profile_overlay), not imported, so nothing downstream
            # treats its absence as a signal.
            emit.write_file(root, OVERLAY_RELATIVE, overlay_text, written)
        return GenerationReport(profile=self.NAME, files=written, blocks=blocks,
                                gates=[w.name for w in wirings], unresolved=unresolved)
