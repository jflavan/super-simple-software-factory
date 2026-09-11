"""Claude Code interface — the second coding-agent backend.

Runs `claude -p --output-format stream-json` and tails its JSONL stdout line by
line, forwarding each event to a callback WHILE the agent works, exactly as
agent_pi does for pi. Exposes the same four names agent_pi does — `run`,
`resolve_model`, `context_window`, and a tool-call tracker — so agents.py can
dispatch between them without knowing which it holds.

Two things differ from pi and are handled here rather than leaking upward:
sessions (pi's --session-id is create-or-continue; Claude Code needs a UUID to
create and --resume to continue), and thinking (no flag; a token budget in the
environment).
"""

from __future__ import annotations

THINKING_TOKENS = {
    "off": 0,
    "minimal": 1024,
    "low": 4000,
    "medium": 10000,
    "high": 24000,
    "xhigh": 32000,
    "max": 64000,
}


def thinking_env(level: str) -> dict[str, str]:
    """SSSF's thinking level as Claude Code environment settings.

    Claude Code has no --thinking flag, so the level becomes a token budget the
    child process reads from its environment.
    """
    budget = THINKING_TOKENS.get(level)
    if budget is None:
        raise ValueError(f"unknown thinking level {level!r} — expected one of "
                         f"{', '.join(THINKING_TOKENS)}")
    return {} if budget == 0 else {"MAX_THINKING_TOKENS": str(budget)}


def apply_thinking(env: dict[str, str], level: str) -> dict[str, str]:
    """Make `env` reflect `level`, and return it.

    A dict of things to SET cannot express "off": the child environment starts
    as a copy of the operator's, so leaving MAX_THINKING_TOKENS alone lets an
    inherited value through and an agent configured `off` thinks anyway. The
    variable is therefore always removed first, then set only when the level
    asks for a budget.
    """
    env.pop("MAX_THINKING_TOKENS", None)
    env.update(thinking_env(level))
    return env


TOOL_NAMES = {
    "read": "Read",
    "bash": "Bash",
    "edit": "Edit",
    "write": "Write",
    "grep": "Grep",
    "find": "Glob",
    "ls": "Bash",
}


def allowed_tools(tools: list[str] | None) -> list[str] | None:
    """SSSF's tool names as a Claude Code --allowedTools list.

    None means every tool, matching the config's "no tools key" semantics.
    An unmappable name raises rather than being dropped: a silently filtered
    tool is invisible at runtime, which is precisely the failure the config
    file warns about for pi extensions.
    """
    if tools is None:
        return None
    mapped: list[str] = []
    unknown: list[str] = []
    for tool in tools:
        name = TOOL_NAMES.get(tool)
        if name is None:
            unknown.append(tool)
        elif name not in mapped:
            mapped.append(name)
    if unknown:
        raise ValueError(
            f"no Claude Code equivalent for tool(s): {', '.join(unknown)}. "
            f"pi extension tools (subagent_*) have no counterpart — remove them "
            f"from this agent, or run it on coding_agent: pi.")
    return mapped


PROVIDERS = {"anthropic"}

# Claude Code resolves model ids server-side, so there is no catalog to probe
# the way pi's --list-models provides one. These are the ceilings SSSF reports
# for context occupancy; an unlisted id gets a conservative floor rather than
# a guess that would overstate headroom.
CONTEXT_WINDOWS = {
    "claude-opus-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-haiku-4-5-20251001": 200_000,
}
DEFAULT_CONTEXT_WINDOW = 200_000


def resolve_model(pattern: str) -> tuple[str, str]:
    """Resolve a config model pattern to an explicit (provider, model_id) pair.

    Same contract as agent_pi.resolve_model, minus the catalog lookup: the
    shape is validated, the provider is checked, and the bare id goes to
    --model.
    """
    if "/" not in pattern:
        raise ValueError(f"model {pattern!r} must be written provider/model-id, "
                         f"e.g. anthropic/claude-opus-5")
    provider, model_id = pattern.split("/", 1)
    if provider not in PROVIDERS:
        raise ValueError(f"provider {provider!r} is not served by coding_agent "
                         f"claude_code — expected one of {', '.join(sorted(PROVIDERS))}")
    return provider, model_id


def context_window(provider: str, model_id: str) -> int:
    """The model's context ceiling. 0 is never returned; unknown ids get a floor."""
    return CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)
