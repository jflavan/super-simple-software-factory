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

That is the stamped half only. A profiled install also **generates** three files and stamps one gate module per framework — see "Stack profiles" below for the full list, because those are the files an operator is most likely to go looking for and not find here.

The two `*_engineering` dirs mirror the two config keys of the same name: `prompt_engineering` is what an agent is told, `harness_engineering` is what its harness can do. Both are yours the moment they are stamped. Edit them in `adws/adw_data/`, never back inside the skill.

`harness_engineering/` ships with `subagents.ts` — the pi extension backing `subagent_create` / `_continue` / `_list` / `_remove`, wired to the planner and scout in the starter roster.

## Idempotency

Re-running is mostly safe. `install.py` skips every **stamped** file that already exists — your config, your prompts, and previously stamped code alike — and reports what it skipped, so a second run doubles as a drift check. The three **generated** files are the exception and are rewritten on every profiled run, deliberately: they describe the repo as it is now, so preserving a stale copy of them would be the wrong kindness. A re-run can also *refuse* outright — see "Upgrading" below. To refresh stamped code (`adw_modules/`, the starter `adw_*.py`) to the skill's current version, run with `--force` — but know that `--force` overwrites ALL existing stamped files, including `sssf.config.yaml` and `prompt_engineering/`, so commit or back up user-owned edits first.

## Post-install checklist

1. **Env** — `cp .env.sample .env`, then set the keys your roster actually needs: `OPENROUTER_API_KEY` (and friends) for `coding_agent: pi` agents, `ANTHROPIC_API_KEY` for `coding_agent: claude_code` agents. The starter roster runs `pi` throughout, so only the Pi key is required out of the box.
2. **The coding agent is installed and on PATH** — `pi --version` for any `pi` agent, `claude --version` for any `claude_code` agent. Set `PI_PATH` / `CLAUDE_CODE_PATH` in `.env` if the binary is not found under its default name.
3. **The model resolves.** For `pi`, the config's default `gemini-3.6-flash` must be a registered id in `~/.pi/agent/models.json` — check with `pi --list-models` or read the file directly. For `claude_code`, the model is written `anthropic/<model-id>` and only its shape and provider are validated — there is no catalog to probe. See `references/config.md` for both.
4. **Gitignore** — `install.py` appends five entries for you; confirm they landed: `adws/adw_data/sessions/`, `adws/adw_data/sssf.db*`, `.env`, `__pycache__/`, and `*.pyc`. The first three are runtime or secrets. The last two matter because the ADWs are Python and importing `adw_modules` writes bytecode next to it — chains ending in a commit phase call `git add -A`, and without those entries a stamped repo commits its own `.pyc` files.
5. **Git repo** — ADWs that end in a commit phase call `git_helper.commit_all`, which raises if the cwd is not a git repository. Run `git init` and make a first commit before using `adw_plan_build.py`, `adw_plan_build_test.py`, or `adw_simple_sdlc.py`. `adw_document.py` needs one too: it measures the change with `git diff` against a base ref (`main` by default, `--base` to override).
6. **Windows: optional, and no longer load-bearing.** The run banner prints box-drawing
   and arrow characters that a default cp1252 console cannot encode. That used to kill the
   run — `rich` raised `UnicodeEncodeError` mid-phase, the process died before it could
   record the phase's outcome, and the session's row stayed `running` in the trace forever.

   It no longer does. Every file the factory reads or writes names `utf-8` explicitly
   rather than inheriting the locale codec, and the console switches stdout to
   `errors="replace"` on the way up, so an unencodable glyph prints as `?` instead of
   raising. The trace is UTF-8 in SQLite either way, so the visualizer shows the real
   characters whatever the terminal could render.

   Setting these still gets you the glyphs instead of `?`, which is nicer to read:

       PYTHONUTF8=1
       PYTHONIOENCODING=utf-8

   Windows Terminal with a UTF-8 code page does the same. Non-Windows consoles are
   unaffected, and always were.
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

## Stack profiles

Without a profile, `quality.py` stays on its `PLACEHOLDER_BLOCKS` — every check is an
`echo` that exits 0 and says out loud that it is fake. A **profile** replaces them
with this repo's real commands, discovered by probing the tree. A bare install is not
the same as `--no-profile`: with no flag at all the installer auto-detects, and the
placeholders survive only when nothing matches.

```bash
uv run <skill>/scripts/install.py                       # auto-detect
uv run <skill>/scripts/install.py --profile dotnet-svelte
uv run <skill>/scripts/install.py --no-profile          # stamp only, wire nothing
uv run <skill>/scripts/install.py --doctor              # re-probe, write nothing
```

With no `--profile`, every profile is tried and the one whose declared frameworks
*all* match is applied; none leaves the placeholders in place (and says so); more
than one stops and asks for `--profile` by name, because wiring a repo to the
wrong stack produces a factory whose checks all pass without running anything
real. Detection runs **before** anything is stamped, so the report describes the
repo you pointed it at, not the factory it is about to write into that repo.

Applying a profile writes three generated files, in this order:

| Path | What it is |
|---|---|
| `adws/adw_modules/profile_gates.py` | generated: the stack gates, wired from what was found |
| `adws/adw_modules/quality_blocks.py` | generated: this repo's real commands, each with a `fast` or `full` tier |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | generated: stack guidance, injected wherever a prompt includes `{{profile_overlay}}` |

Gates before blocks is deliberate: `quality.py` treats the presence of
`quality_blocks.py` as "a profile generated this repo", and the gate loader
treats a missing `profile_gates.py` as "no profile, no stack gates". Writing
gates first means a partial write reads as "not installed" rather than
"installed and quietly weaker".

A profile also stamps one gate module per framework it declares — e.g.
`adws/adw_modules/gates_dotnet.py` — into `adw_modules/`, the same way every
other shipped module is stamped: skipped if it already exists, refreshed only
with `--force`. All three generated files are plain, editable Python (and
Markdown for the overlay), and all three are overwritten by the next
profiled install. Hand edits belong in the *stamped* gate modules or the
prompt files, none of which an install overwrites without `--force`.

**`--doctor`** re-probes and prints what an install would wire today, without
writing anything — it works even on a repo with no `adws/` yet. Run it after a
restructure: the generated blocks do not notice that a frontend moved, and a
command pointing at a directory that no longer exists fails in a way that reads
like a broken build.

### Upgrading: a profile cannot be applied over an older stamped tree

`stamp()` skips any file that already exists unless `--force` — so applying a
profile to a repo that was installed from an earlier SSSF version leaves
`quality.py`, `gates.py`, `utils.py`, `data_types.py`, the ADW scripts, and
`builder/system.md` at their old contents while generation writes the three
files above beside them anyway. The install would report a wired factory and
wire nothing: a stale `quality.py` has no `_import_generated_blocks`, so
`quality_blocks.py` is inert and the `echo` placeholders keep running; a stale
`gates.py` has no `profile_gates()`, so the generated `profile_gates.py` is
inert too; and a stale `builder/system.md` has no `{{profile_overlay}}`, so the
overlay is never injected.

The installer refuses the part it can see: applying `--profile` (or
auto-detecting one) against a repo whose stamped **modules** predate what the
generated files need exits non-zero and names exactly which module is stale
and what breaks without it. The check is three symbols in three files —
`_import_generated_blocks` in `quality.py`, `profile_gates` in `gates.py`,
`claimed_files` in `utils.py` — chosen because a symbol is what the generated
file actually needs, and there is no version to compare.

**It does not cover your prompts.** A `builder/system.md` that predates
`{{profile_overlay}}` passes this check, the install succeeds, it reports a
wired factory, and the overlay is generated and then silently never injected —
the third breakage listed above is the one the guard cannot see. Diff
`adws/adw_data/prompt_engineering/` against the skill's
`templates/prompt_engineering/` after any upgrade.

The fix is `--force`:

```bash
uv run <skill>/scripts/install.py --profile dotnet-svelte --force
```

**Commit first.** `--force` does not touch only the stale modules named in the
error — it refreshes *every* stamped file, which also overwrites
`adws/adw_sssf_config/sssf.config.yaml` and everything under
`adws/adw_data/prompt_engineering/`. Any hand edits to the agent roster or the
prompts need to be committed (or otherwise preserved) before you re-run with
`--force`, so you can diff or restore them afterward. `--doctor` is unaffected
by all of this — it writes nothing, so it has nothing to protect, and keeps
working against a repo it does not own even when the repo is stale.

### The `dotnet-svelte` profile

Matches a repo containing both a `*.sln`/`*.slnx` and a `package.json`
declaring `@sveltejs/kit`. `templates/profiles/dotnet_svelte/profile.yaml`
holds nothing but three fields, of which only `frameworks` is required —
`name` falls back to the directory name and `description` defaults to empty:

```yaml
name: dotnet-svelte
description: ASP.NET Core + EF Core + SvelteKit repositories.
frameworks: [dotnet, sveltekit]
```

Everything else lives in the two frameworks it names.

## Adding a profile

If every technology in the stack already has a framework module, a new stack is
**one file and no registration**. Make a directory under `templates/profiles/`
and put a `profile.yaml` in it, naming only frameworks that are registered
today — `dotnet` and `sveltekit`:

```yaml
name: sveltekit-only
description: A SvelteKit front end with no .NET behind it.
frameworks: [sveltekit]
```

`registry._discover` globs `*/profile.yaml`, so it is visible to `install.py`
and to `--profile sveltekit-only` immediately. Nothing imports it, nothing
lists it, and no shared file changes. That is the cheap path, and it is the one
to check for before writing any Python.

**Naming a framework that is not registered breaks every install, not just
this profile.** `_discover` constructs a `CompositeProfile` for *every*
`*/profile.yaml` it finds, and `install.py` calls `registry.names()` while it
is still building its `--help` text — so one bad file exits with
`unknown framework 'vue' - available: dotnet, sveltekit` before any flag is
parsed, taking `--doctor` and `--no-profile` down with it. If the stack needs
a technology nothing implements yet, write the framework module first: that is
"Adding a framework" below, and the YAML is its last step, not its first.

## Adding a framework

A **framework** owns one technology; a **profile** is a YAML file naming the
frameworks a stack is made of. That split is why pairing .NET with a different
frontend costs one new file, not a fork of the existing profile — the acceptance
test for the design builds a third framework end to end in a 64-line module and
changes no shared module, only the two registration lines of step 4 below.

To add one — Angular, React, Django, whatever:

1. **`templates/profiles/frameworks/<name>.py`** — expose the eight names in
   `FRAMEWORK_INTERFACE`: `NAME`, `GATE_MODULE`, `OVERLAY`, `matches`, `detect`,
   `blocks`, `describe`, `gate_wiring`. Copy `sveltekit.py` for a frontend or
   `dotnet.py` for a backend; both are deliberately short, because the shared
   work is already done by `probes` (finding things) and `emit` (writing them).
   A frontend framework is usually `probes.node_packages(root, "<its marker
   dependency>")` for detection and `emit.script_blocks(...)` for commands. Set
   `GATE_MODULE = ""` and `OVERLAY = ""` if the framework brings neither.
2. **`templates/profiles/gates/<GATE_MODULE>.py`** — only if `GATE_MODULE` is
   non-empty. This file is STAMPED into a target repo's `adw_modules/`, so its
   imports are relative (`from .data_types import ...`), never absolute.
3. **`templates/profiles/prompts/<OVERLAY>`** — only if `OVERLAY` is non-empty:
   a Markdown fragment folded into the generated `profile_overlay.md`.
4. **Register it in `templates/profiles/frameworks/__init__.py`** — two edits,
   both required: import the module at the top of the file, and add it to the
   `FRAMEWORKS` tuple. Doing one without the other raises a `NameError` naming
   a framework that is right there in the tuple.
5. **`templates/profiles/<profile_dir>/profile.yaml`** — name it alongside
   whatever it pairs with (or alone, for a single-framework profile).

Step 4 is the only shared file a framework touches, and it is two lines in a
registration tuple. Nothing in `composite.py`, `registry.py`, `probes.py`,
`emit.py`, or `facts.py` changes, and no other framework's file changes — *that*
is the claim the design makes, and it is the one the acceptance test pins. A
framework must never import another framework: shared work goes through `probes`
and `emit` only.

Adding a **profile** touches no shared file at all, not even a registration
tuple — see "Adding a profile" above.

`tests/fake_framework.py` is a worked example — a third framework ("vue",
standing in for the real next profile) built from `probes`, `emit`, and the
`facts` vocabulary alone. `tests/test_framework_reuse.py` walks all five steps
against it, including registration (appending to `FRAMEWORKS`, exactly as step
4 describes) and discovery (`registry._discover` finding its `profile.yaml`),
and asserts the shared modules needed no new parameter to support it.

## Upgrading an existing installation

The per-agent session directory was renamed from `pi_sessions/` to `sessions/`. A run
resumed with `--adw-id` from before the rename will find an empty directory — and pi's
`--session-id` creates-or-continues, so it starts a fresh session rather than failing,
and that agent silently loses its history. Before resuming an older run, rename the
directory under each agent:

    adws/adw_data/sessions/<adw_id>/<agent>/pi_sessions  ->  .../sessions

Or simply start the run again. New installations are unaffected.

## Worked example: an ASP.NET Core + SvelteKit monorepo

This section names one specific repository, `codec-chat`, because it is the one
the profile was verified against. **It is documentation.** Nothing shipped under
`templates/profiles/` references it, and nothing may: a profile encodes stack
facts, discovered facts and configured facts, never a path from one repo.

The repository: `Codec.sln` with five projects, two SvelteKit frontends at
`apps/web` and `apps/admin`, and a `justfile` with 86 recipes.

```bash
cd /path/to/codec-chat
uv run <skill>/scripts/install.py --doctor
```

Abridged output:

```
profile: dotnet-svelte  (frameworks: dotnet, sveltekit)
  solution: Codec.sln
  project: apps/api/Codec.Api/Codec.Api.csproj  [app]
  project: apps/api/Codec.Api.Tests/Codec.Api.Tests.csproj  [unit-tests]
  project: apps/api/Codec.Api.IntegrationTests/...  [integration-tests]
  frontend: apps/web  [npm] scripts: build, check, check:watch, dev, ...
    env example: apps/web/.env.example
    csp: apps/web/svelte.config.js
  task runner: just (86 recipes)
    recipes from: just --summary
  conventions: CLAUDE.md, AGENTS.md, CONTRIBUTING.md, .github/instructions/

  quality blocks wired: 9
    [fast] test-unit: just test-fast
    [full] test-integration: just test-api-integration
    [fast] build-sln: just build-sln
    [fast] check-web: just check-web
    ...
  gates wired: ef_migration_triad, env_example_sync, sveltekit_csp
  doctor: nothing was written.
```

**Every block resolved to a recipe the team already maintains**, rather than to
a command the generator composed. That is the preference order working: a
recipe is what the humans run and what the humans keep working. Where no recipe
matches, the generator composes `dotnet test <project>` or `npm run <script>`
with the package's directory as `cwd` — and says so in the block's trailing
comment, so the operator can tell the two apart at a glance.

Note `test-integration` is tagged `full`. The project references
`Testcontainers`, so it needs Docker up, and a bounded fix loop would pay that
cost on every retry. `run_tests` runs the fast tier; `run_quality` runs both.

### What `--doctor` tells you after a restructure

Generated blocks do not notice that a frontend moved. Rename `apps/web` and
re-run `--doctor`: the report names the new location while the committed
`quality_blocks.py` still names the old one. That difference is the drift, and
re-installing with `--profile` rewrites the file.

### Reading the unresolved section

The most useful half of the report is what it could **not** wire:

```
  UNRESOLVED (1) - these are not checked by anything:
    ! frontend apps/web has no .env.example - the public variable gate is not wired for it
```

A factory that wired eight of nine things has to say which one is missing. The
alternative is discovering it later as a run that passed without checking.
