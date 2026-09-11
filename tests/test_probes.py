"""Repo probes: true of every stack, owned by none of them."""

from profile_fixtures import JUSTFILE, dotnet_svelte_repo, package, write

from profiles import probes


# ── node packages ────────────────────────────────────────────────────────────

def test_finds_every_package_declaring_the_marker(tmp_path):
    for directory in ("apps/web", "apps/admin", "packages/kiosk"):
        package(tmp_path, directory, {"build": "vite build"})
    found = probes.node_packages(tmp_path, "@sveltejs/kit")
    assert sorted(f.directory for f in found) == ["apps/admin", "apps/web", "packages/kiosk"]


def test_the_marker_is_what_selects_a_package(tmp_path):
    """The one line that separates finding SvelteKit apps from finding Angular ones."""
    package(tmp_path, "svelte-app", {"build": "vite build"}, marker="@sveltejs/kit")
    package(tmp_path, "ng-app", {"build": "ng build"}, marker="@angular/core")
    assert [f.directory for f in probes.node_packages(tmp_path, "@angular/core")] == ["ng-app"]
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["svelte-app"]


def test_a_package_without_the_marker_is_skipped(tmp_path):
    package(tmp_path, "tools", {"build": "tsc"}, marker="")
    assert probes.node_packages(tmp_path, "@sveltejs/kit") == []


def test_reports_the_scripts_the_package_declares(tmp_path):
    package(tmp_path, "web", {"check": "svelte-check", "lint": "eslint ."})
    found = probes.node_packages(tmp_path, "@sveltejs/kit")[0]
    assert found.has("check") and found.has("lint")
    assert not found.has("test")


def test_package_manager_comes_from_the_lockfile(tmp_path):
    package(tmp_path, "web", {"build": "x"}, lockfile="pnpm-lock.yaml")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].package_manager == "pnpm"


def test_package_manager_is_inherited_from_a_parent_lockfile(tmp_path):
    """A workspace keeps one lockfile at the root; the package below has none."""
    package(tmp_path, "apps/web", {"build": "x"}, lockfile="ignored.txt")
    write(tmp_path, "yarn.lock", "")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].package_manager == "yarn"


def test_package_manager_defaults_to_npm_with_no_lockfile_anywhere(tmp_path):
    package(tmp_path, "web", {"build": "x"}, lockfile="notes.txt")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].package_manager == "npm"


def test_a_malformed_package_json_is_skipped_not_fatal(tmp_path):
    package(tmp_path, "web", {"build": "x"})
    write(tmp_path, "broken/package.json", "{ this is not json")
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["web"]


def test_an_env_example_beside_a_package_is_recorded(tmp_path):
    package(tmp_path, "apps/web", {"build": "x"})
    write(tmp_path, "apps/web/.env.example", "PUBLIC_API_URL=\n")
    assert probes.node_packages(tmp_path, "@sveltejs/kit")[0].env_example == \
        "apps/web/.env.example"


def test_vendored_directories_are_never_walked(tmp_path):
    package(tmp_path, "node_modules/vendor", {"build": "x"})
    package(tmp_path, "web", {"build": "x"})
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["web"]


def test_a_vendored_directory_is_skipped_at_any_depth(tmp_path):
    """Top-level-only skipping passes the result assertion and is still wrong."""
    package(tmp_path, "apps/web", {"build": "x"})
    package(tmp_path, "apps/web/node_modules/dep", {"build": "x"})
    package(tmp_path, "node_modules/vendor", {"build": "x"})

    found = probes.node_packages(tmp_path, "@sveltejs/kit")

    assert [f.directory for f in found] == ["apps/web"]
    assert not any("node_modules" in str(p) for p in probes.walk(tmp_path))


def test_a_package_json_at_the_repo_root_yields_dot(tmp_path):
    """The single-app repo is the most common shape there is."""
    package(tmp_path, ".", {"build": "x"})
    assert [f.directory for f in probes.node_packages(tmp_path, "@sveltejs/kit")] == ["."]


def test_a_malformed_manifest_is_collected_when_a_list_is_passed(tmp_path):
    package(tmp_path, "web", {"build": "x"})
    write(tmp_path, "broken/package.json", "{ this is not json")
    unreadable: list[str] = []
    found = probes.node_packages(tmp_path, "@sveltejs/kit", unreadable)
    assert [f.directory for f in found] == ["web"]
    assert unreadable == ["broken/package.json"]


def test_a_malformed_manifest_is_skipped_silently_when_no_list_is_passed(tmp_path):
    package(tmp_path, "web", {"build": "x"})
    write(tmp_path, "broken/package.json", "{ this is not json")
    found = probes.node_packages(tmp_path, "@sveltejs/kit")
    assert [f.directory for f in found] == ["web"]


# ── task runner ──────────────────────────────────────────────────────────────

def test_recipes_are_parsed_from_a_justfile_without_just_installed():
    names = probes.recipes_from_justfile(JUSTFILE)
    assert {"default", "test-unit", "build-sln", "check-web"} <= set(names)
    assert "api_dir" not in names          # an assignment is not a recipe
    assert "set shell" not in names        # nor is a setting


def test_a_comment_is_not_a_recipe():
    assert "# run the fast suite" not in probes.recipes_from_justfile(JUSTFILE)


def test_recipe_bodies_are_not_mistaken_for_recipes():
    """Indented lines are the body of the recipe above them."""
    assert "npm --prefix {{dir}} run check" not in probes.recipes_from_justfile(JUSTFILE)


def test_no_runner_when_no_marker_file_exists(tmp_path):
    assert probes.task_runner(tmp_path) == ("", [], "")


def test_just_is_detected_from_its_marker_file(tmp_path, monkeypatch):
    monkeypatch.setattr(probes, "_summary", lambda runner, root: (None, "just is not installed"))
    write(tmp_path, "justfile", JUSTFILE)
    name, recipes, source = probes.task_runner(tmp_path)
    assert name == "just"
    assert "test-unit" in recipes
    assert "justfile" in source


def test_a_capitalised_justfile_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(probes, "_summary", lambda runner, root: (None, "just is not installed"))
    write(tmp_path, "Justfile", JUSTFILE)
    assert probes.task_runner(tmp_path)[0] == "just"


def test_the_summary_command_wins_over_the_parser(tmp_path, monkeypatch):
    """`just --summary` resolves imports the offline parser cannot see."""
    monkeypatch.setattr(probes, "_summary",
                        lambda runner, root: (["imported-recipe"], "just --summary"))
    write(tmp_path, "justfile", JUSTFILE)
    name, recipes, source = probes.task_runner(tmp_path)
    assert recipes == ["imported-recipe"]
    assert source == "just --summary"


def test_a_refused_summary_is_reported_in_the_source_not_swallowed(tmp_path, monkeypatch):
    """A runner that REFUSED the file is not the same as one that is absent."""
    monkeypatch.setattr(
        probes, "_summary",
        lambda runner, root: (None, "just --summary exited 1 - the parsed recipes may not be runnable"))
    write(tmp_path, "justfile", JUSTFILE)
    name, recipes, source = probes.task_runner(tmp_path)
    assert name == "just"
    assert "test-unit" in recipes            # falls back to the offline parser
    assert "exited 1" in source              # but says so, rather than looking absent


def test_the_runner_table_declares_a_complete_interface():
    """The shape a second runner (nx, make, task) has to fill in.

    Pins the FIELD SET, not the values: a frozen dataclass already enforces
    that every entry supplies all five, so asserting they are truthy could
    only fail on a deliberately empty string.
    """
    import dataclasses
    assert {f.name for f in dataclasses.fields(probes.RunnerProbe)} == {
        "name", "markers", "summary", "parse_summary", "parse_marker"}
    for runner in probes.RUNNERS:
        assert runner.parse_summary("") == []
        assert runner.parse_marker("") == []


# ── _summary (subprocess boundary) ──────────────────────────────────────────

def test_summary_parses_and_dedupes_a_successful_run(tmp_path, monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda name: "/usr/bin/just")

    class FakeCompleted:
        returncode = 0
        stdout = "a b a\nc"

    monkeypatch.setattr(probes.subprocess, "run", lambda *a, **k: FakeCompleted())

    runner = probes.RUNNERS[0]
    recipes, source = probes._summary(runner, tmp_path)
    assert recipes == ["a", "b", "c"]
    assert source == "just --summary"


def test_summary_falls_back_and_reports_a_refusal_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda name: "/usr/bin/just")

    class FakeCompleted:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(probes.subprocess, "run", lambda *a, **k: FakeCompleted())

    runner = probes.RUNNERS[0]
    recipes, reason = probes._summary(runner, tmp_path)
    assert recipes is None
    assert "exited 1" in reason


def test_summary_falls_back_on_timeout_rather_than_propagating(tmp_path, monkeypatch):
    monkeypatch.setattr(probes.shutil, "which", lambda name: "/usr/bin/just")

    def fake_run(*args, **kwargs):
        raise probes.subprocess.TimeoutExpired(cmd="just --summary", timeout=30)

    monkeypatch.setattr(probes.subprocess, "run", fake_run)

    runner = probes.RUNNERS[0]
    recipes, reason = probes._summary(runner, tmp_path)
    assert recipes is None
    assert "timed out" in reason


# ── branch and conventions ───────────────────────────────────────────────────

def test_default_branch_falls_back_to_main_outside_a_git_repo(tmp_path):
    assert probes.default_branch(tmp_path) == "main"


def test_convention_files_and_directories_are_recorded(tmp_path):
    write(tmp_path, "CLAUDE.md", "# house rules\n")
    write(tmp_path, "AGENTS.md", "# agents\n")
    write(tmp_path, ".github/instructions/csharp.instructions.md", "# c#\n")
    write(tmp_path, ".github/instructions/svelte.instructions.md", "# svelte\n")

    found = probes.conventions(tmp_path)

    assert "CLAUDE.md" in found
    assert "AGENTS.md" in found
    # A directory of instructions is ONE entry, not one per file — fifteen
    # bullets would drown the prompt overlay they end up in.
    assert ".github/instructions/" in found
    assert ".github/instructions/csharp.instructions.md" not in found


def test_an_empty_instructions_directory_is_not_recorded(tmp_path):
    (tmp_path / ".github" / "instructions").mkdir(parents=True)
    assert probes.conventions(tmp_path) == []


def test_an_instructions_directory_holding_only_an_empty_subdirectory_is_not_recorded(tmp_path):
    """`any(path.iterdir())` is true for a subdirectory too; only a FILE counts."""
    (tmp_path / ".github" / "instructions" / "nested").mkdir(parents=True)
    assert probes.conventions(tmp_path) == []


def test_no_convention_files_is_an_empty_list_not_an_error(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert probes.conventions(tmp_path) == []
