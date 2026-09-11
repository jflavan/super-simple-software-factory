"""A non-ASCII filename must not walk through the permission boundary.

`permissions` is the module the whole "agents are bounded" claim rests on: it
fingerprints the tree before and after every agent call, rolls back writes the
agent was not permitted to make, and fails the phase. It decides using paths
that come back from `git`.

`git` C-quotes any byte over 0x7F by default (`core.quotePath`), so a file
named `café.txt` is reported as the literal 12-character string
`"caf\303\251.txt"` — quotes, backslashes and octal digits, all ASCII. That
string matches no glob a human would write, so `permitted()` did not recognise
it as protected and `enforce()` raised nothing. Rolling it back failed too: the
quoted form is not a pathspec `git checkout` will match.
"""

import subprocess
import sys

import pytest

from adw_modules import permissions
from adw_modules.utils import path_matches

ACCENTED = "café.txt"


def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True,
                          text=True, encoding="utf-8", errors="surrogateescape")


@pytest.fixture
def repo_with_an_accented_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "base.txt").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    try:
        (repo / ACCENTED).write_text("secret\n", encoding="utf-8")
    except (UnicodeEncodeError, OSError):          # a filesystem that refuses it
        pytest.skip("this filesystem cannot hold a non-ASCII filename")
    return repo


class _Run:
    def __init__(self, repo):
        self.repo_root = str(repo)


def test_git_really_does_quote_the_path(repo_with_an_accented_file):
    """The premise. If git stops quoting, the rest of this file is moot."""
    raw = _git(repo_with_an_accented_file, "status", "--porcelain").stdout
    assert "\\303\\251" in raw, (
        f"git no longer C-quotes by default; got {raw!r}")


def test_the_snapshot_reports_the_real_name(repo_with_an_accented_file):
    """What `permissions._git` now returns, with core.quotePath=false."""
    fingerprints = permissions.snapshot(_Run(repo_with_an_accented_file))
    assert ACCENTED in fingerprints, (
        f"the accented path is not in the snapshot under its real name: "
        f"{sorted(fingerprints)}")
    assert not any(k.startswith('"') for k in fingerprints), (
        f"a C-quoted path leaked into the snapshot: {sorted(fingerprints)}")


def test_a_protected_glob_matches_the_real_name_but_not_the_quoted_one():
    """Why the quoting mattered: the two strings are not interchangeable."""
    assert path_matches(ACCENTED, "*.txt")
    assert not path_matches('"caf\\303\\251.txt"', "*.txt")


def test_an_unrestricted_agent_is_still_barred_from_a_protected_path():
    """`writes: None` means unrestricted, and `protected_files` still wins.

    This is the bypass: with the quoted name, `permitted()` fell through every
    glob and returned `agent.writes is None` — True — so an agent could modify
    a protected file purely because its name contained a non-ASCII character.
    """
    from adw_modules.data_types import (AgentConfig, ConfigDefaults,
                                         PromptEngineering, SSSFConfig)

    cfg = SSSFConfig(defaults=ConfigDefaults(protected_files=["*.txt"],
                                             data_dir="adws/adw_data"))
    agent = AgentConfig(
        name="builder", writes=None,
        prompt_engineering=PromptEngineering(system="s.md", user="u.md"))

    assert permissions.permitted(ACCENTED, agent, cfg) is False
    # and the runtime is still writable, which is what makes a report possible
    assert permissions.permitted("adws/adw_data/x.json", agent, cfg) is True


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows filenames are UTF-16; no undecodable bytes")
def test_a_path_that_is_not_valid_utf8_round_trips_rather_than_collapsing():
    """Linux filenames are bytes and need not decode.

    `errors="replace"` would map every undecodable byte to U+FFFD, so two
    different files could fingerprint to the same key and a protected one could
    match no glob — the same bypass reached a different way. surrogateescape is
    lossless.
    """
    raw = b"bad\xff.txt"
    lossy = raw.decode("utf-8", errors="replace")
    lossless = raw.decode("utf-8", errors="surrogateescape")

    assert lossy != lossless
    assert lossless.encode("utf-8", errors="surrogateescape") == raw
    assert lossy.encode("utf-8", errors="surrogateescape") != raw
