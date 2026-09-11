"""The profile overlay: framework fragments, composed per profile."""

from pathlib import Path
from types import SimpleNamespace

from profile_fixtures import dotnet_svelte_repo, write

from adw_modules import agents
from profiles import registry

TEMPLATES = (Path(__file__).resolve().parent.parent
             / ".claude" / "skills" / "sssf" / "templates")
OVERLAY = "adws/adw_data/prompt_engineering/profile_overlay.md"


def _generate(tmp_path, **kwargs):
    dotnet_svelte_repo(tmp_path, **kwargs)
    profile = registry.get("dotnet-svelte")
    profile.generate(profile.detect(tmp_path), tmp_path)
    return (tmp_path / OVERLAY).read_text()


def test_the_shipped_builder_prompt_has_the_placeholder():
    text = (TEMPLATES / "prompt_engineering" / "builder" / "system.md").read_text()
    assert "{{profile_overlay}}" in text


def test_the_shipped_builder_prompt_names_no_toolchain():
    """bun/uv/pytest were THIS repo's tools, not every repo's.

    Matched on the backticked forms the prompt actually used, not bare
    substrings: `uv` appears inside ordinary English words and a test that
    fails on the word "value" teaches nobody anything.
    """
    text = (TEMPLATES / "prompt_engineering" / "builder" / "system.md").read_text()
    for tool in ("`bun`", "`uv`", "`pytest`"):
        assert tool not in text
    assert "stack notes below" in text


def test_every_framework_that_declares_an_overlay_has_the_file():
    from profiles import frameworks
    for name in frameworks.names():
        overlay = frameworks.get(name).OVERLAY
        if overlay:
            assert (TEMPLATES / "profiles" / "prompts" / overlay).is_file(), name


def test_the_overlay_is_empty_when_no_profile_generated_one(tmp_path):
    run = SimpleNamespace(cfg=SimpleNamespace(
        defaults=SimpleNamespace(data_dir=str(tmp_path / "adw_data"))))
    assert agents.profile_overlay(run) == ""


def test_the_overlay_is_read_when_it_exists(tmp_path):
    overlay = tmp_path / "adw_data" / "prompt_engineering" / "profile_overlay.md"
    overlay.parent.mkdir(parents=True)
    overlay.write_text("## Stack\n\nrunes, not stores.\n")
    run = SimpleNamespace(cfg=SimpleNamespace(
        defaults=SimpleNamespace(data_dir=str(tmp_path / "adw_data"))))
    assert "runes, not stores" in agents.profile_overlay(run)


def test_generation_writes_the_overlay(tmp_path):
    dotnet_svelte_repo(tmp_path)
    profile = registry.get("dotnet-svelte")
    report = profile.generate(profile.detect(tmp_path), tmp_path)
    assert str(tmp_path / OVERLAY) in [str(Path(f)) for f in report.files]


def test_the_overlay_contains_a_fragment_per_declared_framework(tmp_path):
    text = _generate(tmp_path)
    assert "EF Core" in text           # from dotnet.md
    assert "runes" in text             # from sveltekit.md


def test_the_overlay_references_conventions_rather_than_restating_them(tmp_path):
    dotnet_svelte_repo(tmp_path)
    write(tmp_path, "CLAUDE.md", "NEVER use var in C#.\n")
    write(tmp_path, ".github/instructions/csharp.instructions.md", "# c#\n")
    profile = registry.get("dotnet-svelte")
    profile.generate(profile.detect(tmp_path), tmp_path)

    text = (tmp_path / OVERLAY).read_text()

    assert "CLAUDE.md" in text
    assert ".github/instructions/" in text
    assert "NEVER use var" not in text        # the CONTENT is never copied in


def test_the_overlay_names_the_detected_task_runner(tmp_path, monkeypatch):
    from profiles import probes
    # Forces the offline marker-parser fallback deterministically, regardless
    # of whether `just` happens to be installed on the machine running this
    # suite - matching the (None, reason) shape _summary always returns (see
    # tests/test_probes.py), not a bare None, which task_runner cannot unpack.
    monkeypatch.setattr(probes, "_summary",
                        lambda runner, root: (None, "just is not installed"))
    text = _generate(tmp_path, justfile_text="test-unit:\n    dotnet test\n")
    assert "just" in text


def test_the_overlay_says_so_when_there_are_no_conventions(tmp_path):
    text = _generate(tmp_path)
    assert "no convention files" in text.lower()
