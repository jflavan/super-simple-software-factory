"""The framework contract: eight names, checked at import."""

import pytest

from profiles import frameworks


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


def test_no_framework_imports_another_framework():
    """Frameworks compose through probes and emit, never through each other."""
    from pathlib import Path
    for name in frameworks.names():
        text = Path(frameworks.get(name).__file__).read_text()
        for other in frameworks.names():
            if other != name:
                assert f"import {other}" not in text
                assert f"from .{other}" not in text
