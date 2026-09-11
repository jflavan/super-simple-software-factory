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

import json
import os
import uuid
from pathlib import Path

from .data_types import AgentRequest
from .utils import resolve_argv

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
    if not model_id.strip():
        raise ValueError(f"model {pattern!r} has no model-id after the slash — "
                         f"write it as provider/model-id, e.g. anthropic/claude-opus-5")
    if provider not in PROVIDERS:
        raise ValueError(f"provider {provider!r} is not served by coding_agent "
                         f"claude_code — expected one of {', '.join(sorted(PROVIDERS))}")
    return provider, model_id.strip()


def context_window(provider: str, model_id: str) -> int:
    """The model's context ceiling. 0 is never returned; unknown ids get a floor."""
    return CONTEXT_WINDOWS.get(model_id, DEFAULT_CONTEXT_WINDOW)


SESSION_MAP_NAME = "cc_sessions.json"


def _read_session_map(path: Path) -> dict:
    """The session map, or {} if it does not exist yet.

    A corrupt map is reported with its path: it surfaces mid-run, inside an
    agent call, where a bare JSONDecodeError says nothing about which file to
    look at or what to do about it.
    """
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"the Claude Code session map at {path} is not valid JSON ({error}) — "
            f"delete it to let this agent start a fresh session") from error


def session_uuid(session_dir: str, sssf_session_id: str) -> tuple[str, bool]:
    """Map an SSSF session id to a Claude Code UUID. Returns (uuid, resume).

    The mapping is persisted beside the agent's other session state, because it
    has to survive across sends within a phase AND across the ADW processes
    that join an existing --adw-id. A known id resumes; an unknown one mints.

    This is what preserves the correction guarantee: a JSON-parse retry or a
    gate correction re-enters the SAME context window, exactly as it does
    under pi.
    """
    path = Path(session_dir) / SESSION_MAP_NAME
    mapping = _read_session_map(path)
    if sssf_session_id in mapping:
        existing = mapping[sssf_session_id]
        if not isinstance(existing, str) or not existing.strip():
            raise RuntimeError(
                f"the session map at {path} holds {existing!r} for "
                f"{sssf_session_id!r}, which is not a session id. Minting a new "
                f"one would silently start a fresh context window and lose the "
                f"correction this lookup exists to preserve — delete the file to reset.")
        return existing, True
    minted = str(uuid.uuid4())
    mapping[sssf_session_id] = minted
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(mapping, indent=2))
    temp.replace(path)          # atomic on POSIX and Windows
    return minted, False


CLAUDE_PATH = os.environ.get("CLAUDE_CODE_PATH", "claude")


def build_command(request: AgentRequest, session_uuid_value: str,
                  resume: bool) -> list[str]:
    """The full argv for one non-interactive Claude Code turn.

    Pure and separately testable: everything that decides WHAT runs lives here,
    so `run` is left with only the streaming.
    """
    _, model_id = resolve_model(request.model)
    cmd = [
        CLAUDE_PATH, "-p",
        "--output-format", "stream-json", "--verbose",
        "--model", model_id,
        "--append-system-prompt", request.system_prompt,
        "--permission-mode", "acceptEdits",
    ]
    cmd += ["--resume", session_uuid_value] if resume else ["--session-id", session_uuid_value]
    tools = allowed_tools(request.tools)
    # `is not None`, not a truthiness test: None means "every tool" and an empty
    # list means "no tools", and `if tools:` collapses those two opposites into
    # the same branch — handing a deliberately tool-less agent the full set.
    if tools is not None:
        cmd += ["--allowedTools", ",".join(tools)]
    cmd.append(request.prompt)
    return resolve_argv(cmd)
