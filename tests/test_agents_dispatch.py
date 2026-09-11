"""Backend selection and config validation across two coding agents."""

from types import SimpleNamespace

import pytest

from adw_modules import agent_cc, agent_pi, agents
from adw_modules.data_types import AgentConfig, PromptEngineering


def _agent(**overrides) -> AgentConfig:
    defaults = dict(
        name="builder",
        coding_agent="claude_code",
        model="anthropic/claude-opus-5",
        thinking="medium",
        purpose="Implement the plan exactly.",
        prompt_engineering=PromptEngineering(system="system.md", user="user.md"),
        tools=["read", "bash"],
        harness_engineering=[],
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def test_claude_code_agents_dispatch_to_agent_cc():
    assert agents.backend_for(_agent()) is agent_cc


def test_pi_agents_dispatch_to_agent_pi():
    assert agents.backend_for(_agent(coding_agent="pi",
                                     model="google/gemini-3.6-flash")) is agent_pi


def test_an_unknown_backend_is_rejected():
    # AgentConfig.coding_agent is a Literal["pi", "claude_code"], so a real
    # AgentConfig can never carry an unrecognised backend name — pydantic
    # would refuse it before backend_for ever runs. Exercise backend_for's
    # own guard directly with a stand-in that carries the attributes it reads.
    unknown = SimpleNamespace(name="builder", coding_agent="cursor")
    with pytest.raises(SystemExit, match="unknown coding_agent"):
        agents.backend_for(unknown)


def test_harness_engineering_on_claude_code_is_a_config_error():
    problems = agent_cc.validate_agent(_agent(harness_engineering=["subagents.ts"]))

    assert problems
    assert "harness_engineering" in problems[0]


def test_a_pi_extension_tool_on_claude_code_is_a_config_error():
    problems = agent_cc.validate_agent(_agent(tools=["read", "subagent_create"]))

    assert problems
    assert "subagent_create" in problems[0]


def test_a_clean_claude_code_agent_has_no_problems():
    assert agent_cc.validate_agent(_agent()) == []
