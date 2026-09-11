"""The composite driver: profiles are data, frameworks do the work."""

import ast

import pytest
from profile_fixtures import dotnet_svelte_repo, package, write

from profiles import emit
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


def test_a_profile_that_is_not_yaml_names_the_file(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("name: [unclosed\n")
    with pytest.raises(SystemExit, match="profile.yaml"):
        CompositeProfile(path)


def test_a_profile_that_is_not_a_mapping_names_the_file(tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("- dotnet\n- sveltekit\n")
    with pytest.raises(SystemExit, match="mapping"):
        CompositeProfile(path)


def test_a_frameworks_string_is_refused_rather_than_iterated(tmp_path):
    """`frameworks: dotnet` used to iterate characters and report 'unknown framework d'."""
    path = tmp_path / "profile.yaml"
    path.write_text("name: x\nframeworks: dotnet\n")
    with pytest.raises(SystemExit, match="non-empty list"):
        CompositeProfile(path)


def test_a_profile_declaring_no_frameworks_is_refused(tmp_path):
    """It would generate a factory that checks nothing and report a clean install."""
    path = tmp_path / "profile.yaml"
    path.write_text("name: x\nframeworks: []\n")
    with pytest.raises(SystemExit, match="non-empty list"):
        CompositeProfile(path)


def test_a_missing_name_falls_back_to_the_directory_with_hyphens(tmp_path):
    directory = tmp_path / "dotnet_svelte"
    directory.mkdir()
    path = directory / "profile.yaml"
    path.write_text("frameworks: [dotnet]\n")
    assert CompositeProfile(path).NAME == "dotnet-svelte"


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


def test_a_dry_run_still_renders_so_doctor_can_prove_the_module_imports(tmp_path,
                                                                       monkeypatch):
    """The render is what runs ast.parse. Skipping it on a dry run would make
    --doctor unable to report the one failure it exists to catch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    calls = []
    real = emit.render_blocks_module
    monkeypatch.setattr(emit, "render_blocks_module",
                        lambda *a, **k: calls.append(1) or real(*a, **k))

    profile.generate(profile.detect(repo), repo, write=False)

    assert calls == [1]


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
    message = str(error.value)
    assert "build-sln (from dotnet)" in message
    assert "build-sln (from sveltekit)" in message


def test_a_case_only_block_name_clash_names_both_original_spellings(tmp_path,
                                                                     monkeypatch):
    """Folded matching is right (filesystems collide on case), but the message
    must still name the real spellings or grepping for the reported name
    ('build-sln') will never find the other one ('build-SLN')."""
    from profiles.facts import QualityBlock
    from profiles.frameworks import sveltekit

    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    monkeypatch.setattr(sveltekit, "blocks", lambda facts, repo_facts: (
        [QualityBlock(name="build-SLN", area="frontend", operation="build",
                      argv=["npm", "run", "build"])], []))

    profile = _profile(tmp_path)
    with pytest.raises(SystemExit) as error:
        profile.generate(profile.detect(repo), repo, write=False)
    message = str(error.value)
    assert "build-sln (from dotnet)" in message
    assert "build-SLN (from sveltekit)" in message


def test_gate_modules_lists_what_the_declared_frameworks_need_stamped(tmp_path):
    assert _profile(tmp_path).gate_modules() == ["gates_dotnet", "gates_sveltekit"]


def test_generate_writes_the_gates_module(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "apps/web/.env.example", "PUBLIC_X=\n")
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo)

    generated = repo / "adws" / "adw_modules" / "profile_gates.py"
    assert generated.is_file()
    assert str(generated) in report.files
    ast.parse(generated.read_text())


def test_the_wired_gates_come_from_every_framework(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "apps/web/.env.example", "PUBLIC_X=\n")
    # Must actually name a directive, not merely mention "csp" - see
    # test_framework_sveltekit.py's marker tests for the exact contract.
    write(repo, "apps/web/src/hooks.server.ts", "// csp: default-src 'self';\n")
    profile = _profile(tmp_path)

    report = profile.generate(profile.detect(repo), repo, write=False)

    assert report.gates == ["ef_migration_triad", "env_example_sync", "sveltekit_csp"]


def test_a_gate_whose_fact_is_absent_is_not_wired(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    report = profile.generate(profile.detect(repo), repo, write=False)
    assert report.gates == ["ef_migration_triad"]


def test_the_generated_wiring_builds_real_callables(tmp_path):
    """Execute the generated module against the real gate factories."""
    from adw_modules import gates_dotnet, gates_sveltekit

    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    write(repo, "apps/web/.env.example", "PUBLIC_X=\n")
    profile = _profile(tmp_path)
    profile.generate(profile.detect(repo), repo)

    text = (repo / "adws" / "adw_modules" / "profile_gates.py").read_text()
    namespace = {"ef_migration_triad": gates_dotnet.ef_migration_triad,
                 "env_example_sync": gates_sveltekit.env_example_sync,
                 "sveltekit_csp": gates_sveltekit.sveltekit_csp}
    body = "\n".join(line for line in text.splitlines()
                     if not line.startswith("from ."))
    exec(body, namespace)
    assert all(callable(gate) for gate in namespace["PROFILE_GATES"])


def test_a_dry_run_still_renders_the_gates_module_so_doctor_can_prove_it_imports(
        tmp_path, monkeypatch):
    """Mirrors the equivalent blocks-render test above. Both renders run an
    ast.parse self-check, so a --doctor dry run has to trigger both, not just
    whichever one an earlier draft happened to cover."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    calls = []
    real = emit.render_gates_module
    monkeypatch.setattr(emit, "render_gates_module",
                        lambda *a, **k: calls.append(1) or real(*a, **k))

    profile.generate(profile.detect(repo), repo, write=False)

    assert calls == [1]


def test_a_dry_run_still_renders_the_overlay_so_doctor_can_prove_it_too(
        tmp_path, monkeypatch):
    """Mirrors the two render tests above. The overlay is not load-bearing for
    either loader, but --doctor promising a dry run and then skipping one of
    the three renders would be a silent gap the other two tests can't catch."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo)
    profile = _profile(tmp_path)
    calls = []
    real = CompositeProfile.render_overlay
    monkeypatch.setattr(CompositeProfile, "render_overlay",
                        lambda self, *a, **k: calls.append(1) or real(self, *a, **k))

    profile.generate(profile.detect(repo), repo, write=False)

    assert calls == [1]
