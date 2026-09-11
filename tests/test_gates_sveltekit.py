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


def test_each_frontend_is_checked_against_its_own_example(tmp_path):
    _source(tmp_path, "apps/web/.env.example", "")
    _source(tmp_path, "apps/admin/.env.example", "")
    source = _source(tmp_path, "apps/admin/src/x.ts", "const u = PUBLIC_ADMIN_URL;\n")

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
    source = _source(tmp_path, "apps/web/src/a.ts", "const u = PUBLIC_API_URL;\n")
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
