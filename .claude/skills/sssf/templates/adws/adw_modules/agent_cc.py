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
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from .data_types import AgentRequest, AgentResult
from .utils import now_iso, operator_env, resolve_argv

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
    variable is therefore removed first, then set only when the level asks for
    a budget — and the level is validated before anything is touched, so a bad
    level leaves the environment exactly as it found it.
    """
    budget = THINKING_TOKENS.get(level)
    if budget is None:
        raise ValueError(f"unknown thinking level {level!r} — expected one of "
                         f"{', '.join(THINKING_TOKENS)}")
    env.pop("MAX_THINKING_TOKENS", None)
    if budget:
        env["MAX_THINKING_TOKENS"] = str(budget)
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


RESULT_SNIPPET_CHARS = 20_000
ARG_VALUE_CHARS = 20_000
LABEL_CHARS = 80

# The arg that identifies a call at a glance, in the order Claude Code's tools
# tend to use — its file tools take `file_path`, where pi's take `path`, so this
# is deliberately ordered differently from agent_pi.PRIMARY_ARGS rather than
# copied from it. What the two trackers must agree on is the record's SHAPE, not
# which arg a label prefers; the orders only diverge for a tool carrying both
# keys, which neither backend has.
PRIMARY_ARGS = ("command", "file_path", "path", "pattern", "query", "url")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _label(tool: str, args: dict) -> str:
    """One-line human name for a tool call: `Bash: dotnet build`."""
    value = next((args[key] for key in PRIMARY_ARGS
                  if isinstance(args.get(key), str) and args[key].strip()), "")
    if not value:
        value = next((v for v in args.values() if isinstance(v, str) and v.strip()), "")
    value = " ".join(str(value).split())
    return f"{tool}: {_clip(value, LABEL_CHARS)}" if value else tool


def _result_text(block: dict) -> str:
    """Claude Code's tool_result content is a string or a list of text blocks."""
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content
                       if isinstance(part, dict) and part.get("type") == "text")
    return ""


class CcToolCallTracker:
    """Folds Claude Code's tool stream into ONE normalized record per call.

    Claude Code announces a call as a `tool_use` block inside an assistant
    message and returns it as a `tool_result` block inside a later user
    message. Only the result knows the outcome, so that is where a record is
    emitted — and a single user message may close several calls at once, which
    is why observe() returns a list.

    The record shape is identical to agent_pi.ToolCallTracker's, so the tracer,
    the console and the UI never learn which backend produced a call.
    """

    def __init__(self) -> None:
        self._open: dict[str, dict] = {}

    def observe(self, event: dict) -> list[dict]:
        etype = event.get("type", "")
        message = event.get("message")
        if not isinstance(message, dict):
            return []
        content = message.get("content") or []
        if not isinstance(content, list):
            return []
        if etype == "assistant":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self._announce(block.get("id"), block.get("name"), block.get("input"))
            return []
        if etype != "user":
            return []
        return [self._close(block) for block in content
                if isinstance(block, dict) and block.get("type") == "tool_result"]

    def _announce(self, call_id, tool, args) -> None:
        """First sighting starts the clock; a later sighting only fills gaps.

        Mirrors agent_pi's tracker deliberately. Claude Code's current stream
        sends one fully-formed assistant message per turn, so a second sighting
        of the same id is not expected — but overwriting would silently reset
        the clock and understate duration_ms, and the two trackers are parallel
        implementations that should not diverge on a detail like this.
        """
        if not call_id:
            return
        if not isinstance(args, dict):
            args = {}
        known = self._open.get(str(call_id), {})
        self._open[str(call_id)] = {
            "tool": tool or known.get("tool", ""),
            "args": args or known.get("args", {}),
            "started_at": known.get("started_at") or now_iso(),   # wall clock, for the row
            "clock": known.get("clock") or time.monotonic(),      # monotonic, for duration
        }

    def _close(self, block: dict) -> dict:
        call_id = str(block.get("tool_use_id") or "")
        opened = self._open.pop(call_id, {})
        tool = str(opened.get("tool") or "tool")
        args = opened.get("args") or {}
        record = {
            "tool": tool,
            "tool_call_id": call_id,
            "args": {key: _clip(value, ARG_VALUE_CHARS) if isinstance(value, str) else value
                     for key, value in args.items()},
            "ok": not block.get("is_error", False),
            "label": _label(tool, args),
            "ended_at": now_iso(),
        }
        text = _result_text(block)
        if text:
            record["result_snippet"] = _clip(text, RESULT_SNIPPET_CHARS)
        if opened.get("started_at"):
            record["started_at"] = opened["started_at"]
        if opened.get("clock"):
            record["duration_ms"] = int((time.monotonic() - opened["clock"]) * 1000)
        return record


def _popen(cmd: list[str], env: dict[str, str], cwd: str):
    """Launch the agent. A seam: tests replace this to exercise the stream logic.

    stdin is DEVNULL, deliberately — the same hazard agent_pi documents. The
    prompt travels in argv, so the child never needs stdin, but inheriting the
    parent's means a non-TTY the child may block on forever. That failure is
    silent and total: no events, no bytes, an empty raw_output.jsonl.
    """
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, bufsize=1, cwd=cwd, env=env)


def validate_agent(agent) -> list[str]:
    """Config problems this backend can detect before anything spawns."""
    problems = []
    if agent.harness_engineering:
        problems.append(
            f"agent {agent.name!r}: harness_engineering is a pi extension mechanism "
            f"with no Claude Code equivalent ({', '.join(agent.harness_engineering)}) "
            f"— remove it, or run this agent on coding_agent: pi")
    # An agent allowed nothing cannot act. config.md already says an empty list
    # "is not 'all tools' — it is a tool-less agent, and it will stall", so say
    # so at validation rather than spawning something that cannot work. Omitting
    # the key entirely is how you ask for every tool.
    if agent.tools is not None and not agent.tools:
        problems.append(
            f"agent {agent.name!r}: `tools: []` allows nothing, so this agent "
            f"cannot act — name the tools it needs, or omit `tools` for all of them")
    try:
        allowed_tools(agent.tools)
    except ValueError as error:
        problems.append(f"agent {agent.name!r}: {error}")
    return problems


def run(request: AgentRequest, on_event: Optional[Callable[[dict], None]] = None,
        on_spawn: Optional[Callable[[int], None]] = None,
        on_exit: Optional[Callable[[int], None]] = None) -> AgentResult:
    """Run one non-interactive Claude Code turn.

    Same contract as agent_pi.run: tail the JSONL stream, forward every event
    as it arrives, and return the turn's text, usage and cost.
    """
    provider, model_id = resolve_model(request.model)
    session_value, resume = session_uuid(request.session_dir, request.session_id)
    cmd = build_command(request, session_value, resume)

    # apply_thinking, not env.update(thinking_env(...)): the child env starts as
    # a copy of the operator's, so an inherited MAX_THINKING_TOKENS has to be
    # removed for `off` to mean off.
    env = apply_thinking(operator_env(), request.thinking)

    raw_path = Path(request.raw_output_path)
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    result = AgentResult(session_id=request.session_id,
                         context_window=context_window(provider, model_id))
    process = _popen(cmd, env, request.cwd)
    if on_spawn:
        on_spawn(process.pid)

    terminal_subtype = ""
    try:
        with raw_path.open("a") as raw:
            for line in process.stdout:
                raw.write(line)
                raw.flush()                      # events land on disk as they happen
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "result":
                    terminal_subtype = str(event.get("subtype") or "")
                _absorb(result, event)
                if on_event:
                    on_event(event)
    except BaseException:
        # We are no longer draining the child's pipe, so leaving it alive would
        # block it forever on its next write. Reap it deliberately rather than
        # relying on the collector to close the handle for us, and tell the
        # tracer the pid is gone — it recorded the spawn and would otherwise
        # believe this process is still running.
        process.kill()
        process.wait()
        if on_exit:
            on_exit(process.pid)
        raise

    stderr = process.stderr.read() if process.stderr else ""
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)
    if result.returncode != 0 and not result.text:
        raise RuntimeError(f"claude exited {result.returncode}: {stderr.strip()[-800:]}")
    if terminal_subtype and terminal_subtype != "success":
        raise RuntimeError(
            f"claude ended the turn with subtype {terminal_subtype!r} instead of "
            f"'success' and produced no report — this is not a JSON formatting "
            f"problem, so re-prompting will not fix it")
    return result


def _absorb(result: AgentResult, event: dict) -> None:
    """Fold one stream event into the running result.

    Usage accrues per assistant turn; the terminal `result` event carries the
    authoritative cost and the final text. Occupancy is read off the last
    assistant turn, matching agent_pi's rule.

    UsageBreakdown.add_turn is NOT used here: it parses pi's usage shape
    (`input`, `output`, a nested `cost` dict). Claude Code sends `input_tokens`
    / `output_tokens` and reports cost only once, on the result event, so
    add_turn would fold in silent zeros — and agents.execute reports the
    phase's tokens from this breakdown, not from `tokens`.
    """
    etype = event.get("type")
    if etype == "assistant":
        usage = (event.get("message") or {}).get("usage") or {}
        inputs = int(usage.get("input_tokens") or 0)
        outputs = int(usage.get("output_tokens") or 0)
        turn = inputs + outputs
        if turn:
            result.tokens += turn
            result.context_tokens = turn
            result.usage.input_tokens += inputs
            result.usage.output_tokens += outputs
            result.usage.cache_read_tokens += int(usage.get("cache_read_input_tokens") or 0)
            result.usage.cache_write_tokens += int(
                usage.get("cache_creation_input_tokens") or 0)
            result.usage.total_tokens += turn
    elif etype == "result":
        text = event.get("result")
        if isinstance(text, str) and text:
            result.text = text
        # `+=`, not `=`: reads as accrual, though the stream carries exactly one
        # terminal `result` event per turn, so this only ever adds once.
        cost = float(event.get("total_cost_usd") or 0.0)
        result.cost += cost
        # Claude Code prices the turn as one number, so the per-component cost
        # fields stay zero and only the total is claimed. Reporting a made-up
        # split would be worse than reporting none.
        result.usage.total_cost += cost


ToolCallTracker = CcToolCallTracker
