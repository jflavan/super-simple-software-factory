# SSSF: Claude Code backend + the `dotnet-svelte` stack profile

**Date:** 2026-09-10
**Status:** Approved design, pending implementation plan
**Driving case:** `codec-chat` (ASP.NET Core 10 + EF Core + PostgreSQL + SvelteKit 5 + SignalR)
**Scope:** Changes land in `super-simple-software-factory` only. No file in `codec-chat` is modified.

---

## 1. Problem

SSSF is not installed in `codec-chat`, and as shipped it could not run there. Three findings,
each verified against the working tree rather than inferred:

1. **The only implemented coding agent is unavailable.** `pi` is not on PATH on the target
   machine; `claude` 2.1.268 is. `agents.validate()` rejects any agent whose
   `coding_agent != "pi"`, and `agent_cc.py` is a stub that raises. Every ADW dies at
   validation before spawning anything.
2. **Bare-name argv does not resolve on Windows.** `quality.py`'s documented contract is to
   call binaries by bare name. `subprocess.run(["npm", "--version"])` raises `WinError 2`
   here, because `npm` is `npm.cmd`. `quality.py` catches that `OSError` and reports exit 127,
   so a misconfiguration is indistinguishable from a genuine command failure. `just` and
   `dotnet` are real `.exe` and resolve correctly.
3. **`operator_env()` is inert on Windows.** It strips `Path(venv) / "bin"` from PATH; uv on
   Windows uses `Scripts`. The venv-shadowing hazard it documents is therefore unmitigated
   on this platform.

Separately, the `sqlite3` CLI is absent, so every observability instruction in the justfile,
the cookbooks, and `references/observability.md` fails.

Beyond making it run, the factory's shipped defaults are wrong for this stack: `quality.py`
ships `echo` placeholders that exit 0 (the README names this its own worst failure mode), and
the prompts direct agents at `bun`, `uv`, and `pytest`.

## 2. Goals

- A working Claude Code backend, so the factory runs where `claude` is the available agent.
- A **reusable stack profile** for ASP.NET Core + EF Core + SvelteKit repos that produces a
  real, wired factory on install — in `codec-chat` and in any other repo of the same shape.
- Git flow that matches how such repos actually merge: a branch per run, ending in a PR.

### Non-goals

Sandboxing, a human-approval phase, visualizer work, and migrating the default roster off
`pi`. `pi` remains the default backend; the profile selects Claude Code.

## 3. Design rule for the profile

**Nothing in a profile may name a path specific to one repository.** Every value is one of:

- a **stack fact** — EF Core writes a `.Designer.cs` beside every migration;
- a **discovered fact** — where the `.sln` is, which `package.json` files declare `@sveltejs/kit`;
- a **configured fact** — which docs a given change requires, declared in `sssf.config.yaml`.

`codec-chat` is the profile's first instance and its test case, never its definition. The
acceptance test for this rule: stamping the profile into a *different* ASP.NET Core + SvelteKit
monorepo must yield a working factory with no code edits.

---

## 4. Part A — Portability layer

### A1. `adw_modules/agent_cc.py` — the Claude Code backend

Replaces the stub. Exposes the same four names `agent_pi` does, so `agents.py` can dispatch
between them without knowing which it holds: `run()`, `resolve_model()`, `context_window()`,
and a tool-call tracker.

**Invocation.** `claude -p --output-format stream-json --verbose --model <id>
--append-system-prompt <text> --allowedTools <list> --permission-mode acceptEdits`, prompt on
argv, `stdin=DEVNULL`. The stdin rule is carried over deliberately: `agent_pi` documents a
silent total hang when a child inherits a non-TTY stdin, and the same hazard applies here.

**Sessions.** `pi --session-id` is create-or-continue. Claude Code's `--session-id` requires a
UUID and refuses an id that already exists; continuing uses `--resume <uuid>`. SSSF mints
`sssf-{adw_id}-{agent}-{hex4}`, which is not a UUID. The adapter therefore keeps a mapping from
the SSSF session id to a generated UUID, persisted in the agent's session directory:

- first send for a given SSSF session id → generate a UUID, pass `--session-id <uuid>`;
- every later send (JSON parse retries, gate corrections) → `--resume <uuid>`.

This preserves hard rule 2's guarantee that corrections re-enter the same session with context
intact.

**Events.** Claude Code's stream has no `tool_execution_end`. Tool calls appear as `tool_use`
blocks inside assistant messages and return as `tool_result` blocks inside subsequent user
messages. `CcToolCallTracker.observe(event)` pairs them and emits **the same normalized record
shape** `agent_pi.ToolCallTracker` emits — `tool`, `tool_call_id`, `args`, `ok`, `label`,
`result_snippet`, `started_at`, `ended_at`, `duration_ms`. Because the record shape is
preserved, `tracer.py`, `console.py`, and the visualizer require no changes.

**Usage and cost.** Read from the terminal `{"type": "result"}` event: `total_cost_usd` and
`usage`. Context occupancy is taken from the last valid assistant turn, matching `agent_pi`'s
rule that an aborted or errored turn must not overwrite a good reading.

**Thinking.** Claude Code has no `--thinking` flag. SSSF's levels map to `MAX_THINKING_TOKENS`
in the child environment:

| SSSF level | `MAX_THINKING_TOKENS` |
|---|---|
| `off` | unset |
| `minimal` | 1024 |
| `low` | 4000 |
| `medium` | 10000 |
| `high` | 24000 |
| `xhigh` | 32000 |
| `max` | 64000 |

**Tools.** `tools:` entries are pi's lowercase names. The adapter maps them:

| SSSF | Claude Code |
|---|---|
| `read` | `Read` |
| `bash` | `Bash` |
| `edit` | `Edit` |
| `write` | `Write` |
| `grep` | `Grep` |
| `find` | `Glob` |
| `ls` | `Bash` |

A name with no mapping — notably the `subagent_*` tools registered by a pi extension — fails
validation with an explicit message. It must never be silently dropped: the config file already
warns that a filtered-out extension tool is invisible at runtime, and that warning must hold
for both backends.

**Harness engineering.** `pi -e <extension.ts>` has no Claude Code equivalent. An agent that
declares `harness_engineering` while running on `claude_code` fails validation, naming the
extension and the agent.

**Model resolution.** `resolve_model("anthropic/claude-opus-5")` returns `("anthropic",
"claude-opus-5")` and passes the bare id to `--model`. Unlike pi, there is no catalog to probe,
so resolution validates the `provider/id` shape and the known-provider name only.
`context_window()` reads a small static table with a conservative default for unknown ids.

**Binary resolution.** `claude` is located through `utils.resolve_argv` (A3), honouring a
`CLAUDE_CODE_PATH` override, so a `.cmd` shim on Windows resolves correctly.

### A2. Backend dispatch in `agents.py`

`agents.py` is the only module that imports `agent_pi`, across six references — the import
plus `agents.py:69,109,112,127,237`. Introduce a `backend_for(agent) -> module` helper
returning `agent_pi` or `agent_cc`, and replace the direct references. `validate()` drops its
pi-only rejection and instead calls the selected backend's `resolve_model()` and a new
`validate_agent(agent)` hook, letting each backend refuse what it cannot honour (unmappable
tools, extensions on Claude Code, ambiguous pi model patterns).

**Rename.** `PiRequest` / `PiResult` become `AgentRequest` / `AgentResult` in
`data_types.py`. Two backends sharing a type named for one of them is a lie in the type system.
Call sites are `agents.py`, `agent_pi.py`, `agent_cc.py`, and two prose references in
`cookbooks/update_modules.md`; all are updated in the same change, per the synced-triad
discipline hard rule 2 already requires.

### A3. Windows portability

- `utils.operator_env()` strips `Scripts` on Windows and `bin` elsewhere.
- New `utils.resolve_argv(argv) -> list[str]`: resolves `argv[0]` via `shutil.which` (which
  honours PATHEXT), returning the argv unchanged when resolution fails so the existing
  exit-127 path still reports a genuinely missing binary. `quality.py` and `agent_cc.py`
  route every subprocess launch through it.
- `gates.tests_pass` keeps `shell=True`, which is correct on both platforms.

### A4. `adws/adw_trace.py` — trace reader

A small stdlib-`sqlite3` CLI replacing every shell-out to the `sqlite3` binary, which is not
installed. Subcommands: `sessions`, `phases <adw_id>`, `events <adw_id> [--type]`,
`gates <adw_id>`, `processes`. The stamped justfile, `cookbooks/`, and
`references/observability.md` are updated to call it.

---

## 5. Part B — The profile mechanism and the `dotnet-svelte` profile

### B0. Mechanism

```
templates/profiles/<name>/
  profile.yaml         detection rules, recipe map, gate set, prompt overlay manifest
  detect.py            repo probe -> a ProfileFacts object
  generate.py          ProfileFacts -> a concrete quality.py + config fragment
  gates/               profile gate functions
  prompts/             prompt overlay fragments
```

`install.py --profile <name>` applies one; with no flag, each profile's detection rules are
evaluated and an unambiguous match is applied automatically. `dotnet-svelte` is the first
instance and the reference implementation. A future `node-only` or `python-uv` profile is
purely additive and touches no core module.

**`ProfileFacts`** is a concrete Pydantic type (per hard rule 4) carrying: solution path,
.NET project list with each project's role (`app` / `unit-tests` / `integration-tests`),
frontend list (directory, package manager, available scripts), task-runner recipes when one
exists, default branch, and the convention files found.

### B1. Detection — `dotnet-svelte`

Matches when the repo contains **both** a `*.sln` (or `*.slnx`) and at least one `package.json`
declaring `@sveltejs/kit`.

Probes, none of which assume a directory layout:

- Enumerate solution projects via `dotnet sln list`. Classify each: a project referencing
  `xunit` is a test project; one additionally referencing `Testcontainers` is an
  **integration** test project.
- Find every frontend independently — any `package.json` declaring `@sveltejs/kit` — and read
  its `scripts` to learn which of `check`, `test`, `build`, `lint` exist. A repo with one
  frontend or four is handled identically. (`codec-chat` has two, `web` and `admin`; that
  exercises the general case rather than defining a special one.)
- If a `justfile` exists, parse `just --summary` and prefer a matching recipe over a raw
  command wherever one exists.
- Determine the default branch from `git symbolic-ref refs/remotes/origin/HEAD`, falling back
  to the current branch.
- Record which convention files exist: `CLAUDE.md`, `AGENTS.md`, `.github/instructions/*`,
  `.cursor/rules`.

### B2. Generated `quality.py`

The generator writes a concrete `quality.py` with real argv lists baked in and a header comment
recording what was detected and when. The command stays written down as code — hard rule 8
holds; it is simply written by the installer instead of by hand. This directly closes the
failure the README names first: *"the test phase reports green on a fresh install."*

Preference order per block: a matching task-runner recipe, else a raw argv
(`dotnet test <project>`, `npm --prefix <dir> run check`). Every emitted argv passes through
`utils.resolve_argv`.

### B3. Tiered blocks — `fast` and `full`

Each generated block carries a tier. Integration test projects (Testcontainers, therefore
Docker) are tagged `full`; unit tests, typechecks, and builds are `fast`.

- `run_tests(run)` — the block used inside bounded fix loops — runs the `fast` tier only.
- `run_quality(run)` — final verification — runs both.

This is a stack-general consequence of the stack having a slow, service-dependent suite. A repo
that hand-wrote a `test-fast` / `test` split gets the same behaviour synthesized; a repo that
never wrote one gets it for free.

### B4. Gates

New `gates_dotnet_svelte.py` in the profile. Each is `gate(envelope, run) -> GateReport`,
matching the existing contract.

- **`ef_migration_triad`** — for every `*/Migrations/*.cs` in `changed_files` that is not
  itself a `.Designer.cs` or a `*ModelSnapshot.cs`, require the sibling `.Designer.cs` to exist
  and the `*ModelSnapshot.cs` in the same directory to appear in `changed_files`. Pure EF Core
  semantics, no repo-specific paths. This catches a failure that is otherwise silent —
  `Database.Migrate()` skips a migration with no Designer.cs, and the break surfaces later as
  a `PendingModelChangesWarning` in integration tests.
- **`doc_policy`** — **config-driven**, not code. A new optional `doc_policy:` block in
  `sssf.config.yaml`:

  ```yaml
  doc_policy:
    - when: "apps/api/**/Auth*.cs"
      require: ["docs/AUTH.md"]
    - when: "apps/web/src/**"
      require: ["docs/ARCHITECTURE.md", "docs/FEATURES.md"]
  ```

  The gate reports a violation when a `when` pattern matches a changed file and no `require`
  entry appears in `changed_files`. Any repo's documentation contract becomes YAML; none of it
  becomes code.
- **`env_example_sync`** — parameterized by (prefix, example-file) pairs, defaulting to
  SvelteKit's `PUBLIC_` and Vite's `VITE_` conventions with example files discovered at install.
  A new public variable in a frontend source file requires the matching `.env.example`.
- **`sveltekit_csp`** — opt-in, enabled only when detection finds a CSP declaration in a
  discovered `src/hooks.server.ts`. A newly introduced external origin requires that file to
  change. SvelteKit convention, not a repository convention.

### B5. Prompt overlay

The overlay carries **stack** guidance only: EF Core migrations are a three-file change; prefer
Svelte 5 runes over legacy stores; prefer the detected task runner over raw commands; judge
success by exit status. It replaces the shipped builder prompt's `bun` / `uv` / `pytest`
direction.

Repository-specific standards are **referenced, not restated**: the generator renders the list
of convention files it actually found into the prompt, instructing the agent to read them.
Restating them would duplicate and drift, and .NET 10 / C# 14 and Svelte 5 runes post-date most
model priors, so pointing at the live file is also the more accurate option.

### B6. `install.py --doctor`

Prints what was detected, which blocks and gates were wired, and — critically — what could not
be resolved. Stamping into an unfamiliar repo produces a readable report instead of silent
placeholders. `--doctor` is also the re-probe after a repo's layout changes.

---

## 6. Part C — Branch per run, ending in a PR

`git_helper` gains `default_branch()`, `create_run_branch(adw_id)`, `push_branch()`, and
`open_pr(title, body)` via the `gh` CLI.

New `adws/adw_plan_build_test_pr.py`: the `adw_simple_sdlc` spine, with a branch created before
the first commit phase and a `pr` phase after verification. Acceptance still routes through
`run.finish(accepted=...)`, so a red suite leaves the branch pushed and **no** PR opened — the
honest outcome, and consistent with hard rule 10.

Degradation is explicit: no `gh`, or no remote, means push-only with a logged note, never a
silent skip. Existing ADWs keep current-branch behaviour; this workflow is additive.

## 7. Part D — Skill surface

- `SKILL.md` — the v1-scope paragraph and hard rule 9 updated for two backends.
- `cookbooks/install.md` — a profile section, and a preflight covering backend availability
  (`pi` vs `claude`) and the absent `sqlite3` CLI.
- `references/config.md` — the `claude_code` backend, the `doc_policy` block, profile keys.
- `cookbooks/update_modules.md` — the `AgentRequest` / `AgentResult` rename.
- `README.md` — correct the "Where it can still fail" rows for `coding_agent: claude_code` and
  the placeholder test phase, both of which this change resolves.
- A worked-example appendix walks the `codec-chat` install end to end. It is documentation;
  no shipped file names that repository.

---

## 8. Verification

Evidence, not assertion. `agent_cc.py` is the highest-risk component and is tested live.

The scope rule — no file in `codec-chat` is modified — constrains this. Tests 1 and 2 are
read-only and run against `codec-chat`, which is the point: they prove detection and the
backend against a real repository of the stack. Test 3 writes code, so it runs against a
**disposable fixture repo** of the same stack, generated by the test suite. Running it against
`codec-chat` requires explicit go-ahead and a throwaway branch, and is not part of the
default verification.

1. `adw_prompt.py` against `codec-chat` — one agent, read-only, one envelope. Proves config
   validation, session minting, spawn, stream parse, envelope parse, and trace write.
2. `adw_scout.py` against `codec-chat` — multi-tool-call recon. Proves `CcToolCallTracker`
   pairing and streaming trace rows.
3. `adw_plan_build_test_pr.py` against the fixture repo. Proves the chain, the generated
   quality blocks, the gates, the branch, and the PR step.

Each is confirmed by querying `sssf.db` through `adw_trace.py`, not by reading console output.

Unit tests, runnable without a live agent:

- Gates are pure functions over a changeset — tested against synthetic `changed_files` lists,
  including the negative cases (a migration with no Designer.cs; a `PUBLIC_` var with no
  `.env.example` change).
- `detect.py` and `generate.py` are tested against fixture repo trees: one frontend, three
  frontends, no justfile, no integration tests.
- Tool-name mapping and thinking-level mapping are table-driven tests.

## 8a. Verified (2026-09-11)

Part A was implemented and verified live against a scratch clone of `codec-chat`, with the
factory stamped in and the roster switched to `coding_agent: claude_code` on
`anthropic/claude-sonnet-5`. No file in `codec-chat` was modified; `git status` there was
empty before and after.

| Run | ADW | Result | Tokens | Cost | `tool_call` rows |
|---|---|---|---|---|---|
| `f818e39d` | `adw_prompt` | success | 19 | $0.175044 | 2 |
| `0eeeab3d` | `adw_scout` | success | 162 | $0.261514 | 20 |

The console banner and the trace agreed exactly on status, tokens and cost for both runs —
which is the property `run.finish()` exists to guarantee. Validation was also confirmed to
reject a bad config before spawning anything: an agent declaring `harness_engineering` on
the Claude Code backend exited 1 naming the agent and the field.

**Live verification earned its place.** The first attempt failed on every run with
`Error: Input must be provided either through stdin or as a prompt argument when using
--print`. `--allowedTools` is variadic (`<tools...>`), so it swallowed the trailing
positional prompt and `--print` received no input. It broke every agent in the roster,
deterministically — and all 85 offline tests passed throughout, because each asserted on
the **contents** of the argv list and none on how the CLI **parses** it. The fix moves the
variadic flag early so a scalar flag and its value always separate it from the prompt, and
two regression tests now encode that rule rather than our assumptions about it.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Claude Code's stream-json shape changes | The tracker is the only component that parses it, and it normalizes to one record type. A shape change is one file. |
| `--resume` semantics differ from pi's create-or-continue | Explicit UUID map with first-send/later-send branching; covered by test 1, which performs a JSON-retry correction. |
| Generated `quality.py` goes stale after a repo restructure | `--doctor` re-probes and reports drift; the generated header records what was detected. |
| Detection misclassifies a project | `--doctor` prints the classification before anything runs; the generated file is plain, editable Python. |
| `doc_policy` becomes noisy and gets disabled wholesale | It is opt-in and starts empty. Patterns are added deliberately. |

## 10. File manifest

**Modified:** `templates/adws/adw_modules/{agent_cc,agents,data_types,utils,quality,git_helper}.py`,
`scripts/install.py`, `templates/justfile`, `SKILL.md`, `README.md`,
`cookbooks/{install,update_modules,create_config,sssf_overview}.md`,
`references/{config,observability,handoff}.md`.

**Added:** `templates/adws/adw_trace.py`, `templates/adws/adw_plan_build_test_pr.py`,
`templates/profiles/dotnet-svelte/{profile.yaml,detect.py,generate.py,gates/,prompts/}`,
and the test suite for gates, detection, and generation.
