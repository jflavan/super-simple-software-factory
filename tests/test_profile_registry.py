"""Profile discovery: a directory with a profile.yaml is a profile."""

import pytest
from profile_fixtures import dotnet_svelte_repo, package

from profiles import registry


def test_the_dotnet_svelte_profile_is_discovered():
    assert "dotnet-svelte" in registry.names()


def test_a_profile_is_discovered_from_its_yaml_alone():
    """No __init__.py, no Python: a directory with a profile.yaml is enough."""
    from pathlib import Path
    directory = Path(registry.get("dotnet-svelte").path).parent
    assert sorted(p.name for p in directory.iterdir()) == ["profile.yaml"]


def test_the_profile_declares_its_frameworks():
    profile = registry.get("dotnet-svelte")
    assert [f.NAME for f in profile.frameworks] == ["dotnet", "sveltekit"]


def test_an_unknown_profile_name_says_what_is_available():
    with pytest.raises(SystemExit) as error:
        registry.get("cobol-jquery")
    assert "cobol-jquery" in str(error.value)
    assert "dotnet-svelte" in str(error.value)


def test_detect_all_finds_the_matching_profile(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert registry.detect_all(tmp_path) == ["dotnet-svelte"]


def test_detect_all_is_empty_for_an_unrecognised_repo(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    assert registry.detect_all(tmp_path) == []


def test_half_a_stack_does_not_match(tmp_path):
    package(tmp_path, "web", {"build": "x"})
    assert registry.detect_all(tmp_path) == []


def test_select_returns_none_when_nothing_matches(tmp_path):
    (tmp_path / "main.go").write_text("package main\n")
    assert registry.select(tmp_path) is None


def test_select_returns_the_single_match(tmp_path):
    dotnet_svelte_repo(tmp_path)
    assert registry.select(tmp_path).NAME == "dotnet-svelte"


def test_select_refuses_to_guess_between_two_matches(tmp_path, monkeypatch):
    dotnet_svelte_repo(tmp_path)
    monkeypatch.setattr(registry, "detect_all", lambda root: ["dotnet-svelte", "other"])
    with pytest.raises(SystemExit) as error:
        registry.select(tmp_path)
    assert "--profile" in str(error.value)


def test_the_profile_yaml_declares_no_repository_specific_paths():
    """The design rule, on the file most likely to break it."""
    from pathlib import Path
    text = Path(registry.get("dotnet-svelte").path).read_text()
    for forbidden in ("Codec", "codec-chat", "apps/web", "apps/admin", "test-api"):
        assert forbidden not in text
