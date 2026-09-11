"""The dotnet framework: solution parsing, project roles, its blocks and gate."""

from pathlib import Path

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
    assert not dotnet.matches(tmp_path)  # .csproj files alone are not a solution
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    assert dotnet.matches(tmp_path)


def test_by_role_filters(tmp_path):
    dotnet_svelte_repo(tmp_path)
    facts = dotnet.detect(tmp_path)
    assert [p.name for p in facts.by_role("unit-tests")] == ["Api.Tests"]
    assert [p.name for p in facts.by_role("integration-tests")] == ["Api.IntegrationTests"]


# ── Fix 1: every language a solution can name is a project ─────────────────

def test_an_fsharp_test_project_is_detected_not_treated_as_a_solution_folder(tmp_path):
    write(tmp_path, "src/FTests/FTests.fsproj", CSPROJ_UNIT)
    sln(tmp_path, "Mixed.sln", ["src/FTests/FTests.fsproj"])
    facts = dotnet.detect(tmp_path)
    assert [(p.name, p.role) for p in facts.projects] == [("FTests", "unit-tests")]


def test_a_vbproj_is_also_a_project(tmp_path):
    write(tmp_path, "src/VbApp/VbApp.vbproj", CSPROJ_APP)
    sln(tmp_path, "Vb.sln", ["src/VbApp/VbApp.vbproj"])
    assert [p.name for p in dotnet.detect(tmp_path).projects] == ["VbApp"]


# ── Fix 5: a solution entry escaping the repo is dropped, not written into
# generated argv ────────────────────────────────────────────────────────────

def test_a_solution_entry_that_escapes_the_repo_is_dropped_and_reported(tmp_path):
    """QualityBlock validates `cwd` against `..` and absolute paths but not
    `argv` - so an escaping solution entry has to be caught here, while this
    framework is still on the stack."""
    sln(tmp_path, "S.sln", ["../Shared/Shared.csproj"])
    facts = dotnet.detect(tmp_path)
    assert facts.projects == []
    assert facts.unreadable == ["../Shared/Shared.csproj"]
    _, unresolved = dotnet.blocks(facts, _repo())
    assert any("../Shared/Shared.csproj" in note and "escapes the repository" in note
              for note in unresolved)


def test_an_absolute_solution_entry_is_also_dropped(tmp_path):
    import os as _os
    absolute_entry = _os.path.abspath(_os.path.join(_os.sep, "Outside", "Outside.csproj"))
    absolute_entry = absolute_entry.replace("\\", "/")
    sln(tmp_path, "S.sln", [absolute_entry])
    dropped: list[str] = []
    paths = dotnet.solution_projects(tmp_path, "S.sln", dropped)
    assert paths == []
    assert dropped == [absolute_entry]


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
    assert block.operation == "test"


def test_an_integration_project_is_tagged_full(tmp_path):
    blocks, _ = _blocks(tmp_path)
    assert blocks["test-Api.IntegrationTests"].tier == "full"


def test_the_solution_build_is_emitted(tmp_path):
    blocks, _ = _blocks(tmp_path)
    assert blocks["build-sln"].argv == ["dotnet", "build", "Fixture.sln"]
    assert blocks["build-sln"].operation == "build"


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


# ── Fix 2: block names go through emit.labels ───────────────────────────────

def test_two_projects_with_the_same_csproj_stem_get_distinct_block_names(tmp_path):
    """`quality._check_dir` turns a block name into an artifact directory -
    two blocks sharing a name overwrite each other's command.log."""
    write(tmp_path, "modules/Alpha/Tests/Tests.csproj", CSPROJ_UNIT)
    write(tmp_path, "modules/Beta/Tests/Tests.csproj", CSPROJ_UNIT)
    sln(tmp_path, "Modules.sln",
        ["modules/Alpha/Tests/Tests.csproj", "modules/Beta/Tests/Tests.csproj"])
    facts = dotnet.detect(tmp_path)
    blocks, _ = dotnet.blocks(facts, _repo())
    names = [b.name for b in blocks]
    test_names = sorted(n for n in names if n.startswith("test-"))
    assert len(test_names) == 2
    assert len(set(test_names)) == 2                      # names actually differ
    assert test_names == ["test-modules-Alpha-Tests", "test-modules-Beta-Tests"]
    for name in test_names:
        assert "\\" not in name


# ── Fix 3: an unreadable project gets a channel instead of vanishing ───────

def test_a_missing_project_is_recorded_as_unreadable(tmp_path):
    sln(tmp_path, "Stale.sln", ["gone/Gone.csproj"])
    facts = dotnet.detect(tmp_path)
    assert facts.unreadable == ["gone/Gone.csproj"]
    _, unresolved = dotnet.blocks(facts, _repo())
    assert any("gone/Gone.csproj" in note and "could not be read" in note
              for note in unresolved)


def test_a_project_path_that_is_a_directory_is_recorded_as_unreadable(tmp_path):
    (tmp_path / "src/Weird.csproj").mkdir(parents=True)
    sln(tmp_path, "Weird.sln", ["src/Weird.csproj"])
    facts = dotnet.detect(tmp_path)
    assert facts.unreadable == ["src/Weird.csproj"]
    assert facts.projects[0].role == "app"


def test_a_project_that_raises_on_read_does_not_crash_detection(tmp_path, monkeypatch):
    """`errors="replace"` only covers decode failures - a `.csproj` that
    exists but cannot be opened must not raise straight out of detect()."""
    write(tmp_path, "src/Locked/Locked.csproj", CSPROJ_UNIT)
    sln(tmp_path, "Locked.sln", ["src/Locked/Locked.csproj"])

    real_read_text = Path.read_text

    def boom(self, *args, **kwargs):
        if self.name == "Locked.csproj":
            raise PermissionError("locked")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", boom)
    facts = dotnet.detect(tmp_path)
    assert facts.unreadable == ["src/Locked/Locked.csproj"]
    assert facts.projects[0].role == "app"


# ── Fix 4: unit-test recipe candidates, and a recipe with no projects ───────

def test_a_broad_test_api_recipe_no_longer_binds_the_fast_tier(tmp_path):
    """test-api is 'run the backend suite' shaped, not 'the fast subset'
    shaped - trusting it here would put a possibly-slow suite in the fast
    tier without `classify` ever weighing in."""
    repo = _repo(task_runner="just", recipes=["test-api"])
    blocks, _ = _blocks(tmp_path, repo, integration=False)
    assert "test-api" not in blocks
    assert blocks["test-Api.Tests"].argv[0] == "dotnet"


def test_a_recipe_with_no_matching_project_still_emits_but_flags_it(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "F.sln", ["src/App/App.csproj"])
    repo = _repo(task_runner="just", recipes=["test-unit"])
    facts = dotnet.detect(tmp_path)
    blocks, unresolved = dotnet.blocks(facts, repo)
    by_name = {b.name: b for b in blocks}
    assert by_name["test-unit"].argv == ["just", "test-unit"]
    assert any("test-unit" in note and "no unit-tests project" in note
              for note in unresolved)


def test_a_recipe_that_replaces_projects_says_so_in_source(tmp_path):
    repo = _repo(task_runner="just", recipes=["test-unit", "build-sln"])
    blocks, _ = _blocks(tmp_path, repo, integration=False)
    assert "replaces 1 per-project command" in blocks["test-unit"].source


# ── Minor 11: a tie-break between two root-level solutions is noted ───────

def test_a_tie_between_two_root_solutions_is_noted(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Alpha.sln", ["src/App/App.csproj"])
    sln(tmp_path, "Zeta.sln", ["src/App/App.csproj"])
    facts = dotnet.detect(tmp_path)
    assert facts.solution == "Alpha.sln"          # alphabetically first, as before
    assert facts.other_solutions == ["Zeta.sln"]
    _, unresolved = dotnet.blocks(facts, _repo())
    assert any("Alpha.sln" in note and "Zeta.sln" in note for note in unresolved)


def test_the_shallowest_solution_wins_without_a_tie_note(tmp_path):
    """Different depths is not a tie - only same-depth candidates are noted."""
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    sln(tmp_path, "Root.sln", ["src/App/App.csproj"])
    sln(tmp_path, "src/Nested.sln", ["App/App.csproj"])
    facts = dotnet.detect(tmp_path)
    assert facts.other_solutions == []


# ── Minor 13: classify() is anchored to Include=, not a bare substring ─────

def test_classify_ignores_a_comment_and_an_unrelated_none_entry(tmp_path):
    """A bare substring match would misclassify a comment mentioning
    Testcontainers, or an unrelated <None> entry - the dangerous direction,
    since it moves a real unit suite out of the fast loop."""
    text = """<Project Sdk="Microsoft.NET.Sdk">
  <!-- migrated off Testcontainers -->
  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.0" />
    <PackageReference Include="xunit" Version="2.9.0" />
    <None Include="notes/xunit-notes.md" />
  </ItemGroup>
</Project>
"""
    assert dotnet.classify(text) == "unit-tests"


def test_classify_still_matches_a_versioned_testcontainers_package():
    """The match has to be a prefix of the attribute value: real Testcontainers
    references are `Testcontainers.PostgreSql`, `Testcontainers.MsSql`, etc,
    never the bare package name."""
    assert dotnet.classify(CSPROJ_INTEGRATION) == "integration-tests"


# ── Minor 9: real-world .sln bytes - BOM, CRLF, a path with a space ────────

def test_parses_a_real_world_sln_with_bom_crlf_and_a_space_in_the_path(tmp_path):
    write(tmp_path, "src/App/App.csproj", CSPROJ_APP)
    write(tmp_path, "src/My App/My App.csproj", CSPROJ_APP)
    body = (
        'Microsoft Visual Studio Solution File, Format Version 12.00\r\n'
        'Project("{9A19103F-16F7-4668-BE54-9A1E7A4F7556}") = "App", '
        '"src\\App\\App.csproj", "{00000001-0000-0000-0000-000000000000}"\r\n'
        'EndProject\r\n'
        'Project("{9A19103F-16F7-4668-BE54-9A1E7A4F7556}") = "My App", '
        '"src\\My App\\My App.csproj", "{00000002-0000-0000-0000-000000000000}"\r\n'
        'EndProject\r\n')
    (tmp_path / "RealWorld.sln").write_text("﻿" + body, encoding="utf-8")

    facts = dotnet.detect(tmp_path)
    assert facts.solution == "RealWorld.sln"
    assert {p.path for p in facts.projects} == {
        "src/App/App.csproj", "src/My App/My App.csproj"}


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
    # describe() lands in a generated docstring where a backslash is a live
    # escape - this is true by construction (paths are forward-slashed
    # throughout), but was unpinned.
    assert "\\" not in lines


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
