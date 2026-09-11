"""The SvelteKit gates: public env variables, and the content-security policy."""

from types import SimpleNamespace

from adw_modules.data_types import BuildOutput
from adw_modules.gates_sveltekit import env_example_sync, sveltekit_csp

PREFIXES = ["PUBLIC_", "VITE_"]
HOOKS = "apps/web/src/hooks.server.ts"


def _run(tmp_path):
    return SimpleNamespace(repo_root=str(tmp_path), cfg=SimpleNamespace())


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


def _source(tmp_path, relative, text):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return relative


# ── env_example_sync ─────────────────────────────────────────────────────────

def test_no_frontend_change_means_no_checks(tmp_path):
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path))
    assert report.passed
    assert report.checks == []


def test_a_public_variable_absent_from_the_example_fails(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "PUBLIC_OTHER=\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "PUBLIC_API_URL" in report.violations[0]


def test_a_public_variable_present_in_the_example_passes(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "PUBLIC_API_URL=http://x\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_vite_prefixed_variables_are_checked_too(tmp_path):
    source = _source(tmp_path, "apps/web/src/main.ts",
                     "const key = import.meta.env.VITE_MAP_KEY;\n")
    _source(tmp_path, "apps/web/.env.example", "")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "VITE_MAP_KEY" in gate(_envelope([source]), _run(tmp_path)).violations[0]


def test_a_private_variable_is_not_this_gate_s_business(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/db.ts",
                     "import { DATABASE_URL } from '$env/static/private';\n")
    _source(tmp_path, "apps/web/.env.example", "")

    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


# ── Fix 2: a bare PUBLIC_*/VITE_* identifier is not an env reference ─────────

def test_a_bare_const_named_public_is_not_flagged(tmp_path):
    """`const PUBLIC_ROUTES = [...]` in an auth guard is idiomatic SvelteKit."""
    source = _source(tmp_path, "apps/web/src/lib/routes.ts",
                     "const PUBLIC_ROUTES = ['/login', '/register'];\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_comment_mentioning_a_removed_variable_is_not_flagged(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/notes.ts",
                     "// PUBLIC_LEGACY_URL was removed in v2\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_string_literal_matching_the_pattern_is_not_flagged(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/label.test.ts",
                     "expect(label).toBe('PUBLIC_BETA');\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_an_enum_member_is_not_flagged(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/visibility.ts",
                     "export enum Visibility { PUBLIC_READ, PRIVATE_READ }\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_markup_text_matching_the_pattern_is_not_flagged(tmp_path):
    source = _source(tmp_path, "apps/web/src/routes/+page.svelte",
                     "<div>PUBLIC_NOTICE</div>\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_real_static_public_import_still_fires(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "PUBLIC_API_URL" in gate(_envelope([source]), _run(tmp_path)).violations[0]


def test_a_real_import_meta_env_reference_still_fires(tmp_path):
    source = _source(tmp_path, "apps/web/src/lib/map.ts",
                     "const key = import.meta.env.VITE_MAP_KEY;\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "VITE_MAP_KEY" in gate(_envelope([source]), _run(tmp_path)).violations[0]


def test_an_aliased_import_is_checked_under_its_real_name(tmp_path):
    """`X as Y`: the variable actually being read is X, the left side."""
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL as apiUrl } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "PUBLIC_API_URL" in gate(_envelope([source]), _run(tmp_path)).violations[0]


# ── Fix 5: `name in declared` was a substring test over the raw file text ───

def test_a_shorter_declared_name_does_not_falsely_satisfy_a_longer_reference(tmp_path):
    """`.env.example` declares PUBLIC_API_URL; the source reads PUBLIC_API.

    A substring test over the raw text would find "PUBLIC_API" inside
    "PUBLIC_API_URL" and call it satisfied. Parsing declared keys catches this.
    """
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "PUBLIC_API_URL=http://x\n")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))
    assert not report.passed
    assert "PUBLIC_API" in report.violations[0]


def test_a_commented_out_declaration_still_satisfies_the_gate(tmp_path):
    """A commented `# PUBLIC_API_URL=` documents an optional variable."""
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, "apps/web/.env.example", "# PUBLIC_API_URL=\n")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


# ── Fix 6: a root "." pair must not swallow a sibling frontend's files ──────

def test_a_root_pair_does_not_double_check_a_sibling_frontends_files(tmp_path):
    _source(tmp_path, ".env.example", "")
    _source(tmp_path, "apps/admin/.env.example", "PUBLIC_ADMIN_URL=http://x\n")
    source = _source(tmp_path, "apps/admin/src/x.ts",
                     "import { PUBLIC_ADMIN_URL } from '$env/static/public';\n")

    gate = env_example_sync([(".", ".env.example"),
                             ("apps/admin", "apps/admin/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    # Checked once, against its own example - not again against the root's.
    assert len(report.checks) == 1
    assert report.passed


def test_each_frontend_is_checked_against_its_own_example(tmp_path):
    _source(tmp_path, "apps/web/.env.example", "")
    _source(tmp_path, "apps/admin/.env.example", "")
    source = _source(tmp_path, "apps/admin/src/x.ts",
                     "import { PUBLIC_ADMIN_URL } from '$env/static/public';\n")

    gate = env_example_sync([("apps/web", "apps/web/.env.example"),
                             ("apps/admin", "apps/admin/.env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    assert len(report.checks) == 1
    assert "apps/admin/.env.example" in report.violations[0]


def test_a_non_source_file_is_not_scanned(tmp_path):
    source = _source(tmp_path, "apps/web/README.md",
                     "set PUBLIC_DOCS_URL before running\n")
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_a_deleted_source_file_does_not_crash_the_gate(tmp_path):
    """changed_files includes deletions; the file is gone from disk."""
    _source(tmp_path, "apps/web/.env.example", "")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert gate(_envelope(["apps/web/src/gone.ts"]), _run(tmp_path)).passed


def test_a_missing_example_file_is_reported_not_raised(tmp_path):
    source = _source(tmp_path, "apps/web/src/a.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert not gate(_envelope([source]), _run(tmp_path)).passed


def test_the_gate_has_a_readable_name_for_the_trace():
    gate = env_example_sync([("apps/web", "apps/web/.env.example")], PREFIXES)
    assert "env_example_sync" in gate.__name__


def test_root_directory_public_variable_is_scanned(tmp_path):
    """A frontend at the repo root arrives as directory == "." - `npx sv create`
    in a fresh repo is the single-app default. A naive prefix of "./" would
    match nothing, since changed_files are repo-relative and never
    `./`-prefixed, and the gate would silently examine zero files forever."""
    source = _source(tmp_path, "src/lib/api.ts",
                     "import { PUBLIC_API_URL } from '$env/static/public';\n")
    _source(tmp_path, ".env.example", "PUBLIC_OTHER=\n")

    gate = env_example_sync([(".", ".env.example")], PREFIXES)
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "PUBLIC_API_URL" in report.violations[0]


# ── sveltekit_csp ────────────────────────────────────────────────────────────

def test_csp_is_silent_when_the_frontend_did_not_change(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path)).checks == []


def test_a_new_external_origin_requires_the_hooks_file_to_change(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")

    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "tiles.example.com" in report.violations[0]


def test_an_origin_already_in_the_policy_is_fine(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"img-src https://tiles.example.com\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).passed


def test_changing_the_hooks_file_satisfies_the_gate(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source, HOOKS]), _run(tmp_path)).passed


def test_localhost_is_not_an_external_origin(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/dev.ts",
                     "fetch('http://localhost:5173/x');\n"
                     "fetch('http://127.0.0.1:8080/y');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


# ── Fix 1: an origin only matters if something REQUESTS it ─────────────────

def test_an_inline_svgs_xmlns_is_not_flagged(tmp_path):
    """Every standalone inline SVG carries this - it is not a subresource."""
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/Icon.svelte",
                     '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                     '<path d="M1 1" /></svg>\n')
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_comment_link_is_not_flagged(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/notes.ts",
                     "// see https://kit.svelte.dev/docs/configuration\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_licence_url_is_not_flagged(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/vendor.ts",
                     "// @license ... https://opensource.org/licenses/MIT\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_json_ld_schema_url_is_not_flagged(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/seo.ts",
                     'const type = "https://schema.org/Person";\n')
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([source]), _run(tmp_path)).checks == []


def test_a_fetch_call_still_fires_despite_the_narrower_pattern(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/maps.ts",
                     "fetch('https://tiles.example.com/a.png');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))
    assert not report.passed
    assert "tiles.example.com" in report.violations[0]


# ── Fix 4: policy comparison is whole extracted origins, not raw substring ──

def test_a_narrower_origin_is_not_hidden_by_a_wider_ports_suffix(tmp_path):
    """policy allows :8443; the source requests the bare origin - different
    tokens, so a substring match ("https://example.com" inside
    "https://example.com:8443") must not silently satisfy it."""
    _source(tmp_path, HOOKS, "const csp = \"connect-src https://example.com:8443\";\n")
    source = _source(tmp_path, "apps/web/src/lib/api.ts",
                     "fetch('https://example.com/data');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))
    assert not report.passed
    assert "example.com" in report.violations[0]


# ── Fix 8: LOCAL_HOSTS compares the parsed host, not a substring ───────────

def test_a_host_merely_containing_localhost_is_not_treated_as_local(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/evil.ts",
                     "fetch('https://localhost.attacker.com/x');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))
    assert not report.passed
    assert "localhost.attacker.com" in report.violations[0]


def test_a_host_merely_containing_localhost_as_a_substring_is_not_local(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "apps/web/src/lib/cdn.ts",
                     "fetch('https://my-localhost-cdn.com/x');\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    report = gate(_envelope([source]), _run(tmp_path))
    assert not report.passed
    assert "my-localhost-cdn.com" in report.violations[0]


def test_the_hooks_file_itself_is_not_scanned_for_origins(tmp_path):
    _source(tmp_path, HOOKS, "const csp = \"connect-src https://api.example.com\";\n")
    gate = sveltekit_csp([("apps/web", HOOKS)])
    assert gate(_envelope([HOOKS]), _run(tmp_path)).checks == []


def test_the_csp_gate_has_a_readable_name_for_the_trace():
    assert "sveltekit_csp" in sveltekit_csp([("apps/web", HOOKS)]).__name__


def test_root_directory_new_external_origin_is_scanned(tmp_path):
    """Same root-directory hazard as env_example_sync: directory == "." must
    be treated as the whole repo, not as a "./" prefix that matches nothing."""
    hooks = "src/hooks.server.ts"
    _source(tmp_path, hooks, "const csp = \"default-src 'self'\";\n")
    source = _source(tmp_path, "src/lib/api.ts",
                     "fetch('https://tiles.example.com/a.png');\n")

    gate = sveltekit_csp([(".", hooks)])
    report = gate(_envelope([source]), _run(tmp_path))

    assert not report.passed
    assert "tiles.example.com" in report.violations[0]
