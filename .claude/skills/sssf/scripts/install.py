#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic>=2", "pyyaml>=6"]
# ///
"""/install — stamp the SSSF factory from the skill into the cwd. Idempotent.

Usage:
    uv run <skill>/scripts/install.py [--force] [--profile NAME | --no-profile]
    uv run <skill>/scripts/install.py --doctor

Stamps: adws/ (modules + starter ADWs), adws/adw_data/prompt_engineering/
(5 starter agents), adws/adw_sssf_config/sssf.config.yaml, .env.sample,
.gitignore entries. Existing files are skipped unless --force.

Then applies a stack PROFILE: probes the repo, stamps the gate module of every
framework the profile declares, and GENERATES this repo's real quality blocks,
gate wiring, and prompt overlay. With no --profile, the profile whose
frameworks all match is applied; an ambiguous match stops and asks. --doctor
re-probes and reports without writing anything, which is what to run after the
repo's layout changes.
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"

# The profile packages live beside the templates and import each other
# relatively, so `templates/` has to be importable as a package root. This is
# the same insert tests/conftest.py performs, deliberately: what the tests
# import is what the installer imports.
if str(TEMPLATES) not in sys.path:
    sys.path.insert(0, str(TEMPLATES))

from profiles import probes, registry  # noqa: E402  (must follow the sys.path insert)

PROFILE_GATES_SRC = TEMPLATES / "profiles" / "gates"

GITIGNORE_ENTRIES = [
    "adws/adw_data/sessions/",
    "adws/adw_data/sssf.db*",
    ".env",
    # The ADWs are Python, so importing adw_modules writes bytecode next to it.
    # Chains that end in a commit phase call `git add -A`, so without this a
    # stamped repo commits its own .pyc files — 15 of them showed up in the
    # first repo that was ever installed into from scratch.
    "__pycache__/",
    "*.pyc",
]


def stamp(src: Path, dest: Path, force: bool, stamped: list, skipped: list) -> None:
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if child.name == "__pycache__":
                continue
            stamp(child, dest / child.name, force, stamped, skipped)
        return
    if dest.exists() and not force:
        skipped.append(str(dest))
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    stamped.append(str(dest))


def ensure_gitignore(root: Path, stamped: list) -> None:
    gitignore = root / ".gitignore"
    existing = (gitignore.read_text(encoding="utf-8").splitlines()
                if gitignore.exists() else [])
    missing = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if missing:
        with gitignore.open("a", encoding="utf-8", newline="\n") as f:
            f.write("\n# sssf runtime\n" + "\n".join(missing) + "\n")
        stamped.append(f"{gitignore} (+{len(missing)} entries)")


def stamp_profile_gates(profile, root: Path, force: bool,
                        stamped: list, skipped: list) -> None:
    """Stamp one gate module per framework the profile declares.

    Stamped like every other shipped module, which means an existing copy is
    left alone without --force. A gate is code an operator is invited to edit;
    silently overwriting their edit on a re-install would be the one thing this
    installer has never done.
    """
    missing = []
    for module in profile.gate_modules():
        source = PROFILE_GATES_SRC / f"{module}.py"
        if source.is_file():
            stamp(source, root / "adws" / "adw_modules" / f"{module}.py",
                  force, stamped, skipped)
        else:
            missing.append(module)
    if missing:
        # gate_modules() is declarative - it reports what the frameworks DECLARE,
        # without consulting the disk. A framework that names a GATE_MODULE it
        # never shipped would otherwise produce a generated profile_gates.py
        # importing a module nobody stamped, and that surfaces as an ImportError
        # inside an ADW run, an install later. Refuse here instead.
        raise SystemExit(
            f"profile {profile.NAME!r} declares gate module(s) with no source "
            f"file: {', '.join(sorted(missing))}. Expected them under "
            f"{PROFILE_GATES_SRC}. A framework declaring GATE_MODULE must ship "
            f"it (step 2 of ADDING A FRAMEWORK).")


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
        # A manifest that does not parse never revealed which framework it
        # belonged to, so no framework module can report it - and a repo whose
        # ONLY manifest is broken looks exactly like a repo with no frontend.
        # This is the one place that can say so out loud.
        unreadable: list[str] = []
        probes.node_packages(root, "", unreadable)
        for path in unreadable:
            print(f"  ! {path} does not parse as JSON - a package it declares "
                  f"would be invisible to detection")
    return profile


# What a generated file needs from the stamped tree. Each entry is (path,
# symbol, what breaks without it).
GENERATED_DEPENDENCIES = (
    ("adws/adw_modules/quality.py", "_import_generated_blocks",
     "quality_blocks.py would be inert and the echo placeholders would still run"),
    ("adws/adw_modules/gates.py", "def profile_gates",
     "profile_gates.py would be inert and no stack gate would ever fire"),
    ("adws/adw_modules/utils.py", "def claimed_files",
     "importing profile_gates.py would raise ImportError at ADW runtime"),
)


def stale_modules(root: Path) -> list[str]:
    """Stamped modules too old to use what a profile generates.

    `stamp()` skips a file that already exists, so upgrading an existing
    installation leaves the runtime at its old version while generation
    happily writes the new files beside it. The result reports a wired factory
    and wires nothing - this project's own worst failure mode, reached through
    the ordinary upgrade door rather than a partial write.

    Checked by symbol rather than by version, because there is no version to
    check and a symbol is what the generated file actually needs.
    """
    problems = []
    for relative, symbol, consequence in GENERATED_DEPENDENCIES:
        path = root / relative
        if path.is_file() and symbol not in path.read_text(encoding="utf-8",
                                                           errors="replace"):
            problems.append(f"{relative} is missing {symbol!r} - {consequence}")
    return problems


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

    profile = select_profile(root, args.profile, args.no_profile)

    facts = None
    if profile is not None:
        # Detected BEFORE stamping. Stamping writes the factory's own justfile
        # into a repo that has none, and detection would then report SSSF's
        # recipes as if they were the repo's - true of the tree on disk, and
        # misleading about the repository.
        facts = profile.detect(root)

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

        if profile is not None:
            stamp_profile_gates(profile, root, args.force, stamped, skipped)

            stale = stale_modules(root)
            if stale:
                raise SystemExit(
                    "this repo has an older SSSF stamped in it, and a profile cannot "
                    "be applied on top of it:\n  - " + "\n  - ".join(stale) +
                    "\n\nRe-run with --force to refresh the stamped modules. NOTE that "
                    "--force also overwrites adws/adw_sssf_config/sssf.config.yaml and "
                    "adws/adw_data/prompt_engineering/ - commit first.")

    if profile is not None:
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
        print("\n  windows: optional - set PYTHONUTF8=1 and PYTHONIOENCODING=utf-8")
        print("           to see the banner's box-drawing characters instead of '?'.")
        print("           Not required: piping output to a cp1252 stream degrades")
        print("           them rather than killing the run, and every file the")
        print("           factory reads or writes names utf-8 explicitly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
