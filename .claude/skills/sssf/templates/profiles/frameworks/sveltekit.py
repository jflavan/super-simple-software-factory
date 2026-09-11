"""Everything about SvelteKit, in one file.

Deliberately short. Detection is `probes.node_packages` with one marker plus a
single SvelteKit-specific probe; block generation is one call to
`emit.script_blocks`. That is what a frontend framework should cost once the
shared layer exists - and it is the measure to hold a future angular.py to.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from .. import emit, probes
from ..facts import FrameworkFacts, Frontend, GateWiring, ProfileFacts, QualityBlock

NAME = "sveltekit"
GATE_MODULE = "gates_sveltekit"
OVERLAY = "sveltekit.md"

# The dependency that identifies this framework in a package.json.
MARKER = "@sveltejs/kit"

# SvelteKit exposes only PUBLIC_*; Vite, which it builds on, exposes VITE_*.
# Build-tool conventions, not repository conventions.
ENV_PREFIXES = ["PUBLIC_", "VITE_"]

# SvelteKit's server hook, and the words that mean it declares a policy.
HOOKS_RELATIVE = "src/hooks.server.ts"
CSP_MARKERS = ("csp", "content-security-policy")

# (package.json script, candidate recipe names, quality operation, block prefix)
SCRIPTS = [
    ("check", ["check-{name}", "check-frontend"], "typecheck", "check"),
    ("lint", ["lint-{name}", "lint-frontend"], "lint", "lint"),
    ("test", ["test-{name}", "test-frontend"], "test", "test"),
    ("build", ["build-{name}", "build-frontend"], "build", "build"),
]


class SvelteKitFacts(FrameworkFacts):
    frontends: list[Frontend] = Field(default_factory=list)
    # Manifests that did not parse. probes.node_packages skips them, which makes
    # them invisible to matches() too - so a repo whose only SvelteKit
    # package.json has a trailing comma is told "no profile matches", for a
    # reason the installer knew and did not print. Collected here, reported by
    # blocks() as unresolved.
    unreadable: list[str] = Field(default_factory=list)
    # frontend directory -> the file declaring its content-security policy.
    # Lives here rather than on Frontend because only SvelteKit has the
    # concept: a shared type with one empty slot per framework is how "adding
    # a framework touches no core module" stops being true.
    csp_files: dict[str, str] = Field(default_factory=dict)


def _csp_file(root: Path, frontend: Frontend) -> str:
    """The server hook, but only when it actually declares a CSP.

    Opt-in on purpose: the csp gate fires on external origins, and pointing it
    at a repo that has no policy would be noise on every single run.
    """
    hooks = root / frontend.directory / HOOKS_RELATIVE
    if not hooks.is_file():
        return ""
    text = hooks.read_text(errors="replace").lower()
    return probes.relative(root, hooks) if any(m in text for m in CSP_MARKERS) else ""


def matches(root) -> bool:
    return bool(probes.node_packages(Path(root), MARKER))


def detect(root) -> SvelteKitFacts:
    root = Path(root)
    unreadable: list[str] = []
    frontends = probes.node_packages(root, MARKER, unreadable)
    csp_files = {f.directory: _csp_file(root, f) for f in frontends}
    return SvelteKitFacts(frontends=frontends, unreadable=unreadable,
                          csp_files={d: p for d, p in csp_files.items() if p})


def blocks(facts: SvelteKitFacts,
           repo: ProfileFacts) -> tuple[list[QualityBlock], list[str]]:
    emitted, unresolved = emit.script_blocks(facts.frontends, repo, SCRIPTS)
    unresolved += [f"{path} does not parse as JSON - the package it declares is "
                   f"invisible to detection" for path in facts.unreadable]
    return emitted, unresolved


def describe(facts: SvelteKitFacts) -> list[str]:
    """Name the files the gates key off, so --doctor can show them moving.

    A relocated .env.example or hooks.server.ts silently unwires a gate, and
    the gate list alone reports only a name. These lines are what make that
    drift visible in a doctor run.
    """
    lines = []
    for frontend in facts.frontends:
        lines.append(f"frontend: {frontend.directory}  [{frontend.package_manager}] "
                     f"scripts: {', '.join(frontend.scripts) or 'none'}")
        if frontend.env_example:
            lines.append(f"  env example: {frontend.env_example}")
        if facts.csp_files.get(frontend.directory):
            lines.append(f"  csp: {facts.csp_files[frontend.directory]}")
    return lines


def gate_wiring(facts: SvelteKitFacts) -> list[GateWiring]:
    """Wire a gate only when the fact it needs was actually found.

    A gate that cries wolf is deleted along with the ones that do not, so an
    absent fact means an absent gate rather than a disabled one.
    """
    wirings = []

    env_pairs = [(f.directory, f.env_example) for f in facts.frontends if f.env_example]
    if env_pairs:
        wirings.append(GateWiring(
            module=GATE_MODULE, name="env_example_sync",
            call=f"env_example_sync({env_pairs!r}, {ENV_PREFIXES!r})"))

    csp_pairs = sorted(facts.csp_files.items())
    if csp_pairs:
        wirings.append(GateWiring(
            module=GATE_MODULE, name="sveltekit_csp",
            call=f"sveltekit_csp({csp_pairs!r})"))
    return wirings
