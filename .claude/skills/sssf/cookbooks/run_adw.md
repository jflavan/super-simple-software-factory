# Run ADW

Run a workflow and report on it. **You run and observe — you never step into the process or do the work yourself.**

## Step 0 — translate the request

**Read [how_to_prompt_for_the_eng.md](how_to_prompt_for_the_eng.md) before you launch anything.** The prompt you pass is read by every agent in the chain, so it gets written deliberately: same intent, sharper words, verified paths, and a stated "done means". That cookbook is the whole procedure; this one starts once you have the prompt.

## The orchestrator's posture

The ADW is the worker. Your job is to launch it, watch the trace, and tell the engineer what happened. Do not read the agent's target files and "help", do not fix the code an agent was supposed to fix, do not edit an envelope. If a run fails, report the failing phase and its violations — the fix is a config, prompt, or ADW change, made deliberately, and then a re-run.

## Launch

Which chain to launch is decided in `how_to_prompt_for_the_eng.md`, and the short version is: **the ADW the engineer named, or else the most complete composed chain the work justifies — never a single-agent one.** Read `ls adws/adw_*.py` and the `Phases:` line in each docstring to see what this repo has; the names below are shape, not a menu.

```bash
uv run adws/<end-to-end-chain>.py "add a /health endpoint"
uv run adws/<plan-build-verify-chain>.py requests/health.md
uv run adws/<build-first-chain>.py "implement the plan" --adw-id a1b2c3d4
uv run adws/<recon-chain>.py "where is auth handled" --config path/to/other.config.yaml
```

The prompt is inline text or a file path. Launch in the background so you can poll while it works; the `adw_id` is printed on startup — capture it, everything else keys off it.

### Listen for the roster

The chain says *what runs*; the config says *who runs it*. **If the engineer references a roster, a config, or a model tier, pass it — do not fall through to the default.**

There is no recipe for this in the stamped `justfile` — it ships deliberately small, and a `rosters` recipe is one of the extras on the `example` branch. Read the configs off disk:

```bash
ls adws/adw_sssf_config/*.yaml                        # every roster on disk
grep -nE "name:|model:" adws/adw_sssf_config/*.yaml   # who is in each, and on what
```

`-E` matters: plain `grep` is BRE, where `|` is a literal character and that
pattern matches nothing at all.

That gives you the path to pass and who is in it. Read it from disk every time.
A roster that documents the names it answers to does so in its header comment,
so `head -5 <file>` settles "which one did they mean" when there is more than
one — the shipped default carries no aliases, because there is nothing to
disambiguate it from. Rosters are the engineer's to add, rename, and retune, so a name you remember from a doc is a guess.

They will rarely say `--config`. Treat any of these as naming a roster, then resolve it to a file:

| What they say | What it means |
|---|---|
| "run it on the frontier config", "use the frontier roster" | the roster file whose name matches |
| "run this with the big models", "use the sota roster" | the non-default roster — confirm which if there is more than one. Each config's header comment lists the names it answers to, so `head -3` on the file settles it |
| "have opus plan this one" | a roster whose planner is that model; if none exists, say so rather than editing the config mid-request |
| nothing about models at all | the default, `adws/adw_sssf_config/sssf.config.yaml` |

`--config` takes the path directly; the justfile recipes read `SSSF_CONFIG` instead:

```bash
uv run adws/<chain>.py "<prompt>" --config adws/adw_sssf_config/sssf.frontier.config.yaml
SSSF_CONFIG=adws/adw_sssf_config/sssf.frontier.config.yaml just <recipe> "<prompt>"
```

Two things that bite:

- **Never swap rosters on your own.** A different roster is a different cost and a different result. If the default's model looks wrong for the work, say so and let the engineer choose.
- **Switching rosters mid-session breaks resumption.** `agent_map.json` records the model each coding-agent session was created with, so a joined run (`--adw-id`) whose config now names a different model starts that agent **fresh** instead of resuming its context window. That is deliberate — a bad resume is worse — but it means "plan on the frontier roster, then build on the default" costs the builder its accumulated context. Say so when you report it.

`--adw-id` is optional on **every** ADW. Given one, the run joins that session if it exists or creates it pinned to exactly that id: same `sessions/{adw_id}/` dirs, same `context_handoff/`, envelopes appended, and each agent resumes its existing coding-agent context window via `agent_map.json`. That is how you chain ADWs — plan under one id, then build under the same id.

## Observe

The trace db is `adws/adw_data/sssf.db`. It is WAL, so reads never block the running writers — poll it as often as you like.

```bash
# where the run stands
uv run adws/adw_trace.py phases a1b2c3d4

# the event list — same rows the visualizer's cursor poll reads, in order
uv run adws/adw_trace.py events a1b2c3d4

# why a phase failed
uv run adws/adw_trace.py gates a1b2c3d4

# session-level status
uv run adws/adw_trace.py sessions --limit 5

# what an agent actually did — filter the event list to tool calls
uv run adws/adw_trace.py events a1b2c3d4 --type tool_call
```

`adw_trace.py` has no cursor or ordering flags — `events` always prints the full list, oldest first, and `sessions --limit N` is the only paging it does. For a live cursor poll on `rowid` the way the visualizer does it, query `sssf.db` directly with the stdlib `sqlite3` module (see `references/observability.md`) rather than shelling out to a CLI that may not be installed.

`tool_call` rows carry a real span, so durations come off the columns — see `references/observability.md` for which fields each event type populates.

The ADW also narrates to stdout, and every line it prints is written to the db as a `log` event — terminal and swim lane tell the same story by construction, so tailing the background process is a valid second view rather than a competing source of truth.

Files are the raw record if you need more than the db shows: `adws/adw_data/sessions/{adw_id}/{agent}/raw_output.jsonl` (full coding-agent stream), `envelope.json` (the parsed final response), `prompts/` (exactly what was sent), and `context_handoff/` (what agents wrote for each other).

## When a run is stuck

A hung coding agent produces no events at all, so the trace goes quiet rather than red. Read it in this order:

```bash
just phases <adw_id>     # which phase is still `running`
just procs <adw_id>      # what that phase is actually running, with pids
```

There is **no `just kill`** in the stamped `justfile` — like `rosters`, it is one of the extras on the `example` branch. Read the pids out of the trace and signal them yourself, **children first**, so the workflow does not respawn what you just stopped:

```bash
uv run adws/adw_trace.py processes | grep <adw_id>   # live rows are the ones with no end time
kill <child_pid>                                     # the coding agent
kill <workflow_pid>                                  # then the ADW
```

Check each pid still matches the command the trace recorded before you signal it — pids get recycled, and the row you are reading may be minutes old.

`processes` rows with `ended_at IS NULL` are the live ones. If `procs` shows a pi child but the phase has produced no `tool_call` events and its `raw_output.jsonl` is empty, the agent never got started properly — check the model resolves and that nothing is blocking the subprocess, rather than waiting it out.

A killed run still closes its own trace. `session.ensure` installs a SIGTERM/SIGINT handler that finalizes the session to `fail` and closes its process rows on the way out, so a plain `kill <pid>` marks the run dead rather than leaving the db claiming work is in flight. A session that reads `running` with no live process means the workflow died *without* a signal — a hard kill, or the cp1252 banner crash on Windows.

## When a check fails

A `kind="code"` quality phase fails differently from an agent phase, and the phase log is deliberately short. Four things to know:

- **The real output is on disk.** Every block writes its full stdout and stderr to `context_handoff/quality/<seq>_<name>/command.log` inside that session's directory. The phase log carries the block name, the exit code, and a snippet; the log file carries the rest. Read it before reporting anything.
- **`RuntimeError: no quality blocks in tier(s) [...]`** is not a missing test suite. It means every block in `quality_blocks.py` is tagged for a different tier than the one the phase asked for — usually everything tagged `full` and a fix loop asking for `fast`. The engine refuses rather than reporting green on zero commands. It is a config problem, not a code problem, and re-running will not help.
- **`ValueError: duplicate quality block name(s)`** means two blocks share a name case-insensitively. A name is an artifact directory, so two blocks with one name would overwrite each other's log. Rename one in `quality_blocks.py`.
- **A command pointing at a directory that moved** shows up as a shell-level failure with an exit code nobody wrote. Run `uv run .claude/skills/sssf/scripts/install.py --doctor` — it re-probes the repo and prints what a profile *would* wire now, writing nothing, so the diff between that and `quality_blocks.py` is the drift. Report it; regenerating is the engineer's call, because it overwrites hand edits.

## Report

Tell the engineer, in order: which chain and which roster you launched (name the config whenever it was not the default), which phase is running now (or which failed), phase statuses in sequence, and for a failure the gate violations or the error verbatim. Remember **every phase defaults to `fail`** — a phase showing `fail` may simply never have completed; `queued` means it never started. Don't dress up a partial run as a success.

For a visual live view, the visualizer app in the skill polls this same db — sessions as cards, runs as swim lanes, phases and tool calls drill-in. `just obs` boots both halves: the API on `:4600` and the Vite dev server on `:4601`. **Open `http://localhost:4601`** — 4600 is the API, and it serves the UI only when a built `dist/` exists, which the skill does not ship. The sqlite queries above remain the headless equivalent.
