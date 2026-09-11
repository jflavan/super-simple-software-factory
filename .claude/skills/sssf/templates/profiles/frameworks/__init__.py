"""Framework modules: one per technology, all the same shape.

ADDING A FRAMEWORK
------------------
1. Write `frameworks/<name>.py` exposing the eight names in
   FRAMEWORK_INTERFACE. Copy `sveltekit.py` for a frontend or `dotnet.py` for
   a backend - both are deliberately short.
2. If it brings gates, write `gates/<GATE_MODULE>.py`. It is STAMPED into a
   target repo's adw_modules/, so its imports are relative.
3. If it has prompt guidance, write `prompts/<OVERLAY>`.
4. Add it to FRAMEWORKS below.
5. Create `<profile_dir>/profile.yaml` naming it alongside whatever it pairs
   with. No core module changes, and no other framework changes.

A framework must NOT import another framework. Shared work lives in `probes`
(finding things) and `emit` (writing things), which is why pairing .NET with a
second frontend costs one file rather than a fork of this one.
"""

from types import ModuleType

from . import dotnet, sveltekit

# What a profile driver may call on any framework.
FRAMEWORK_INTERFACE = (
    "NAME",           # str: the id it registers under
    "GATE_MODULE",    # str: gate file to stamp, "" for none
    "OVERLAY",        # str: prompt fragment filename, "" for none
    "matches",        # (root) -> bool
    "detect",         # (root) -> FrameworkFacts subclass
    "blocks",         # (facts, repo) -> (list[QualityBlock], list[str])
    "describe",       # (facts) -> list[str], rendered into a generated
                      #   module's DOCSTRING - return normalized paths, because
                      #   a backslash there is a live escape sequence
    "gate_wiring",    # (facts) -> list[GateWiring]
)


def verify(module) -> None:
    """Fail at import, naming what is missing, rather than at first use."""
    missing = [a for a in FRAMEWORK_INTERFACE if not hasattr(module, a)]
    if missing:
        raise ImportError(
            f"framework {getattr(module, 'NAME', module)!r} is missing "
            f"{', '.join(missing)} - see FRAMEWORK_INTERFACE")


FRAMEWORKS: tuple[ModuleType, ...] = (dotnet, sveltekit)

for _framework in FRAMEWORKS:
    verify(_framework)


def names() -> list[str]:
    return sorted(f.NAME for f in FRAMEWORKS)


def get(name: str) -> ModuleType:
    for framework in FRAMEWORKS:
        if framework.NAME == name:
            return framework
    raise SystemExit(f"unknown framework {name!r} - available: {', '.join(names())}")
