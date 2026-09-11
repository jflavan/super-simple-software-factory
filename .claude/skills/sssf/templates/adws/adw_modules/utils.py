"""Small shared helpers. Anything bigger belongs in its own module."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def venv_bin_dir(venv: str, windows: bool | None = None) -> str:
    """The directory a virtualenv puts executables in.

    Split out, with an explicit `windows` flag, so both branches are testable
    on either platform. uv writes to `Scripts` on Windows and `bin` elsewhere;
    operator_env previously stripped only `bin`, so on Windows it stripped
    nothing and the shadowing hazard it documents went unmitigated.
    """
    if windows is None:
        windows = os.name == "nt"
    return str(Path(venv) / ("Scripts" if windows else "bin"))


def _comparable_path(path: str) -> str:
    """A PATH entry reduced to a form two spellings of the same directory share.

    normpath collapses `..` and redundant separators; normcase folds case and
    slash direction on Windows. Neither resolves symlinks — that needs the path
    to exist and costs a stat per PATH entry, which is not worth it for a
    comparison whose worst failure is leaving one extra directory on PATH.
    """
    return os.path.normcase(os.path.normpath(path))


def operator_env() -> dict[str, str]:
    """The engineer's own environment, as their shell would hand it over.

    Agents and quality blocks are meant to see exactly what the operator sees:
    their PATH, their toolchains, their globally installed packages. Copying
    os.environ gets almost all the way there — but ADWs launch under `uv run`,
    which prepends its ephemeral venv's bin to PATH and sets VIRTUAL_ENV. That
    venv holds the ADW's OWN dependencies (pydantic, pyyaml), not the
    operator's, so anything a subprocess resolves through it — `python3`,
    `pip`, every globally pip-installed CLI — silently becomes the wrong one.

    Stripping the venv restores parity: `python3` in an agent's bash is the
    same `python3` the engineer gets in their terminal. The ADW's own imports
    are unaffected; this env is only ever handed to child processes.
    """
    env = os.environ.copy()
    venv = env.pop("VIRTUAL_ENV", "")
    if not venv:
        return env
    venv_bin = _comparable_path(venv_bin_dir(venv))
    parts = [p for p in env.get("PATH", "").split(os.pathsep)
             if p and _comparable_path(p) != venv_bin]
    env["PATH"] = os.pathsep.join(parts)
    return env


def resolve_argv(argv: list[str]) -> list[str]:
    """Resolve argv[0] to an absolute executable path.

    On Windows `npm` is `npm.cmd`, and a bare-name argv raises WinError 2 in
    subprocess.run — which quality.py catches as an OSError and reports as
    exit 127, making a PATH problem indistinguishable from a command that ran
    and failed. shutil.which honours PATHEXT, so it finds the shim.

    When nothing resolves, the argv is returned unchanged: that failure is a
    genuinely missing binary, and the existing exit-127 path reports it
    correctly with the real message.
    """
    if not argv:
        return list(argv)
    found = shutil.which(argv[0])
    return [found, *argv[1:]] if found else list(argv)


def new_id(length: int = 8) -> str:
    return secrets.token_hex(length // 2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_prompt(arg: str) -> str:
    """CLI prompt arg: a file path resolves to its contents, else inline text."""
    try:
        p = Path(arg)
        if p.is_file():
            return p.read_text()
    except OSError:
        pass
    return arg


def engineer_name() -> str:
    name = os.environ.get("ENGINEER_NAME", "").strip()
    if name:
        return name
    try:
        out = subprocess.run(["git", "config", "user.name"],
                             capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except OSError:
        pass
    return os.environ.get("USER", "engineer")


@lru_cache(maxsize=512)
def glob_to_regex(pattern: str) -> re.Pattern:
    """Translate a path glob, with `*` stopping at a path separator.

    fnmatch would let `*` cross `/`, which quietly widens every pattern:
    `adws/adw_*.py` would match `adws/adw_data/sessions/x/y.py` as well as the
    ADW scripts it means. `**` is the way to say "cross directories".

    `**/` matches zero or more directories, so `**/*.md` covers `README.md` at
    the root as well as `docs/a/b.md`. Requiring at least one directory there
    is a trap: the pattern reads as "any markdown file anywhere" and every
    author who writes it means that.
    """
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def path_matches(path: str, pattern: str) -> bool:
    """One path against one pattern: prefix, glob, or exact equality.

    Backslashes are folded to forward slashes first. git reports forward
    slashes on every platform, but an agent reporting `changed_files` on
    Windows may not, and a permission check that silently stops matching on
    one platform is the worst possible failure of a permission check.
    """
    path = str(path).replace("\\", "/")
    if pattern.endswith("/"):                      # directory prefix
        return path.startswith(pattern)
    if "*" in pattern or "?" in pattern:
        return glob_to_regex(pattern).fullmatch(path) is not None
    return path == pattern


def repo_relative(path: str, repo_root: str) -> str:
    """An agent's reported path, reduced to the repo-relative form rules use.

    Envelopes carry whatever shape the model wrote: absolute, `./`-prefixed, or
    already relative. Every rule in this system — `writes:`, `doc_policy`, the
    stack gates — is written repo-relative, so the normalization happens once,
    here, rather than in each of them slightly differently.
    """
    text = str(path).replace("\\", "/")
    root = str(repo_root).replace("\\", "/").rstrip("/")
    if root and text.startswith(root + "/"):
        return text[len(root) + 1:]
    return text[2:] if text.startswith("./") else text


def changed_files(envelope, run) -> list[str]:
    """Every path an envelope claims to have changed, repo-relative."""
    return [repo_relative(f, getattr(run, "repo_root", ""))
            for f in getattr(envelope, "changed_files", [])]


def read_text(path) -> str:
    """File text, or empty when it is gone.

    A gate reads files the change touched, and `changed_files` includes
    DELETIONS — so "the file is not there" is an ordinary case, not an error.
    """
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""
