# Install

`/sssf install` — stamp the entire factory out of the skill and into the current working directory.

## Run it

```bash
uv run .claude/skills/sssf/scripts/install.py
```

Run from the **target repo root** — the cwd is where everything lands. If the skill lives in your user scope, the path is `~/.claude/skills/sssf/scripts/install.py`.

## What gets stamped

`install.py` copies `templates/` into the cwd:

| Stamped | From | Tracked? |
|---|---|---|
| `adws/adw_sssf_config/sssf.config.yaml` | `templates/sssf.config.yaml` | yes — the agent roster |
| `.env.sample` | `templates/env.sample` | yes |
| `adws/adw_*.py` | `templates/adws/` | yes — the twelve starter ADWs |
| `adws/adw_modules/` | `templates/adws/adw_modules/` | yes — all low-level logic |
| `adws/adw_data/prompt_engineering/{planner,builder,scout,reviewer,documenter}/` | `templates/prompt_engineering/` | yes — **the user-owned home for prompts** |
| `adws/adw_data/harness_engineering/` | `templates/harness_engineering/` | yes — **the user-owned home for pi extensions** |
| `justfile` | `templates/justfile` | yes — starter recipes: `just demo`, the workflows, the trace reads, `just obs` |
| `adws/adw_data/sessions/`, `adws/adw_data/sssf.db` | created at runtime | no — gitignored |

The two `*_engineering` dirs mirror the two config keys of the same name: `prompt_engineering` is what an agent is told, `harness_engineering` is what its harness can do. Both are yours the moment they are stamped. Edit them in `adws/adw_data/`, never back inside the skill.

`harness_engineering/` ships with `subagents.ts` — the pi extension backing `subagent_create` / `_continue` / `_list` / `_remove`, wired to the planner and scout in the starter roster.

## Idempotency

Re-running is safe. `install.py` skips **every** file that already exists — your config, your prompts, and previously stamped code alike — and reports what it skipped, so a second run doubles as a drift check. To refresh stamped code (`adw_modules/`, the starter `adw_*.py`) to the skill's current version, run with `--force` — but know that `--force` overwrites ALL existing stamped files, including `sssf.config.yaml` and `prompt_engineering/`, so commit or back up user-owned edits first.

## Post-install checklist

1. **Env** — `cp .env.sample .env`, then set the keys your roster actually needs: `OPENROUTER_API_KEY` (and friends) for `coding_agent: pi` agents, `ANTHROPIC_API_KEY` for `coding_agent: claude_code` agents. The starter roster runs `pi` throughout, so only the Pi key is required out of the box.
2. **The coding agent is installed and on PATH** — `pi --version` for any `pi` agent, `claude --version` for any `claude_code` agent. Set `PI_PATH` / `CLAUDE_CODE_PATH` in `.env` if the binary is not found under its default name.
3. **The model resolves.** For `pi`, the config's default `gemini-3.6-flash` must be a registered id in `~/.pi/agent/models.json` — check with `pi --list-models` or read the file directly. For `claude_code`, the model is written `anthropic/<model-id>` and only its shape and provider are validated — there is no catalog to probe. See `references/config.md` for both.
4. **Gitignore** — `install.py` appends `adws/adw_data/sessions/`, `adws/adw_data/sssf.db*`, and `.env` for you; confirm they landed. All three are runtime or secrets and must never be committed.
5. **Git repo** — ADWs that end in a commit phase call `git_helper.commit_all`, which raises if the cwd is not a git repository. Run `git init` and make a first commit before using `adw_plan_build.py`, `adw_plan_build_test.py`, or `adw_simple_sdlc.py`. `adw_document.py` needs one too: it measures the change with `git diff` against a base ref (`main` by default, `--base` to override).
6. **Windows: force UTF-8 on your console.** The run banner prints box-drawing and arrow
   characters. A default Windows console is cp1252 and cannot encode them, and the failure is
   not cosmetic — `rich` raises `UnicodeEncodeError` mid-phase, the run dies before it can
   record the phase's outcome, and that session's row stays `running` in the trace forever.
   Set both, in the shell you launch ADWs from:

       PYTHONUTF8=1
       PYTHONIOENCODING=utf-8

   Windows Terminal with a UTF-8 code page works too. Non-Windows consoles are unaffected.
7. **Smoke test** — `just demo` runs two cheap read-only workflows back to back, or run the smallest ADW directly:

```bash
just demo                                                    # both, end to end
uv run adws/adw_prompt.py "reply with a one-line summary of this repo"   # the raw form
```

Green means the whole path works: config validated, session minted, the coding agent ran, envelope parsed, events landed in `adws/adw_data/sssf.db`. Verify the trace exists before trusting anything larger:

```bash
uv run adws/adw_trace.py sessions --limit 1
```

If the smoke test fails, fix it before composing chains — every multi-agent ADW rides on this exact path.

## Upgrading an existing installation

The per-agent session directory was renamed from `pi_sessions/` to `sessions/`. A run
resumed with `--adw-id` from before the rename will find an empty directory — and pi's
`--session-id` creates-or-continues, so it starts a fresh session rather than failing,
and that agent silently loses its history. Before resuming an older run, rename the
directory under each agent:

    adws/adw_data/sessions/<adw_id>/<agent>/pi_sessions  ->  .../sessions

Or simply start the run again. New installations are unaffected.
