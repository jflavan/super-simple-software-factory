# Update Config

Add or retune agents in `sssf.config.yaml`.

## Retune model or thinking

Edit the agent's entry in place:

```yaml
  - name: builder
    model: google/gemini-3.6-flash   # ALWAYS provider/model-id
    thinking: high                   # was medium
```

Write the model as `provider/model-id`, never a bare id. The same model is usually carried by several providers, and an ambiguous pattern raises in `agents.validate()` — grounding every agent that inherits it. See `references/config.md`.

Thinking levels are the same six-word ladder on both backends — `off | minimal | low | medium | high | xhigh | max` — but the mechanism differs. On `pi`, this is Pi's reasoning effort; it only bites when the model is registered with `reasoning: true` in `~/.pi/agent/models.json`. On `claude_code`, there is no reasoning-effort flag at all — `agent_cc.py` maps the same ladder to a `MAX_THINKING_TOKENS` budget in the child process's environment instead.

**A model change means a fresh session.** `agent_map.json` records the model each coding-agent session was created with. When a joined run (`--adw-id`) finds the config's model no longer matches the recorded one, that agent starts a **new** session rather than resuming — the map is updated, never a bad resume. Thinking changes do not invalidate a session; model changes do. Expect the agent to lose its accumulated context window on the first run after the change.

## Recolor an agent's lane

```yaml
  - name: builder
    color: "#22d3ee"      # hex; the starter roster ships violet, cyan, amber, rose, fuchsia
```

Purely cosmetic and safe to change mid-project: the color rides the `agent_start` event and the `agent_sessions` row, so the visualizer picks it up on the next run without touching past sessions. Omit the key to let the UI's fallback palette choose.

## Retune tools

Pi's seven builtins: `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`. The last three are **off in bare Pi**, so an agent that doesn't name them will shell out through `bash` to search and list.

These names are pi's; on `coding_agent: claude_code` they are translated (`read` → `Read`, `grep` → `Grep`, and so on) — except **`find` → `Glob` and `ls` → `Bash`**, because Claude Code has no dedicated listing tool, so an agent granted only `ls` gets arbitrary shell execution on that backend. `tools: []` is refused outright at validation for a `claude_code` agent, for the same reason it stalls a Pi one: an agent granted nothing cannot act. See `references/config.md` for the full mapping.

Set the roster-wide floor in `defaults`, then narrow per agent:

```yaml
defaults:
  tools: [read, bash, edit, write, grep, find, ls]

agents:
  - name: reviewer
    tools:                # explicit list wins over defaults
      - read
      - grep
      - find
      - ls
      - bash
      - write
```

**Resolution:** the agent's own list wins → else it inherits `defaults.tools` → else `None`, meaning all tools. An empty list is not "all tools"; it is a tool-less agent, and it will stall.

Narrow by role, not by reflex:

- Any agent that must produce a `context_handoff/` artifact needs **`write`** — without it, it falls back to a `bash` heredoc to create the file the gate checks for.
- Withhold `edit`/`write` only where the restriction *is* the guarantee. The reviewer's contract is "change nothing", so withholding `edit` makes that structural instead of merely prompted.
- Recon agents should get the full read surface (`read`, `grep`, `find`, `ls`) — cheaper and more legible in the trace than the equivalent `bash` calls.

**Extension tools count against the allowlist.** `--tools` filters built-in, extension, and custom tools alike. Once an agent has a `tools` list — its own, or inherited from `defaults` — a tool registered by one of its `harness_engineering` extensions is dropped unless it is named there. Nothing errors: the extension loads, the run passes, the tool is just never offered. Any agent with a tool-registering extension must list that tool by name.

## Add harness extensions

```yaml
    harness_engineering:
      - .pi/extensions/json_guard.ts    # a pi extension FILE PATH
```

Entries are pi extension **file paths**, passed through as `pi -e <path>`, applied to that agent only. Reach for an output-tightening extension when an agent keeps wrapping its envelope in prose and burning correction retries. The starter roster ships exactly one — `adws/adw_data/harness_engineering/subagents.ts`, on `planner` and `scout`, which is also the live example of the two-part edit below — and every other agent leaves the key off.

**This is a pi-only mechanism, enforced, not just undocumented.** A `claude_code` agent that sets `harness_engineering` fails `agents.validate()` before anything spawns — there is no Claude Code equivalent. Run that agent on `coding_agent: pi`, or drop the key.

**Adding a tool-registering extension is a two-part edit.** The extension path goes in `harness_engineering`, *and* the tool name it registers goes in that agent's `tools` list:

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
      - ast_query                       # REQUIRED — or the extension loads and its tool is filtered out
```

Skip the second half and it fails silently: extension loaded, run green, tool never available to the model. Extensions that only shape output or register flags — no new tool — need no `tools` change.

## Add a new agent

Four steps. The first three are required — skipping any one fails `agents.validate()` at ADW startup, before anything spawns. The fourth fails nothing, which is exactly why it gets forgotten:

1. **Prompts.** Create `adws/adw_data/prompt_engineering/{name}/system.md` (Purpose + Instructions — the agent's static identity, nothing else) and `user.md` (an h3 per incoming datum: `{{prompt}}`, `{{previous_envelope}}`, `{{context_handoff_dir}}`, then the task, then a `## Report` section showing the exact output JSON). Copy an existing pair as the shape. An agent that acts on repo code should also name `{{profile_overlay}}` — that is where the stack profile tells it what this repo is built out of, and a template that does not name it silently does not get it.
2. **Config entry.** Name, purpose, prompt refs, plus anything that differs from `defaults`.
3. **An output type.** Every agent call parses against a concrete Pydantic model in `adw_modules/data_types.py`. If none of `PlanOutput`, `BuildOutput`, `ScoutOutput`, `ReviewOutput`, `DocumentOutput` fits the new agent's report, add one — see `update_modules.md`. The user prompt's `Report` section must show exactly that JSON shape.
4. **`writes:`, stated deliberately.** An agent that omits the key is **unrestricted** — `bash` runs anything and `write` reaches any path, so the boundary is not something `tools` can express. `writes` is a glob allowlist checked in code after every call; anything outside it is rolled back and the phase fails. Write `writes: []` for an agent that must change nothing in the repo (it can still write its own report, which is runtime, not the repo), or list the prefixes it owns. Nothing warns you if you leave it off.

Then name the agent in an ADW's `REQUIRED_AGENTS` and call it.

## Add a documentation contract

`doc_policy` is a top-level key in this same file, and the one gate an operator configures rather than codes. Each rule says that a change matching `when` obliges a change matching one of `require`:

```yaml
doc_policy:
  - when: "apps/api/**/Auth*.cs"
    require: ["docs/AUTH.md"]
  - when: "apps/web/src/**"
    require: ["docs/ARCHITECTURE.md", "docs/web/**/*.md"]
```

`gates.doc_policy` reads it after every repo-changing agent call. A rule fires when a changed file matches `when`, and it then requires **each** `require` entry to appear among the changed files too — `require` is a conjunction, not a menu, so the second rule above obliges both documents. The violation goes back into the same session as a correction and the agent updates the document with its context intact; it does not restart. Empty or absent means the gate never fires, so this costs nothing until you use it.

It judges the envelope's **claimed** `changed_files`, like every gate. An agent that quietly omits a file from its own claim is not caught here — this is a contract with a mechanical check behind it, not a proof.

Glob shapes are the same engine as `writes` and `protected_files`: `*` stops at a directory separator, `**` crosses them and matches zero or more directories (so `**/*.md` includes root-level files), and a trailing `/` is a literal directory prefix with glob characters disabled inside it.

## Rules that do not bend

- ADW scripts name **agents**, never models. Swapping a model is a config edit and touches no Python.
- One agent, one prompt, one purpose. If an entry needs two purposes, it is two agents.
- Output types never appear in config — they live at the call site, paired with the user prompt.

Full spec: `references/config.md`.
