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
from urllib.parse import urlparse

from .data_types import EnvelopeBase, GateReport
from .utils import claimed_files, read_text

# Files worth scanning for references. A README that mentions a variable is
# documentation, not a dependency on it.
SOURCE_SUFFIXES = {".ts", ".js", ".mjs", ".cjs", ".svelte", ".tsx", ".jsx"}

# A minified bundle checked into the repo (`static/app.bundle.js`, a vendored
# .js) is not hand-authored source, and has nothing these regex gates should
# act on. Capping what gets read keeps a full install from fully loading and
# scanning megabytes of it twice - once per gate - after every code-changing
# agent phase.
MAX_BYTES = 256 * 1024

# An origin only matters if something REQUESTS it. Matching every URL in the
# text flagged `xmlns="http://www.w3.org/2000/svg"` - which every standalone
# inline SVG carries - plus documentation links in `//` comments and licence
# URLs (`@license ... https://opensource.org/licenses/MIT`). None of those is
# a subresource the browser fetches, so none belongs in a CSP, and a gate
# demanding they be added is one an operator cannot satisfy.
#
# `href=` is deliberately NOT included: an `<a href>` is a navigation, not a
# CSP-governed subresource, and doc links in markup are common.
_HOST = r"https?://[A-Za-z0-9.\-]+(?::\d+)?"
REQUESTED_ORIGIN = re.compile(
    rf"""(?:fetch|WebSocket|EventSource|importScripts|sendBeacon)\s*\(\s*["'`]({_HOST})"""
    rf"""|\bsrc\s*=\s*["'`]({_HOST})""")

# A development host is not an origin a production policy has to allow.
# `[::1]` is deliberately absent: REQUESTED_ORIGIN's host character class
# excludes `[` and `:`, so a bracketed IPv6 literal never produces a captured
# origin at all - there is nothing here for it to match against.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0")

# Only the two shapes that ARE env references. A bare PUBLIC_* identifier is
# not one: `const PUBLIC_ROUTES = [...]` in an auth guard is idiomatic, and a
# gate demanding it be added to .env.example is a gate that gets deleted.
PUBLIC_IMPORT = re.compile(
    r"""import\s*\{([^}]*)\}\s*from\s*["']\$env/(?:static|dynamic)/public["']""")
VITE_ENV = re.compile(r"import\.meta\.env\.([A-Za-z][A-Za-z0-9_]*)")

# A key the example file declares, commented or not: a commented-out
# `# PUBLIC_API_URL=` documents an optional variable, and that is the example
# file doing its job.
ENV_KEY = re.compile(r"^\s*#?\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", re.MULTILINE)


def _host(origin: str) -> str:
    return urlparse(origin).hostname or ""


def _referenced_env_names(text: str, prefixes: tuple[str, ...]) -> set[str]:
    """Every env variable name this source genuinely reads.

    A `$env/.../public` import binds by name - `X` or `X as Y`, where `X` is
    the variable actually being read, not the local alias `Y`.
    `import.meta.env.X` names it directly. Anything else - a bare identifier
    in a comment, a string, an enum member, markup text - is not a reference
    to the environment at all.
    """
    names: set[str] = set()
    for group in PUBLIC_IMPORT.findall(text):
        for item in group.split(","):
            name = item.strip().split(" as ")[0].strip()
            if name:
                names.add(name)
    names |= set(VITE_ENV.findall(text))
    # SvelteKit's public import can only legally carry PUBLIC_*, and
    # `import.meta.env` also exposes MODE/DEV/PROD - not the operator's to
    # declare in an example file.
    return {n for n in names if n.startswith(prefixes)}


def _sources(changed: list[str], directory: str, exclude: str = "",
            other_prefixes: tuple[str, ...] = ()) -> list[str]:
    """The changed source files belonging to one frontend.

    A frontend at the repo root arrives as "." - `npx sv create` in a fresh
    repo is the single-app default, so this is the COMMON shape, not an edge
    case. Its prefix is empty: changed files are repo-relative and never
    `./`-prefixed, so treating "." as a literal prefix would match nothing and
    the gate would report `passed` having examined no file at all.

    `other_prefixes` matters only for that root case. `probes.node_packages`
    can hand back a root frontend alongside deeper ones - `[(".", ...),
    ("apps/admin", ...)]` - and the root's empty prefix would otherwise match
    every sibling frontend's files too: checked twice, and against the wrong
    example/policy file. A file already claimed by a more specific prefix is
    excluded from the root's own sources.
    """
    prefix = "" if directory in (".", "") else directory.rstrip("/") + "/"
    return [f for f in changed
            if f.startswith(prefix) and f != exclude
            and Path(f).suffix in SOURCE_SUFFIXES
            and not (prefix == "" and any(f.startswith(p) for p in other_prefixes))]


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

    "References" means an actual `$env/.../public` import or an
    `import.meta.env.X` read - not a bare `PUBLIC_*`/`VITE_*` identifier
    appearing anywhere in the text. A bare identifier also matches a route
    table entry, a removed-variable comment, a test fixture, an enum member,
    or markup text, none of which is a dependency on an environment variable.
    """
    prefix_tuple = tuple(prefixes)
    other_prefixes = tuple(d.rstrip("/") + "/" for d, _ in pairs if d not in (".", ""))

    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = claimed_files(envelope, run)
        for directory, example in pairs:
            sources = _sources(changed, directory, other_prefixes=other_prefixes)
            if not sources:
                continue
            declared = set(ENV_KEY.findall(
                read_text(Path(run.repo_root) / example, max_bytes=MAX_BYTES)))
            referenced: set[str] = set()
            for source in sources:
                text = read_text(Path(run.repo_root) / source, max_bytes=MAX_BYTES)
                referenced |= _referenced_env_names(text, prefix_tuple)
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

    An origin is only collected when it appears in a request-shaped context
    (`fetch(...)`, `new WebSocket(...)`, an element's `src=`, and similarly)
    rather than anywhere in the text - see REQUESTED_ORIGIN above.

    Known limitations, recorded rather than hidden:
    - Not directive-aware: an origin listed under `img-src` satisfies a
      `fetch` to it just as well as one under `connect-src`, even though the
      browser enforces per-directive and would still block the request.
    - Not comment-aware: the policy is compared as whole extracted origins
      rather than raw substrings, which fixes a port suffix hiding an origin
      (or the reverse) - but an origin merely mentioned in a `//` comment
      inside the policy file extracts identically to one in a real directive
      value.
    """
    other_prefixes = tuple(d.rstrip("/") + "/" for d, _ in pairs if d not in (".", ""))

    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        changed = claimed_files(envelope, run)
        for directory, policy_file in pairs:
            sources = _sources(changed, directory, exclude=policy_file,
                               other_prefixes=other_prefixes)
            if not sources:
                continue
            policy = read_text(Path(run.repo_root) / policy_file, max_bytes=MAX_BYTES)
            # Whole origins, not a raw substring test: `policy.split()` was
            # tried first and rejected - the policy is embedded in JS
            # (`const csp = "img-src https://x.com";`), so a whitespace token
            # picks up the trailing `";` and a real, already-declared origin
            # stops matching. Re-extracting with the same host pattern used
            # on the sources gets a clean origin either way.
            policy_origins = set(re.findall(_HOST, policy))
            origins: set[str] = set()
            for source in sources:
                text = read_text(Path(run.repo_root) / source, max_bytes=MAX_BYTES)
                origins |= {match for groups in REQUESTED_ORIGIN.findall(text)
                            for match in groups if match}
            unknown = sorted(o for o in origins
                             if _host(o) not in LOCAL_HOSTS
                             and o not in policy_origins)
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
