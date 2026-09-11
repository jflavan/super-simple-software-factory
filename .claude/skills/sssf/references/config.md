# Config Reference

The full `sssf.config.yaml` spec: every field, how defaults merge, and how model / thinking / tools / extensions map onto the coding agent.

It lives at **`adws/adw_sssf_config/sssf.config.yaml`** — the default path every `adw_*.py` and the justfile resolve, and where `install.py` / `make_config.py` stamp it. Pass `--config <path>` to any ADW (or set `SSSF_CONFIG` for the justfile) to run against a different roster.

## Shape

```yaml
defaults:
  coding_agent: pi
  model: google/gemini-3.6-flash        # ALWAYS provider/model-id
  thinking: medium
  harness_engineering: []
  tools: [read, bash, edit, write, grep, find, ls]
  protected_files:                      # no agent may edit the machinery that grades it
    - adws/adw_modules/
    - adws/adw_sssf_config/
    - adws/adw_*.py
  data_dir: adws/adw_data

observability:
  db: adws/adw_data/sssf.db
  poll_ms: 500

doc_policy:                             # optional; empty means the gate never fires
  - when: "apps/api/**/Auth*.cs"
    require: ["docs/AUTH.md"]

agents:
  - name: planner
    coding_agent: pi
    model: google/gemini-3.6-flash        # ALWAYS provider/model-id
    thinking: high
    color: "#a78bfa"
    purpose: Turn a request into a plan the builder can implement without asking questions.
    prompt_engineering:
      system: adws/adw_data/prompt_engineering/planner/system.md
      user: adws/adw_data/prompt_engineering/planner/user.md
    harness_engineering:
      - adws/adw_data/harness_engineering/subagents.ts   # a PATH, not a name
    tools:
      - read
      - bash
    writes:                               # the boundary; omit for unrestricted
      - specs/
```

## Fields

### `defaults`

| Field | Type | Meaning |
|---|---|---|
| `coding_agent` | `pi` \| `claude_code` | Which interface runs the agent. Both are real backends behind the same interface in `agents.py` — `pi` (default) runs the Pi agent, `claude_code` runs Claude Code. |
| `model` | string | Model id. For `pi`, any id registered in `~/.pi/agent/models.json`, e.g. `google/gemini-3.6-flash`. For `claude_code`, always `anthropic/<model-id>`, e.g. `anthropic/claude-opus-5` — there is no catalog to probe the way pi's `--list-models` provides one, so only the shape (`provider/model-id`) and the provider (`anthropic`) are validated, not that the id itself exists. Default `google/gemini-3.6-flash` — written in full, like every model id. |
| `thinking` | enum | Reasoning effort — see below. Default `medium`. |
| `color` | hex string | Lane color for every agent that does not set its own. Default empty — the visualizer falls back to its own palette. |
| `harness_engineering` | list[string] | Pi extension file paths. Pi-only: a `claude_code` agent that sets this fails `agents.validate()`, before anything spawns. |
| `tools` | list[string] | Roster-wide tool allowlist. Every agent that omits its own `tools` inherits this. Unset = all tools usable. |
| `protected_files` | list[string] | Paths **no** agent may modify unless it names them in its own `writes`. Default: `adws/adw_modules/`, `adws/adw_sssf_config/`, `adws/adw_*.py` — an agent must not be able to edit the machinery that decides whether its work passed. |
| `data_dir` | path | Runtime home. Sessions land at `{data_dir}/sessions/{adw_id}/{agent_name}/`. Default `adws/adw_data`. |

### `observability`

| Field | Type | Meaning |
|---|---|---|
| `db` | path | SQLite trace db. `tracer.py` writes it directly; the visualizer polls it. Default `adws/adw_data/sssf.db`. |
| `poll_ms` | int | Visualizer live-poll cadence in ms. History uses the same queries, lazy-paged. Default `500`. |

### `agents[]`

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | The identifier ADW scripts use. **ADWs name agents, never models.** |
| `purpose` | yes | One sentence: what this agent is for. Should match its `system.md` Purpose. |
| `prompt_engineering.system` | yes | Path to the system prompt — who the agent is, its single purpose, its output contract. |
| `prompt_engineering.user` | yes | Path to the default user prompt — the task template with `{{prompt}}`, `{{previous_envelope}}`, `{{context_handoff_dir}}`. |
| `color` | no | Hex swatch (`"#a78bfa"`) for this agent's lane in the visualizer. Travels config → `agent_sessions.color` → `/api/sessions/:adw_id`, and rides the `agent_start` event so a lane is colored while the agent is still running. Unset = the UI's fallback palette. |
| `coding_agent`, `model`, `thinking`, `color`, `harness_engineering` | no | Override the corresponding `defaults` key. |
| `tools` | no | Allowlist. **Omitting the key means all tools usable.** A capability list, not a boundary — see `writes`. |
| `writes` | no | What this agent may modify **in the repo**, enforced after every call. Omitted = unrestricted (still barred from `protected_files`). `[]` = no repo writes at all. A list = only those paths: a trailing `/` is a directory prefix, `*` matches within one path segment, `**` crosses segments, anything else is an exact path. Naming a `protected_files` path here is what unlocks it. **The session runtime under `data_dir` is always writable** — `writes: []` means read-only with respect to the repo, not unable to write its own report. |

Output types are deliberately absent: config defines who an agent *is*; the ADW call site defines how it's *used*. One agent serves many calls — same system prompt, different user prompt + output type per call.

## Defaults merging

`agents.py` merges each entry **over** `defaults`, key by key. An entry states only what differs; anything unset inherits. `agents.validate(cfg, REQUIRED_AGENTS)` then confirms every name an ADW declares exists, resolves to a usable coding agent + model, and has both prompt files present on disk. Any miss fails the run immediately — **no agent is ever spawned against a half-valid config.**

## Thinking levels

Pi's reasoning-effort ladder, lowest to highest:

```
off | minimal | low | medium | high | xhigh | max
```

On `pi`, this maps to Pi's reasoning effort control and is honored when the model is registered with `reasoning: true` in `~/.pi/agent/models.json`; on a non-reasoning model the setting is inert — no error, no effect. Rough guidance: `high`/`xhigh` for planners and reviewers, `medium` for builders, `low` for mechanical read-and-report agents.

On `claude_code` there is no `--thinking` flag at all. `agent_cc.py` maps the same ladder to a `MAX_THINKING_TOKENS` budget set in the child process's environment (`off` clears it, `medium` is 10,000, up to 64,000 at `max`) — same six-word config, a different mechanism entirely underneath.

## Model resolution

**Always write `model` as `provider/model-id`.** What "resolution" means depends on the
backend. This section is pi's: catalog lookup, ambiguity, per-provider keys. Claude Code's
is the short version above — shape and provider only, no catalog, because Claude Code
resolves model ids server-side and SSSF has nothing local to check them against.

`agents.py` hands the string to the Pi interface, which resolves it against pi's merged catalog — `~/.pi/agent/models.json` plus pi's built-in providers. The same model is usually carried by more than one provider (`gemini-3.6-flash` lives under `google` *and* under `openrouter` as `google/gemini-3.6-flash`), and a bare id that matches several **raises at resolution**:

```
agent 'scout': model pattern 'gemini-3.6-flash' is ambiguous:
  [('google', 'gemini-3.6-flash'), ('openrouter', 'google/gemini-3.6-flash'), ...]
```

That is `agents.validate()` doing its job — it fails before anything spawns rather than silently billing the wrong provider — but it means every agent in the roster inheriting that default is grounded until the pattern is qualified. Qualifying is the whole fix: `google/gemini-3.6-flash`, `openai/gpt-5.6-terra`, `fireworks/accounts/fireworks/models/kimi-k3`. The leading segment is matched against the provider list first, so the rest of the string can contain slashes.

Other consequences worth knowing:

- A model must be in the catalog before any agent can name it. An unknown id fails at resolution, before spawn. `pi --list-models` is the catalog the resolver actually reads.
- **Ambiguity can appear without you touching the config.** Registering a new provider that carries a model you already use turns a formerly-fine bare pattern ambiguous. If a roster stops validating and nobody edited it, that is why.
- Provider credentials come from the environment, not the config — the key that matches the provider you named (`GEMINI_API_KEY` for `google/...`, `OPENROUTER_API_KEY` for `openrouter/...`).
- The resolved model is recorded per session in `agent_map.json` and mirrored into the `agent_sessions` table. **Changing an agent's model invalidates its session**: a joined run starts that agent fresh instead of resuming a context window built by a different model.

## Tools

`tools` maps to `pi --tools`. Pi's seven builtin tool names:

| Tool | Purpose | Pi's own default |
|---|---|---|
| `read` | read file contents | on |
| `bash` | execute bash commands | on |
| `edit` | find/replace edits | on |
| `write` | create/overwrite files | on |
| `grep` | search file contents | **off** |
| `find` | find files by glob | **off** |
| `ls` | list directory contents | **off** |

`grep`, `find`, and `ls` are off in bare Pi, so an agent that does not name them will shell out through `bash` to do the same work. The starter roster therefore sets `defaults.tools` to all seven and lets each agent narrow from there.

**Resolution order:** an agent's own `tools` list wins; an agent that omits the key inherits `defaults.tools`; if neither is set, `tools` stays `None` and all tools are usable. An empty list is not "all tools" — it is a tool-less agent, and it will stall. On `claude_code`, `tools: []` is refused outright at validation, for exactly the same reason: an agent granted nothing cannot act.

**Tool names are per backend, and one mapping widens capability.** The names above are
pi's. On `coding_agent: claude_code` they are translated (`read` → `Read`, `find` →
`Glob`, and so on). One translation is not one-for-one: **`ls` maps to `Bash`**, because
Claude Code has no dedicated listing tool. An agent granted only `ls` therefore gets
arbitrary shell execution on that backend. If that is not what you want, drop `ls` — and
remember that `tools:` was never a sandbox anyway: `writes:` and `protected_files` are
what actually bound an agent, enforced in `adw_modules/permissions.py` after every call.

`harness_engineering` tools (`subagent_*`) have no Claude Code counterpart at all —
naming one for a `claude_code` agent raises rather than being silently dropped.

## Write permissions — `writes` and `protected_files`

`tools` cannot express a safety boundary, because two of the tools are general
purpose. `bash` runs anything, including `git checkout`, which discards an
engineer's uncommitted work; `write` reaches any path, not only the one report
file an agent was granted it for. So "this agent changes nothing" is a claim a
tool list can state but never keep.

`adw_modules/permissions.py` keeps it, the same way every other claim in this
system is kept — after the fact, against the repo. Before an agent's first
prompt the working tree's change-set is fingerprinted; after its last send
(including JSON retries and gate corrections) it is fingerprinted again. Any
path that appeared, vanished, or changed is attributed to that agent.

Comparing change-sets rather than watching writes is deliberate: a path that was
modified before the agent ran and is clean afterwards has been **reverted**, and
a reversion is a modification. That is what catches `git checkout`.

A breach is not a gate violation. Gates are for work an agent can be asked to
redo; a write has already happened, so re-prompting fixes nothing. Instead:

1. every unauthorized change the agent **introduced** is rolled back — tracked
   files with `git checkout --`, untracked files by deletion;
2. a path that was **already dirty** before the agent ran is left untouched. The
   operator had uncommitted work there, and discarding it to tidy up would be
   the same harm this module exists to prevent;
3. the phase fails and names every path with what happened to it.

```yaml
defaults:
  protected_files: [adws/adw_modules/, adws/adw_sssf_config/, "adws/adw_*.py"]

agents:
  - name: builder      # no `writes` key -> unrestricted, minus protected_files
  - name: scout
    writes: []         # no repo writes; its findings still land in context_handoff/
  - name: planner
    writes: [specs/]
  - name: documenter
    writes: [app_docs/, docs/, "**/*.md", "*.md"]
```

**The session runtime under `data_dir` is always writable, for every agent.**
`context_handoff/` is how agents hand work to each other, and each agent's
prompts, `raw_output.jsonl`, and `envelope.json` sit beside it. That grant comes
from `data_dir` rather than from `.gitignore`: the runtime is normally ignored,
so it never even appears in a snapshot, but an agent's ability to record its own
work must not depend on a gitignore line someone can delete.

Narrow by role, not by reflex. Anything that must produce a `context_handoff/` artifact needs `write`, or it will resort to a `bash` heredoc. Withhold `edit`/`write` only where the restriction *is* the guarantee — a reviewer that cannot edit cannot quietly fix what it was asked to report.

### Extension tools must be named explicitly

`pi --tools` is an allowlist over **built-in, extension, and custom tools alike** — not just builtins. So the moment an agent has a `tools` list at all (its own, or one inherited from `defaults`), any tool registered by its `harness_engineering` extensions is **excluded unless it appears in that list by name**.

This fails quietly. The extension still loads, the run still succeeds, and the tool the extension exists to provide is simply never offered to the model — you find out by noticing the agent never called it.

```yaml
  - name: reviewer
    harness_engineering:
      - .pi/extensions/ast_query.ts     # registers tool: ast_query
    tools:
      - read
      - grep
      - find
      - ls
      - bash
      - ast_query                       # REQUIRED — the extension's tool, named or lost
```

Rule: **every entry in `harness_engineering` that registers a tool must have that tool name added to the agent's `tools` list.** Adding an extension is therefore a two-line change, never one. The alternative is dropping the `tools` key *and* leaving `defaults.tools` unset so the agent resolves to `None` (all tools) — but with a roster-wide `defaults.tools` in place, that escape hatch is closed; naming the tool is the only path.

## `doc_policy` — the documentation contract

`doc_policy` is a top-level key in `sssf.config.yaml` (a sibling of `defaults`,
`observability`, and `agents`), optional and **empty by default** — the
`doc_policy` gate never fires until you write a rule.

```yaml
doc_policy:
  - when: "apps/api/**/Auth*.cs"
    require: ["docs/AUTH.md"]
  - when: "apps/web/src/**"
    require: ["docs/ARCHITECTURE.md", "docs/FEATURES.md"]
```

A rule fires when a changed file matches `when`; it then requires each
`require` entry to also appear among the changed files. Both sides are path
globs with the same semantics as `writes:` — `*` stops at a directory
separator, `**` crosses them (and `**/` also matches zero directories, so
`**/*.md` covers `README.md` at the repo root), a trailing `/` is a directory
prefix.

The gate is silent when no rule triggers — it reports a check only per rule
that actually fired, so one real violation is never buried under a hundred
green lines. It judges the envelope's **claimed** `changed_files`, like every
gate does; `permissions.enforce` is what checks the real diff, and it runs
after the gates and only bounds what an agent may write, not what it admitted
to. A violation returns to the same agent session, context intact, so the
correction is "also update this document," not a fresh run.

## Quality blocks — `quality_blocks.py`

`adw_modules/quality.py` is the engine; the commands it runs live in
`adws/adw_modules/quality_blocks.py`, a generated list of `QualityCheckSpec`.
`install.py --profile <name>` writes that file from what it finds in the repo.
Without a matching profile, `quality.py` falls back to `PLACEHOLDER_BLOCKS` —
every block is an `echo` that exits 0 and names itself as fake, on purpose: a
wrong-but-plausible command that silently passes is worse than one that admits
it.

```python
QualityCheckSpec(
    name="check-web", area="frontend", operation="typecheck",
    argv=["npm", "run", "check"],
    cwd="apps/web", tier="fast", timeout_seconds=600,
)
```

- `tier` is `"fast"` or `"full"`. `quality.run_tests()` (the bounded fix loop)
  runs only `fast`; `quality.run_quality()` (final verification, run once) runs
  both. A Testcontainers suite needs Docker up, so paying for it on every retry
  is a real cost, not a theoretical one — put it in `full`.
- Selecting a tier with **no blocks in it raises**, rather than reporting a
  green result from zero executed commands. That is reachable two ways — an
  empty `BLOCKS`, or a block list where every entry is `full` so the fast tier
  selects nothing — and neither is something a builder can repair, so neither
  is allowed to look like a pass.
- `cwd` is repo-relative. A monorepo runs the same command in several
  packages; this is how, without a per-package-manager flag table.
- `argv` is a list, never a shell string, and binaries are called by bare name
  so they resolve through the operator's own PATH.

## Harness engineering

`harness_engineering` entries are pi extension **file paths**, passed through as `pi -e <path>`, one flag per entry, scoped to that agent only. This is where per-agent harness changes live — e.g. an output-tightening extension for an agent that keeps wrapping its envelope in prose. The starter roster ships one, `adws/adw_data/harness_engineering/subagents.ts`, wired to `planner` and `scout`; every other agent leaves the key off. Note the shape: a repo-relative **path**, never a bare extension name.

**This is a pi-only mechanism.** It has no Claude Code equivalent, and that is enforced,
not just undocumented: a `claude_code` agent that sets `harness_engineering` fails
`agents.validate()` before anything spawns. Run that agent on `coding_agent: pi` instead,
or drop the key.

**If the extension registers a tool, name that tool in the agent's `tools` list too** — `--tools` filters extension tools exactly like builtins, so an unnamed extension tool is silently unavailable no matter that the extension loaded fine. See [Extension tools must be named explicitly](#extension-tools-must-be-named-explicitly) above. Extensions that only shape output or add flags (no tool registration) need no `tools` change.
