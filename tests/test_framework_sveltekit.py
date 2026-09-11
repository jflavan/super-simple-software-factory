"""The sveltekit framework: marker, CSP probe, its blocks and two gates."""

from profile_fixtures import package, write

from profiles.facts import ProfileFacts
from profiles.frameworks import sveltekit


def _repo(**kwargs):
    return ProfileFacts(profile="p", repo_root=".", **kwargs)


def test_matches_only_when_a_package_declares_sveltekit(tmp_path):
    assert not sveltekit.matches(tmp_path)
    package(tmp_path, "ng", {"build": "ng build"}, marker="@angular/core")
    assert not sveltekit.matches(tmp_path)
    package(tmp_path, "web", {"build": "vite build"})
    assert sveltekit.matches(tmp_path)


def test_every_frontend_is_found_independently(tmp_path):
    for directory in ("apps/web", "apps/admin"):
        package(tmp_path, directory, {"check": "svelte-check"})
    assert sorted(f.directory for f in sveltekit.detect(tmp_path).frontends) == \
        ["apps/admin", "apps/web"]


def test_a_hooks_file_is_recorded_only_when_it_mentions_csp(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    package(tmp_path, "apps/admin", {"build": "x"})
    write(tmp_path, "apps/web/src/hooks.server.ts",
          "// content-security-policy is set here\n")
    write(tmp_path, "apps/admin/src/hooks.server.ts", "export const handle = x;\n")

    facts = sveltekit.detect(tmp_path)

    assert facts.csp_files == {"apps/web": "apps/web/src/hooks.server.ts"}
    assert "apps/admin" not in facts.csp_files


def test_scripts_become_blocks_through_the_shared_emitter(tmp_path):
    package(tmp_path, "apps/web", {"check": "svelte-check", "test": "vitest run",
                                   "build": "vite build"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    blocks, unresolved = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    by_name = {b.name: b for b in blocks}

    assert by_name["check-web"].argv == ["npm", "run", "check"]
    assert by_name["check-web"].cwd == "apps/web"
    assert by_name["check-web"].operation == "typecheck"
    assert by_name["test-web"].argv == ["npm", "run", "test"]
    assert by_name["test-web"].operation == "test"
    assert by_name["build-web"].argv == ["npm", "run", "build"]
    assert by_name["build-web"].operation == "build"
    assert unresolved == []


def test_a_lint_script_is_picked_up_when_present(tmp_path):
    package(tmp_path, "web", {"lint": "eslint ."})
    blocks, _ = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    assert blocks[0].name == "lint-web"
    assert blocks[0].operation == "lint"


def test_describe_names_every_frontend_and_its_manager(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"}, lockfile="pnpm-lock.yaml")
    lines = "\n".join(sveltekit.describe(sveltekit.detect(tmp_path)))
    assert "apps/web" in lines
    assert "pnpm" in lines


def test_env_example_sync_is_wired_only_when_an_example_exists(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    assert sveltekit.gate_wiring(sveltekit.detect(tmp_path)) == []

    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert [w.name for w in wirings] == ["env_example_sync"]
    assert "apps/web/.env.example" in wirings[0].call
    assert "PUBLIC_" in wirings[0].call


def test_csp_is_wired_only_when_a_policy_was_detected(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/src/hooks.server.ts",
          "// csp: default-src 'self';\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert [w.name for w in wirings] == ["sveltekit_csp"]
    assert "hooks.server.ts" in wirings[0].call


def test_the_wired_calls_are_valid_python_expressions(tmp_path):
    import ast
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    write(tmp_path, "apps/web/src/hooks.server.ts",
          "// csp: default-src 'self';\n")
    for wiring in sveltekit.gate_wiring(sveltekit.detect(tmp_path)):
        ast.parse(wiring.call, mode="eval")


def test_gates_from_several_frontends_are_wired_in_one_call(tmp_path):
    for directory in ("apps/web", "apps/admin"):
        package(tmp_path, directory, {"build": "x"})
        write(tmp_path, f"{directory}/.env.example", "PUBLIC_X=\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert len(wirings) == 1
    assert "apps/web" in wirings[0].call and "apps/admin" in wirings[0].call


def test_the_framework_declares_no_repository_specific_paths():
    from pathlib import Path
    text = Path(sveltekit.__file__).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/web", "apps/admin"):
        assert forbidden not in text


# ── Fix 1: a root-level app is the whole-repo case, not a "./" prefix ──────

def test_a_root_level_app_is_wired_as_the_whole_repo(tmp_path):
    """`npx sv create` at the repo root is the single-app default.

    The pair carries "." and the gate must read that as "every changed file",
    not as a `./` prefix nothing matches. Pinned here because the gate lives in
    another module and this is where the value is produced.
    """
    package(tmp_path, ".", {"build": "vite build"})
    write(tmp_path, ".env.example", "PUBLIC_X=\n")

    facts = sveltekit.detect(tmp_path)
    wirings = sveltekit.gate_wiring(facts)

    assert facts.frontends[0].directory == "."
    assert "'.'" in wirings[0].call or '"."' in wirings[0].call


# ── Fix 2 & 3: the CSP probe follows SvelteKit's own documented locations ──

def test_a_javascript_hooks_file_is_detected_too(tmp_path):
    """`.ts` is not the only legal spelling of the server hook."""
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/src/hooks.server.js",
          "// content-security-policy: default-src 'self';\n")

    facts = sveltekit.detect(tmp_path)

    assert facts.csp_files == {"apps/web": "apps/web/src/hooks.server.js"}


def test_a_policy_in_svelte_config_is_detected(tmp_path):
    """`kit.csp.directives` in svelte.config.js is what SvelteKit documents -
    the mainstream configuration, and the config file is tried first."""
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/svelte.config.js",
          "export default { kit: { csp: { directives: { 'default-src': ['self'] } } } };\n")

    facts = sveltekit.detect(tmp_path)

    assert facts.csp_files == {"apps/web": "apps/web/svelte.config.js"}


def test_a_hooks_file_merely_naming_csp_is_not_mistaken_for_a_policy(tmp_path):
    """A `cspNonce` variable or a `// TODO: csp` names no directive at all -
    wiring a gate against it would fail every future external URl against a
    file that holds no policy to check it against."""
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/src/hooks.server.ts",
          "const cspNonce = crypto.randomUUID();\n// TODO: csp\n")

    facts = sveltekit.detect(tmp_path)

    assert facts.csp_files == {}
    assert sveltekit.gate_wiring(facts) == []


# ── Fix 6: a frontend with no .env.example is reported, not silent ────────

def test_a_frontend_with_no_env_example_is_reported_unresolved(tmp_path):
    package(tmp_path, "apps/web", {"build": "vite build"})
    _, unresolved = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    assert any("apps/web" in note and ".env.example" in note for note in unresolved)


# ── Fix 7: unreadable manifests are reported, not silently dropped ────────

def test_an_unreadable_manifest_is_reported_alongside_a_good_package(tmp_path):
    package(tmp_path, "apps/web", {"build": "vite build"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    write(tmp_path, "broken/package.json", "{ this is not json,}")

    facts = sveltekit.detect(tmp_path)
    _, unresolved = sveltekit.blocks(facts, _repo())

    assert facts.unreadable == ["broken/package.json"]
    assert any("broken/package.json" in note for note in unresolved)


# ── Fix 8: tier follows the script's command, not its name ────────────────

def test_a_playwright_test_script_is_tagged_the_full_tier(tmp_path):
    package(tmp_path, "apps/web", {"test": "playwright test"})
    blocks, _ = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    assert blocks[0].tier == "full"


def test_a_vitest_script_stays_in_the_fast_tier(tmp_path):
    package(tmp_path, "apps/web", {"test": "vitest run"})
    blocks, _ = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    assert blocks[0].tier == "fast"
