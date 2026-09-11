"""Profile discovery, lookup, and auto-detection.

The one module install.py imports. Profiles are found by scanning for
`*/profile.yaml` next to this file, so adding a stack means adding a directory
with a YAML file in it - no registration, no import, no core change.
"""

from __future__ import annotations

from pathlib import Path

from .composite import CompositeProfile

PROFILES_DIR = Path(__file__).resolve().parent


def _discover() -> list[CompositeProfile]:
    return sorted((CompositeProfile(path)
                   for path in PROFILES_DIR.glob("*/profile.yaml")),
                  key=lambda profile: profile.NAME)


def all_profiles() -> list[CompositeProfile]:
    # Re-read on every call rather than caching at import: an installer runs
    # once, and a stale cache would be a confusing way to lose a profile
    # somebody just added.
    return _discover()


def names() -> list[str]:
    return [profile.NAME for profile in all_profiles()]


def get(name: str) -> CompositeProfile:
    for profile in all_profiles():
        if profile.NAME == name:
            return profile
    raise SystemExit(f"unknown profile {name!r} - available: {', '.join(names())}")


def detect_all(root) -> list[str]:
    """Every profile that claims this repo."""
    root = Path(root)
    return [profile.NAME for profile in all_profiles() if profile.matches(root)]


def select(root) -> CompositeProfile | None:
    """The profile to apply, or None when none matches.

    Refuses to choose between two matches. Wiring a repo to the wrong stack
    produces a factory whose checks all pass because none of them run anything
    real - the exact failure this mechanism exists to prevent - so ambiguity
    stops the install and asks.
    """
    matched = detect_all(root)
    if not matched:
        return None
    if len(matched) > 1:
        raise SystemExit(
            f"{len(matched)} profiles match this repo: {', '.join(matched)}. "
            f"Pick one with --profile <name>, or skip profiles with --no-profile.")
    return get(matched[0])
