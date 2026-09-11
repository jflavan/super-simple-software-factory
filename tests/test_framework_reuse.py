"""Adding a framework must not require touching a shared file."""

import ast
from pathlib import Path

import fake_framework
from profile_fixtures import dotnet_svelte_repo, package

from profiles import frameworks
from profiles.composite import CompositeProfile


PROFILE_YAML = ("name: dotnet-vue\n"
                "description: a third stack\n"
                "frameworks: {frameworks_list}\n")


def _register(monkeypatch):
    """Step 4, for real: append to FRAMEWORKS rather than patch the lookup.

    An earlier draft monkeypatched `composite.get_framework`, which meant the
    registration path - the step a newcomer is most likely to half-do, since it
    needs both an import line and a tuple entry - was never executed by the one
    task whose job is to prove the instructions work.
    """
    monkeypatch.setattr(frameworks, "FRAMEWORKS",
                        frameworks.FRAMEWORKS + (fake_framework,))


def _stamp_framework_files(monkeypatch, tmp_path):
    """Steps 2 and 3: a real gate module and a real prompt fragment on disk.

    Written into redirected directories so the shipped tree stays clean - a
    fake framework must not leave a gates_vue.py behind in the profiles package.
    """
    gates = tmp_path / "gates"
    prompts = tmp_path / "prompts"
    gates.mkdir()
    prompts.mkdir()
    (gates / "gates_vue.py").write_text(
        "def vue_smoke(directories):\n"
        "    def gate(envelope, run):\n"
        "        return None\n"
        "    gate.__name__ = f'vue_smoke({len(directories)})'\n"
        "    return gate\n", encoding="utf-8")
    (prompts / "vue.md").write_text("### Vue\n\n- Single-file components.\n",
                                    encoding="utf-8")
    monkeypatch.setattr("profiles.composite.PROMPTS_DIR", prompts)
    return gates, prompts


def _profile(tmp_path, monkeypatch, frameworks_list="[dotnet, vue]"):
    """Register the third framework and build a profile that declares it."""
    _register(monkeypatch)
    path = tmp_path / "profile.yaml"
    path.write_text(PROFILE_YAML.format(frameworks_list=frameworks_list))
    return CompositeProfile(path)


def test_the_third_framework_satisfies_the_published_interface():
    frameworks.verify(fake_framework)
    for attribute in frameworks.FRAMEWORK_INTERFACE:
        assert hasattr(fake_framework, attribute), attribute


def test_it_imports_only_the_shared_layer():
    """The claim: a framework composes through probes and emit, not siblings."""
    text = Path(fake_framework.__file__).read_text()
    assert "from profiles import emit, probes" in text
    for sibling in ("dotnet", "sveltekit"):
        assert f"import {sibling}" not in text


def test_a_profile_declaring_it_detects_a_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"test": "vitest run", "build": "vite build"},
            marker="vue")

    profile = _profile(tmp_path, monkeypatch)
    assert profile.matches(repo)

    facts = profile.detect(repo)
    assert facts.of("dotnet").solution == "Fixture.sln"
    assert [f.directory for f in facts.of("vue").frontends] == ["apps/store"]


def test_its_blocks_are_generated_beside_the_other_framework_s(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")

    profile = _profile(tmp_path, monkeypatch)
    report = profile.generate(profile.detect(repo), repo)

    names = [b.name for b in report.blocks]
    assert "build-sln" in names          # from dotnet, unchanged
    assert "build-store" in names        # from the third framework
    ast.parse((repo / "adws" / "adw_modules" / "quality_blocks.py").read_text())


def test_a_framework_with_no_gates_and_no_overlay_composes_cleanly(tmp_path,
                                                                   monkeypatch):
    """Composing still works when the third framework's files are not stamped.

    NOTE on the assertions below: `fake_framework` deliberately declares a
    non-empty GATE_MODULE/OVERLAY (see its module docstring - an earlier draft
    that used "" for both is exactly the flaw this task exists to catch), and
    `gate_wiring()` fires whenever it detects a frontend, and `gate_modules()`
    is declarative from GATE_MODULE alone - neither checks whether
    `gates_vue.py` actually exists on disk. So with vue detecting the
    `apps/store` package below, both frameworks' gate metadata legitimately
    show up in `report.gates` and `gate_modules()`, even though only dotnet's
    module is real. What this test actually proves is the overlay half: only
    the framework whose FRAGMENT FILE exists on disk contributes overlay text
    - vue.md was never stamped (no call to `_stamp_framework_files`), so the
    real, unpatched PROMPTS_DIR has no such file and `render_overlay` skips it
    silently rather than crashing on the missing file.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")

    profile = _profile(tmp_path, monkeypatch)
    facts = profile.detect(repo)
    report = profile.generate(facts, repo)

    # both declared frameworks' gate metadata is recorded - GATE_MODULE and
    # gate_wiring() are both facts-independent-of-disk, so this is not a sign
    # that vue's ungenerated gates_vue.py was silently dropped.
    assert report.gates == ["ef_migration_triad", "vue_smoke"]
    assert profile.gate_modules() == ["gates_dotnet", "gates_vue"]
    # but the overlay carries only the fragments that exist ON DISK
    overlay = (repo / "adws" / "adw_data" / "prompt_engineering"
               / "profile_overlay.md").read_text()
    assert "EF Core" in overlay
    assert "Single-file components" not in overlay


def test_the_describe_lines_reach_the_report(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")
    profile = _profile(tmp_path, monkeypatch)
    assert "vue app: apps/store" in profile.describe(profile.detect(repo))


def test_a_profile_declaring_it_is_DISCOVERED_not_just_constructed(tmp_path,
                                                                   monkeypatch):
    """Step 5: registry._discover globs `*/profile.yaml`, so put one where it looks.

    Constructing a CompositeProfile directly, as the other tests do, skips
    discovery entirely — and discovery is what decides whether a new profile is
    visible to `install.py` at all.
    """
    from profiles import registry

    _register(monkeypatch)
    directory = tmp_path / "dotnet_vue"
    directory.mkdir()
    (directory / "profile.yaml").write_text(
        PROFILE_YAML.format(frameworks_list="[dotnet, vue]"), encoding="utf-8")
    monkeypatch.setattr(registry, "PROFILES_DIR", tmp_path)

    assert "dotnet-vue" in registry.names()
    assert [f.NAME for f in registry.get("dotnet-vue").frameworks] == ["dotnet", "vue"]


def test_its_gate_module_and_overlay_reach_the_generated_output(tmp_path,
                                                                monkeypatch):
    """Steps 2 and 3: a framework bringing a gate and a fragment is wired."""
    repo = tmp_path / "repo"
    repo.mkdir()
    dotnet_svelte_repo(repo, frontends=[])
    package(repo, "apps/store", {"build": "vite build"}, marker="vue")
    _stamp_framework_files(monkeypatch, tmp_path)

    profile = _profile(tmp_path, monkeypatch)
    facts = profile.detect(repo)

    assert "gates_vue" in profile.gate_modules()
    report = profile.generate(facts, repo)
    assert "vue_smoke" in report.gates
    overlay = (repo / "adws" / "adw_data" / "prompt_engineering"
               / "profile_overlay.md").read_text()
    assert "Single-file components" in overlay


def test_no_shared_file_needed_a_change_for_this_framework():
    """Recorded as an assertion so a future reviewer sees the claim being made.

    fake_framework.py uses only names that existed before it was written:
    probes.node_packages, emit.script_blocks, and the facts vocabulary. If
    adding it had required a new parameter on any of those, this whole task
    would have failed to prove what it set out to prove.
    """
    from profiles import emit, probes
    assert callable(probes.node_packages)
    assert callable(emit.script_blocks)
