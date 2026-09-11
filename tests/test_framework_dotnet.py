"""The dotnet framework: solution parsing, project roles, its blocks and gate."""

from profile_fixtures import (CSPROJ_APP, CSPROJ_INTEGRATION, CSPROJ_UNIT,
                              dotnet_svelte_repo, sln, write)

from profiles.facts import ProfileFacts
from profiles.frameworks import dotnet


def _repo(**kwargs):
    return ProfileFacts(profile="p", repo_root=".", **kwargs)


# ── detection ────────────────────────────────────────────────────────────────

def test_finds_the_solution_and_classifies_every_project(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)

    assert facts.solution == "Fixture.sln"
    assert {p.name: p.role for p in facts.projects} == {
        "Api": "app", "Api.Tests": "unit-tests",
        "Api.IntegrationTests": "integration-tests"}


def test_project_paths_are_repo_relative_with_forward_slashes(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)
    assert all("\\" not in p.path for p in facts.projects)
    assert "apps/api/Api/Api.csproj" in [p.path for p in facts.projects]


def test_solution_folders_are_not_projects(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Folders.sln", ["src/App/App.csproj"], folders=["Solution Items"])
    assert [p.name for p in dotnet.detect(tmp_path).projects] == ["App"]


def test_an_slnx_solution_is_read_too(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    write(tmp_path, "Modern.slnx",
          '<Solution>\n  <Project Path="src/App/App.csproj" />\n</Solution>\n')
    facts = dotnet.detect(tmp_path)
    assert facts.solution == "Modern.slnx"
    assert [p.name for p in facts.projects] == ["App"]


def test_testcontainers_outranks_a_test_sdk():
    """A project with both is an INTEGRATION suite - it needs Docker up."""
    assert dotnet.classify(CSPROJ_INTEGRATION) == "integration-tests"
    assert dotnet.classify(CSPROJ_UNIT) == "unit-tests"
    assert dotnet.classify(CSPROJ_APP) == "app"


def test_a_project_named_in_the_solution_but_missing_on_disk_is_an_app(tmp_path):
    """Never crash on a stale solution entry; the worst case is a wrong role."""
    sln(tmp_path, "Stale.sln", ["gone/Gone.csproj"])
    assert [(p.name, p.role) for p in dotnet.detect(tmp_path).projects] == [("Gone", "app")]


def test_a_solution_inside_node_modules_is_ignored(tmp_path):
    write(tmp_path, "node_modules/pkg/Vendor.sln", "Microsoft Visual Studio Solution File")
    assert dotnet.detect(tmp_path).solution == ""


def test_the_shallowest_solution_wins(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Root.sln", ["src/App/App.csproj"])
    sln(tmp_path, "src/Nested.sln", ["App/App.csproj"])
    assert dotnet.detect(tmp_path).solution == "Root.sln"


def test_matches_requires_a_solution(tmp_path):
    assert not dotnet.matches(tmp_path)
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    assert dotnet.matches(tmp_path)


def test_by_role_filters(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)
    assert [p.name for p in facts.by_role("unit-tests")] == ["Api.Tests"]
    assert [p.name for p in facts.by_role("integration-tests")] == ["Api.IntegrationTests"]


# ── blocks ───────────────────────────────────────────────────────────────────

def _blocks(tmp_path, repo=None, **kwargs):
    dotnet_svelte_repo(tmp_path, **kwargs)
    facts = dotnet.detect(tmp_path)
    blocks, unresolved = dotnet.blocks(facts, repo or _repo())
    return {b.name: b for b in blocks}, unresolved


def test_a_unit_test_project_becomes_a_fast_dotnet_test_block(tmp_path):
    blocks, _ = _blocks(tmp_path, integration=False)
    block = blocks["test-Api.Tests"]
    assert block.argv == ["dotnet", "test", "apps/api/Api.Tests/Api.Tests.csproj"]
    assert block.tier == "fast"
    assert block.area == "backend"


def test_an_integration_project_is_tagged_full(tmp_path):
    blocks, _ = _blocks(tmp_path)
    assert blocks["test-Api.IntegrationTests"].tier == "full"


def test_the_solution_build_is_emitted(tmp_path):
    blocks, _ = _blocks(tmp_path)
    assert blocks["build-sln"].argv == ["dotnet", "build", "Fixture.sln"]


def test_a_recipe_replaces_the_per_project_commands(tmp_path):
    """One recipe covers every project of a role; running it per project would
    run the same suite N times."""
    repo = _repo(task_runner="just", recipes=["test-unit", "build-sln"])
    blocks, _ = _blocks(tmp_path, repo)
    assert blocks["test-unit"].argv == ["just", "test-unit"]
    assert "test-Api.Tests" not in blocks
    assert blocks["build-sln"].argv == ["just", "build-sln"]


def test_a_recipe_that_does_not_exist_falls_back_to_the_raw_command(tmp_path):
    repo = _repo(task_runner="just", recipes=["deploy"])
    blocks, _ = _blocks(tmp_path, repo)
    assert blocks["test-Api.Tests"].argv[0] == "dotnet"


def test_a_missing_role_is_reported_unresolved(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    _, unresolved = dotnet.blocks(dotnet.detect(tmp_path), _repo())
    assert any("unit-tests" in note for note in unresolved)
    assert any("integration-tests" in note for note in unresolved)


def test_no_solution_means_no_build_block_and_a_note(tmp_path):
    blocks, unresolved = dotnet.blocks(dotnet.detect(tmp_path), _repo())
    assert blocks == []
    assert any("sln" in note for note in unresolved)


# ── report and gates ─────────────────────────────────────────────────────────

def test_describe_names_the_solution_and_every_project(tmp_path):
    dotnet_svelte_repo(tmp_path)
    lines = "\n".join(dotnet.describe(dotnet.detect(tmp_path)))
    assert "Fixture.sln" in lines
    assert "Api.IntegrationTests" in lines
    assert "integration-tests" in lines


def test_the_migration_gate_is_always_wired(tmp_path):
    dotnet_svelte_repo(tmp_path)
    wirings = dotnet.gate_wiring(dotnet.detect(tmp_path))
    assert [w.name for w in wirings] == ["ef_migration_triad"]
    assert wirings[0].module == dotnet.GATE_MODULE
    assert wirings[0].call == "ef_migration_triad"


def test_the_framework_declares_no_repository_specific_paths():
    """The design rule, checked on the file most likely to break it."""
    from pathlib import Path
    text = Path(dotnet.__file__).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/api", "Fixture.sln"):
        assert forbidden not in text
