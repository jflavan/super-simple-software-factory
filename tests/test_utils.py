"""utils: argv resolution and the operator environment."""

from pathlib import Path

from adw_modules import utils


def test_resolve_argv_finds_a_real_binary():
    resolved = utils.resolve_argv(["git", "status"])

    assert Path(resolved[0]).is_absolute()
    assert Path(resolved[0]).stem == "git"
    assert resolved[1:] == ["status"]


def test_resolve_argv_passes_a_missing_binary_through_unchanged():
    # Unresolvable argv must survive intact so the caller's existing exit-127
    # path still reports a genuinely missing binary.
    argv = ["sssf-definitely-not-a-real-binary", "--version"]

    assert utils.resolve_argv(argv) == argv


def test_resolve_argv_handles_an_empty_argv():
    assert utils.resolve_argv([]) == []
