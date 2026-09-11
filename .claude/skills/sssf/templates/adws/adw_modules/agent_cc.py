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
