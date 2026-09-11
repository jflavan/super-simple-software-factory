"""The composite driver: profiles are data, frameworks do the work."""

import ast

import pytest
from profile_fixtures import dotnet_svelte_repo, package, write

from profiles.composite import CompositeProfile


def _profile(tmp_path, frameworks="[dotnet, sveltekit]", name="test-stack"):
    """A profile is a YAML file. That is the whole point, so tests write one."""
    path = tmp_path / "profile.yaml"
    path.write_text(f"name: {name}\ndescription: a test stack\n"
                    f"frameworks: {frameworks}\n")
    return CompositeProfile(path)


def test_a_profile_is_built_from_its_yaml(tmp_path):
    profile = _profile(tmp_path)
    assert profile.NAME == "test-stack"
    assert profile.description == "a test stack"
    assert [f.NAME for f in profile.frameworks] == ["dotnet", "sveltekit"]


def test_an_unknown_framework_in_a_profile_fails_loudly(tmp_path):
    with pytest.raises(SystemExit) as error:
        _profile(tmp_path, frameworks="[dotnet, cobol]")
    assert "cobol" in str(error.value)


def test_matching_requires_every_declared_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    profile = _profile(tmp_path)

    package(repo, "web", {"build": "x"})          # sveltekit only
    assert not profile.matches(repo)

    dotnet_svelte_repo(repo)                      # now both
    assert profile.matches(repo)


def test_a_single_framework_profile_matches_on_its_own(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    package(repo, "web", {"build": "x"})
    assert _profile(tmp_path, frameworks="[sveltekit]").matches(repo)


def test_detect_fills_repo_facts_and_every_framework_section(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "CLAUDE.md", "# rules\n")

    facts = _profile(tmp_path).detect(repo)

    assert facts.profile == "test-stack"
    assert facts.conventions == ["CLAUDE.md"]
    assert facts.of("dotnet").solution == "Fixture.sln"
    assert [f.directory for f in facts.of("sveltekit").frontends] == ["apps/web"]


def test_describe_concatenates_every_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    lines = "\n".join(profile.describe(profile.detect(repo)))
    assert "Fixture.sln" in lines
    assert "apps/web" in lines


def test_generate_writes_the_blocks_module(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo)

    generated = repo / "adws" / "adw_modules" / "quality_blocks.py"
    assert generated.is_file()
    assert str(generated) in report.files
    ast.parse(generated.read_text())
    assert "PLACEHOLDER" not in generated.read_text()


def test_the_blocks_come_from_both_frameworks(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    names = [b.name for b in profile.generate(profile.detect(repo), repo).blocks]
    assert "build-sln" in names          # dotnet
    assert "check-web" in names          # sveltekit


def test_the_header_records_what_was_detected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    profile.generate(profile.detect(repo), repo)
    text = (repo / "adws" / "adw_modules" / "quality_blocks.py").read_text()
    assert "Fixture.sln" in text
    assert "apps/web" in text


def test_unresolved_notes_are_collected_from_every_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, integration=False, frontends=[])
    package(repo, "web", {"dev": "vite"})          # no check/test/build/lint
    profile = _profile(tmp_path)
    report = profile.generate(profile.detect(repo), repo, write=False)
    joined = " ".join(report.unresolved)
    assert "integration-tests" in joined           # from dotnet
    assert "web" in joined                         # from sveltekit


def test_a_dry_run_writes_nothing_but_still_reports(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo, write=False)

    assert report.files == []
    assert report.blocks
    assert not (repo / "adws" / "adw_modules" / "quality_blocks.py").exists()


def test_two_frameworks_emitting_the_same_block_name_stop_the_install(tmp_path,
                                                                     monkeypatch):
    """A silently dropped block is a check that stopped running."""
    from profiles.facts import QualityBlock
    from profiles.frameworks import sveltekit

    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    monkeypatch.setattr(sveltekit, "blocks", lambda facts, repo_facts: (
        [QualityBlock(name="build-sln", area="frontend", operation="build",
                      argv=["npm", "run", "build"])], []))

    profile = _profile(tmp_path)
    with pytest.raises(SystemExit) as error:
        profile.generate(profile.detect(repo), repo, write=False)
    assert "build-sln" in str(error.value)


def test_gate_modules_lists_what_the_declared_frameworks_need_stamped(tmp_path):
    assert _profile(tmp_path).gate_modules() == ["gates_dotnet", "gates_sveltekit"]
