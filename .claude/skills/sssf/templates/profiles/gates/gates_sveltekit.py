"""Gates that come with SvelteKit.

STAMPED into adws/adw_modules/, so the imports are relative.

Both are factories: the rules are SvelteKit's, but which directories and files
they apply to is discovered at install time and baked into the generated
wiring. That split is what keeps a framework rule from becoming a repository
rule.
"""

from __future__ import annotations

import re
from pathlib import Path

from .data_types import EnvelopeBase, GateReport
from .utils import claimed_files, read_text

# Files worth scanning for references. A README that mentions a variable is
# documentation, not a dependency on it.
SOURCE_SUFFIXES = {".ts", ".js", ".mjs", ".cjs", ".svelte", ".tsx", ".jsx"}

ORIGIN = re.compile(r"https?://[A-Za-z0-9.\-]+(?::\d+)?")

# A development host is not an origin a production policy has to allow.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


def _sources(changed: list[str], directory: str, exclude: str = "") -> list[str]:
    """The changed source files belonging to one frontend.

    A frontend at the repo root arrives as "." - `npx sv create` in a fresh
    repo is the single-app default, so this is the COMMON shape, not an edge
    case. Its prefix is empty: changed files are repo-relative and never
    `./`-prefixed, so treating "." as a literal prefix would match nothing and
    the gate would report `passed` having examined no file at all.
    """
    prefix = "" if directory in (".", "") else directory.rstrip("/") + "/"
    return [f for f in changed
            if f.startswith(prefix) and f != exclude
            and Path(f).suffix in SOURCE_SUFFIXES]


def env_example_sync(pairs: list[tuple[str, str]], prefixes: list[str]):
    """Gate factory: a public variable a frontend reads must be in its example file.

    `pairs` is (frontend directory, its example file) and `prefixes` the build
    tools' public-variable conventions - SvelteKit's `PUBLIC_`, Vite's `VITE_`.
    All three are discovered at install time, which is what keeps this gate a
    framework rule rather than one repository's rule.

    It checks every public variable the changed files reference, not only newly
    added ones. Deriving "newly added" needs a diff and gives a weaker answer:
    a variable that was missing from the example three commits ago is just as
    broken for the next person who clones.
    """
    pattern = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in prefixes)
                         + r")[A-Z0-9_]+\b")

    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = claimed_files(envelope, run)
        for directory, example in pairs:
            sources = _sources(changed, directory)
            if not sources:
                continue
            declared = read_text(Path(run.repo_root) / example)
            referenced = set()
            for source in sources:
                referenced |= set(pattern.findall(read_text(Path(run.repo_root) / source)))
            for name in sorted(referenced):
                present = name in declared
                report.check(f"{name} in {example}", present,
                             "declared" if present else
                             f"{name} is read by {directory} but {example} does not "
                             f"declare it - the build works here and nowhere else")
        return report

    gate.__name__ = f"env_example_sync({len(pairs)} frontend(s))"
    return gate


def sveltekit_csp(pairs: list[tuple[str, str]]):
    """Gate factory: a new external origin requires the CSP to be updated.

    `pairs` is (frontend directory, the file declaring its policy). Only
    frontends where detection found an actual policy are wired, because a repo
    with no CSP would see this fire on every external URL it ever adds - and a
    gate that cries wolf is deleted along with the ones that do not.

    The failure it prevents is browser-side and silent: the request is blocked,
    nothing throws on the server, and the feature simply does not work.
    """
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = claimed_files(envelope, run)
        for directory, policy_file in pairs:
            sources = _sources(changed, directory, exclude=policy_file)
            if not sources:
                continue
            policy = read_text(Path(run.repo_root) / policy_file)
            origins = set()
            for source in sources:
                origins |= set(ORIGIN.findall(read_text(Path(run.repo_root) / source)))
            unknown = sorted(o for o in origins
                             if not any(host in o for host in LOCAL_HOSTS)
                             and o not in policy)
            if not unknown:
                continue
            report.check(policy_file, policy_file in changed,
                         "updated alongside the new origin(s)"
                         if policy_file in changed else
                         f"{len(unknown)} origin(s) not in the CSP and {policy_file} "
                         f"was not changed: {', '.join(unknown[:3])} - the browser "
                         f"will block these and nothing will throw on the server")
        return report

    gate.__name__ = f"sveltekit_csp({len(pairs)} frontend(s))"
    return gate
