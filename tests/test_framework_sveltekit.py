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
    blocks, unresolved = sveltekit.blocks(sveltekit.detect(tmp_path), _repo())
    by_name = {b.name: b for b in blocks}

    assert by_name["check-web"].argv == ["npm", "run", "check"]
    assert by_name["check-web"].cwd == "apps/web"
    assert by_name["check-web"].operation == "typecheck"
    assert by_name["test-web"].argv == ["npm", "run", "test"]
    assert by_name["build-web"].argv == ["npm", "run", "build"]
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
    write(tmp_path, "apps/web/src/hooks.server.ts", "// csp\n")
    wirings = sveltekit.gate_wiring(sveltekit.detect(tmp_path))
    assert [w.name for w in wirings] == ["sveltekit_csp"]
    assert "hooks.server.ts" in wirings[0].call


def test_the_wired_calls_are_valid_python_expressions(tmp_path):
    import ast
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_X=\n")
    write(tmp_path, "apps/web/src/hooks.server.ts", "// csp\n")
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
