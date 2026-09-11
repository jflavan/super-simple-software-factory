"""The framework contract: eight names, checked at import."""

import pytest

from profiles import frameworks
from profiles.facts import FrameworkFacts, ProfileFacts, QualityBlock


def test_both_shipped_frameworks_are_registered():
    assert frameworks.names() == ["dotnet", "sveltekit"]


def test_every_framework_satisfies_the_interface():
    for name in frameworks.names():
        module = frameworks.get(name)
        for attribute in frameworks.FRAMEWORK_INTERFACE:
            assert hasattr(module, attribute), f"{name} is missing {attribute}"


def test_the_interface_is_the_one_documented():
    assert set(frameworks.FRAMEWORK_INTERFACE) == {
        "NAME", "GATE_MODULE", "OVERLAY",
        "matches", "detect", "blocks", "describe", "gate_wiring"}
    # The set comparison above would pass with a duplicated entry in the
    # tuple; this pins arity so a repeated name cannot hide behind it.
    assert len(frameworks.FRAMEWORK_INTERFACE) == 8


def test_an_unknown_framework_says_what_is_available():
    with pytest.raises(SystemExit) as error:
        frameworks.get("angular")
    assert "angular" in str(error.value)
    assert "sveltekit" in str(error.value)


def test_a_framework_registers_under_its_own_NAME():
    for name in frameworks.names():
        assert frameworks.get(name).NAME == name


def test_the_interface_check_rejects_an_incomplete_framework():
    """The guarantee itself: a half-written module must fail loudly."""
    from types import SimpleNamespace
    broken = SimpleNamespace(NAME="broken", GATE_MODULE="", OVERLAY="")
    with pytest.raises(ImportError) as error:
        frameworks.verify(broken)
    assert "matches" in str(error.value)


def test_duplicate_NAME_registration_is_rejected():
    """A copy-pasted framework that forgot to rename NAME must fail loudly.

    Same technique as test_the_interface_check_rejects_an_incomplete_framework:
    call the real enforcement function directly on constructed input, rather
    than mutating the module-level FRAMEWORKS in place.
    """
    from types import SimpleNamespace
    dupes = [SimpleNamespace(NAME="dotnet"), SimpleNamespace(NAME="dotnet")]
    with pytest.raises(ImportError) as error:
        frameworks.verify_unique_names(dupes)
    assert "dotnet" in str(error.value)


@pytest.mark.parametrize("name", frameworks.names())
def test_every_framework_honours_the_shape_verify_cannot_check(name, tmp_path):
    """`verify()` checks that the eight names EXIST. This checks what they do.

    Parametrized over the registry rather than written per framework, so a
    framework added next year inherits it without anyone remembering to.
    """
    module = frameworks.get(name)

    facts = module.detect(tmp_path)
    assert isinstance(facts, FrameworkFacts)

    repo = ProfileFacts(profile="p", repo_root=str(tmp_path))
    blocks, unresolved = module.blocks(facts, repo)
    assert all(isinstance(b, QualityBlock) for b in blocks)
    assert all(isinstance(note, str) for note in unresolved)

    # The one failure mode FRAMEWORK_INTERFACE names: describe() output is
    # interpolated into a generated module's DOCSTRING, where a backslash is a
    # live escape sequence.
    assert all("\\" not in line for line in module.describe(facts))

    assert all(isinstance(w.call, str) for w in module.gate_wiring(facts))


def test_no_framework_imports_another_framework():
    """Frameworks compose through probes and emit, never through each other."""
    from pathlib import Path
    for name in frameworks.names():
        text = Path(frameworks.get(name).__file__).read_text()
        for other in frameworks.names():
            if other != name:
                assert f"import {other}" not in text
                assert f"from .{other}" not in text
