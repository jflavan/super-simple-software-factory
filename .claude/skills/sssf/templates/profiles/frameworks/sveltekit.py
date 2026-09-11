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

# Where a SvelteKit app declares a Content-Security-Policy, in the order the
# framework documents them: `kit.csp.directives` in the config is the blessed
# route, and a hand-written header in the server hook is the alternative.
# Several spellings each, because a JavaScript project is not a TypeScript one.
CSP_FILES = ("svelte.config.js", "svelte.config.ts",
             "src/hooks.server.ts", "src/hooks.server.js", "src/hooks.server.mjs")

# Tighter than a bare "csp": a `cspNonce` variable or a `// TODO: csp` would
# otherwise wire a gate against a file holding no directives at all, and the
# gate would then demand an edit to the wrong file for every external URL.
CSP_MARKERS = ("csp:", "content-security-policy", "contentsecuritypolicy")

# (package.json script, candidate recipe names, quality operation, block prefix)
SCRIPTS = [
    ("check", ["check-{name}", "check-frontend"], "typecheck", "check"),
    ("lint", ["lint-{name}", "lint-frontend"], "lint", "lint"),
    ("test", ["test-{name}", "test-frontend"], "test", "test"),
    ("build", ["build-{name}", "build-frontend"], "build", "build"),
]


class SvelteKitFacts(FrameworkFacts):
    frontends: list[Frontend] = Field(default_factory=list)
    # Manifests anywhere in the repo that did not parse as JSON. Not
    # attributable to a framework - a manifest that fails to parse never
    # revealed which framework it belonged to - so this is "what detection
    # could not read", reported so a package does not vanish silently.
    # It does NOT rescue a repo whose only manifest is broken: matches() runs
    # before blocks(), so such a repo is reported as "no profile matches"
    # instead. install.py handles that case on the no-match path.
    unreadable: list[str] = Field(default_factory=list)
    # frontend directory -> the file declaring its content-security policy.
    # Lives here rather than on Frontend because only SvelteKit has the
    # concept: a shared type with one empty slot per framework is how "adding
    # a framework touches no core module" stops being true.
    csp_files: dict[str, str] = Field(default_factory=dict)


def _csp_file(root: Path, frontend: Frontend) -> str:
    """Where this app's CSP is declared, if it declares one at all.

    Tried in the order SvelteKit documents them: `svelte.config.js`'s
    `kit.csp.directives` is the config-file route the framework describes, so
    it is tried before the hand-written server-hook alternative. Opt-in on
    purpose: the csp gate fires on external origins, and pointing it at a
    repo that has no policy would be noise on every single run.
    """
    for candidate in CSP_FILES:
        path = root / frontend.directory / candidate
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        if any(m in text for m in CSP_MARKERS):
            return probes.relative(root, path)
    return ""


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
    unresolved += [f"frontend {f.directory} has no .env.example - the public "
                   f"variable gate is not wired for it"
                   for f in facts.frontends if not f.env_example]
    unresolved += [f"{path} does not parse as JSON - the package it declares is "
                   f"invisible to detection - fix the JSON and re-run "
                   f"install.py --profile" for path in facts.unreadable]
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
                     f"scripts: {', '.join(sorted(frontend.scripts)) or 'none'}")
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
