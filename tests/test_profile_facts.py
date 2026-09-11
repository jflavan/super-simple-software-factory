"""The vocabulary detection and generation share."""

import pytest
from pydantic import BaseModel, ValidationError

from profiles.facts import (Frontend, FrameworkFacts, GateWiring, GenerationReport,
                            ProfileFacts, QualityBlock)


class _Fake(FrameworkFacts):
    """Stands in for a real framework's facts, so this file imports none."""
    thing: str = ""
    items: list[str] = []

    def loud(self) -> str:
        return self.thing.upper()


def test_repo_level_facts_default_to_an_empty_repo():
    facts = ProfileFacts(profile="x", repo_root=".")
    assert facts.task_runner == ""
    assert facts.recipes == []
    assert facts.default_branch == "main"
    assert facts.conventions == []
    assert facts.frameworks == {}


def test_a_framework_section_keeps_its_own_type_fields_and_methods():
    """The load-bearing property: pydantic must not downcast to the base."""
    facts = ProfileFacts(profile="x", repo_root=".",
                         frameworks={"fake": _Fake(thing="sln", items=["a"])})
    section = facts.of("fake")
    assert isinstance(section, _Fake)
    assert section.thing == "sln"
    assert section.loud() == "SLN"


def test_a_framework_section_may_be_filled_after_construction():
    """Detection fills the dict one framework at a time."""
    facts = ProfileFacts(profile="x", repo_root=".")
    facts.frameworks["fake"] = _Fake(thing="later")
    assert facts.of("fake").thing == "later"


def test_asking_for_a_framework_the_profile_does_not_declare_is_an_error():
    facts = ProfileFacts(profile="x", repo_root=".",
                         frameworks={"fake": _Fake(thing="sln")})
    with pytest.raises(KeyError) as excinfo:
        facts.of("angular")
    message = str(excinfo.value)
    assert "x" in message
    assert "angular" in message
    assert "fake" in message


def test_profile_facts_requires_its_identity():
    with pytest.raises(ValidationError):
        ProfileFacts(repo_root=".")


def test_a_frontend_knows_which_scripts_it_has():
    frontend = Frontend(directory="apps/web", package_manager="npm",
                        scripts={"check": "svelte-check", "test": "vitest run",
                                 "build": "vite build"})
    assert frontend.has("check")
    assert not frontend.has("lint")


def test_a_quality_block_defaults_to_fast_at_the_repo_root():
    block = QualityBlock(name="t", area="backend", operation="build", argv=["a"])
    assert block.tier == "fast"
    assert block.cwd == "."


def test_gate_wiring_carries_its_module_name_and_call():
    wiring = GateWiring(module="gates_dotnet", name="ef_migration_triad",
                        call="ef_migration_triad")
    assert wiring.module == "gates_dotnet"


def test_a_generation_report_lists_what_it_could_not_resolve():
    report = GenerationReport(profile="dotnet-svelte",
                              unresolved=["no frontend declares a `test` script"])
    assert report.files == []
    assert report.blocks == []
    assert report.unresolved == ["no frontend declares a `test` script"]


def test_framework_facts_is_a_plain_model_any_framework_can_extend():
    assert issubclass(FrameworkFacts, BaseModel)


def test_the_block_vocabulary_matches_the_stamped_runtime():
    """A generator must not be able to emit a value the runtime will reject.

    `facts.py` is installer-side and `data_types.py` is stamped into the target
    repo, so the two cannot share a definition without coupling the installer to
    the runtime tree. They can be pinned to each other, which is what this does:
    the day someone adds an operation to one and not the other, a generated
    block becomes a pydantic error inside an ADW run instead of here.
    """
    from typing import get_args

    from adw_modules.data_types import QualityArea as RuntimeArea
    from adw_modules.data_types import QualityOperation as RuntimeOperation
    from adw_modules.data_types import QualityTier as RuntimeTier
    from profiles.facts import QualityArea, QualityOperation, QualityTier

    assert set(get_args(QualityOperation)) == set(get_args(RuntimeOperation))
    assert set(get_args(QualityTier)) == set(get_args(RuntimeTier))
    assert set(get_args(QualityArea)) == set(get_args(RuntimeArea))


def test_a_block_refuses_a_vocabulary_it_cannot_emit():
    """The typed fields are only worth their comment if they actually reject."""
    for bad in ({"operation": "deploy"}, {"area": "database"}, {"tier": "someday"}):
        with pytest.raises(ValidationError):
            QualityBlock(**{"name": "x", "area": "backend", "operation": "build",
                            "argv": ["a"], **bad})


def test_a_gate_call_that_is_not_an_expression_is_refused():
    with pytest.raises(ValidationError):
        GateWiring(module="gates_x", name="g", call="def not_an_expression(:")


def test_a_block_cwd_may_not_climb_out_of_the_repo():
    for escape in ("/etc", "../sibling", "C:/Windows"):
        with pytest.raises(ValidationError):
            QualityBlock(name="x", area="backend", operation="build",
                         argv=["a"], cwd=escape)
