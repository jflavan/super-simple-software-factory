"""A third framework, built from the shared pieces alone.

This is the acceptance test for the framework interface. It imports `probes`,
`emit`, and `facts` - never `dotnet` or `sveltekit` - and it required no change
to any of them. If a future change to the shared layer breaks this file, the
shared layer has grown a framework-specific assumption.

It pretends to be Vue rather than Angular deliberately: Angular is the real
next profile and deserves real detection written against a real repo, not a
stub that makes the tests pass.
"""

from pydantic import Field

from profiles import emit, probes
from profiles.facts import FrameworkFacts, Frontend, GateWiring, ProfileFacts, QualityBlock

NAME = "vue"
# Deliberately NON-empty. An earlier draft set both to "" so this framework
# brought no gate module and no prompt fragment - which meant the acceptance
# test exercised step 1 of ADDING A FRAMEWORK and skipped steps 2 and 3, the
# two it most needed to prove. The files these name are created by the test.
GATE_MODULE = "gates_vue"
OVERLAY = "vue.md"

MARKER = "vue"

SCRIPTS = [
    ("test", ["test-{name}"], "test", "test"),
    ("build", ["build-{name}"], "build", "build"),
]


class VueFacts(FrameworkFacts):
    frontends: list[Frontend] = Field(default_factory=list)


def matches(root) -> bool:
    return bool(probes.node_packages(root, MARKER))


def detect(root) -> VueFacts:
    return VueFacts(frontends=probes.node_packages(root, MARKER))


def blocks(facts: VueFacts, repo: ProfileFacts) -> tuple[list[QualityBlock], list[str]]:
    return emit.script_blocks(facts.frontends, repo, SCRIPTS)


def describe(facts: VueFacts) -> list[str]:
    return [f"vue app: {f.directory}" for f in facts.frontends]


def gate_wiring(facts: VueFacts) -> list[GateWiring]:
    """One gate per frontend found, so the wiring path is actually exercised.

    A framework that wires nothing would let render_gates_module go untested by
    this task, which is the one task whose job is to prove a new framework
    reaches every part of the machinery.
    """
    if not facts.frontends:
        return []
    return [GateWiring(module=GATE_MODULE, name="vue_smoke",
                       call=f"vue_smoke({[f.directory for f in facts.frontends]!r})")]
