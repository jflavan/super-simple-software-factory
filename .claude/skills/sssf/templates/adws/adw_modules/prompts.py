"""Prompt rendering: load system/user refs from config, replace {{placeholders}}."""

from __future__ import annotations

from pathlib import Path


def render(template_path: str | Path, variables: dict[str, str]) -> str:
    # Explicit utf-8, not the locale codec. Every starter prompt contains an
    # em dash; read as cp1252 on a default Windows install each one became
    # three mojibake characters IN THE PROMPT THE MODEL WAS SENT, silently,
    # on every call. The file on disk was never the file the agent read.
    text = Path(template_path).read_text(encoding="utf-8")
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def save(directory: str | Path, name: str, content: str) -> Path:
    """Save the exact prompt sent, before execution — the audit copy."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(content, encoding="utf-8", newline="\n")
    return path
