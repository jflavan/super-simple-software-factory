# Super Simple Software Factory

> **Repeatable agents-plus-code workflows, packaged as one skill, stamped into any repo.**
> Deterministic Python owns the graph. Coding agents are bounded nodes inside it.

📺 Full breakdown on YouTube: **[Super Simple Software Factory](https://youtu.be/haUfb1ievTE)**

<p align="center">
  <img src="images/00_swimlane_waterfall.svg" alt="A run as swim lanes: engineer, code, planner, builder, and reviewer phases laid on a time axis, each block labelled with its duration, one phase still running and the next still queued" width="850">
</p>

<p align="center">
  <img src="images/01_factory_spine.svg" alt="A run spine: engineer, agent, and code phases on a deterministic rail, every event dropping into a SQLite trace db that the UI polls" width="850">
</p>

A software factory does one thing: it gives you more leverage on your prompt. How much leverage depends entirely on what you invest in it. At the low end you chain two agents together and hope. At the high end you build a system of agents plus code that runs without you, and does the job about as well as you would.

Everyone can get an agent to write code once. Almost nobody gets the same result twice. This fixes that by moving the control plane out of the prompt and into Python. An ADW script (AI Developer Workflow) owns sequencing, retries, and acceptance. Agents work inside named phases. Typed JSON envelopes carry context across the seams. Every event streams into SQLite while it is still happening. **Agent proposes, code disposes.**

> [!NOTE]
> **This branch is the skill alone**, which is the thing you install. For a repo with the factory already stamped into it, a demo app it planned, built, tested, reviewed, and documented, and the real traces from those runs, see the **[`example` branch](../../tree/example)**.

---

## Why this exists

<p align="center">
  <img src="images/02_control_plane.svg" alt="Left: one big agent owning its own loop with no phase boundary and no acceptance. Right: code owning the loop with agents as bounded, gated nodes" width="780">
</p>

Hand a capable model your whole SDLC and you get a machine with no seams. There is no phase boundary, so you cannot say which step failed. There is no acceptance criterion you can name, so "done" means "the agent stopped talking." A retry is a cold start that throws away everything the agent just learned. The only trace is a transcript you have to read like a novel. Run it twice, get two different systems.

The fix is not a better prompt. The fix is deciding, deliberately, that **code owns sequencing, retries, and acceptance, and the agent owns only the work inside one bounded phase**. Everything else falls out of that one line. Phases become the unit of the trace. Envelopes become the only way context crosses a seam. Gates become the definition of done. A correction becomes cheaper than a restart, because the session is still alive.

### Agents are great. You do not always need one.

This is the part most engineers are going to skip, and pay for later.

Code costs nothing. It runs at the speed of light. You can change it in a second. And you actually own it, which is not true of any model you are renting by the token.

So when the invocation is already known, write it down. `bun test` is not a judgement call. Neither is `ruff check`. An agent rediscovering your test runner burns a context window to learn what a subprocess already knows, and it charges you for the privilege every single run. Worse, it puts a passing test suite into a context window, which buys you nothing at all.

Agents are for the parts that need reading and deciding. Everything else is a `kind="code"` phase. When code fails, the failure comes back to the builder as an envelope, through the same door an agent's report would have used. The repair loop is identical. You just stopped paying an agent to do arithmetic.

The bill for skipping this is not only tokens. It is cost, speed, and consistency, and you pay it on run one hundred and run one thousand, not on run one.

> *Same models. Same prompts. The difference is who owns the loop.*

---

## Install

Two steps: get the skill into your repo, then stamp the factory.

### Agentic Install

Copy `.claude/skills/sssf/` into the target repo and type `/sssf install` inside Claude Code. The skill is named `sssf`, so that is the skill name followed by the `install` argument. There is no bare `/install` command. The agent reads the skill's own `cookbooks/install.md` and does the rest.

### Manual Install

**Prereqs:** [`uv`](https://docs.astral.sh/uv/), the coding agent(s) your roster names — [`pi`](https://github.com/mariozechner/pi-coding-agent) and/or [Claude Code](https://github.com/anthropics/claude-code) — and an API key for whichever providers your roster names (see below). The trace reads the db with the stdlib `sqlite3` module, so the `sqlite3` CLI is not required. [`bun`](https://bun.sh) only if you want the visualizer.

```bash
# 1. get the skill into the target repo
mkdir -p .claude/skills
cp -r /path/to/super-simple-software-factory/.claude/skills/sssf .claude/skills/

# 2. stamp the factory (run from the target repo ROOT, the cwd is where everything lands)
uv run .claude/skills/sssf/scripts/install.py    # probes for a stack profile, stamps, then wires it
cp .env.sample .env                              # then set OPENROUTER_API_KEY
pi --version                                     # confirm pi is on PATH, or set PI_PATH in .env
git init && git commit --allow-empty -m init     # chains that end in a commit phase need a repo

# 3. smoke test: two cheap read-only runs, end to end
just demo
just sessions              # what just happened
just obs                   # the trace UI, needs bun

# no just? every recipe is one line. the raw form of `just demo` is:
uv run adws/adw_prompt.py "reply with a one-line summary of this repo" --agent scout
```

A bare install does two things. It **probes** your repo for a matching [stack profile](#stack-profiles), then **stamps** the factory — modules, starter ADWs, roster, prompts — and finally uses what it probed to generate this repo's real quality commands, gate wiring, and prompt overlay. Detection runs first deliberately: stamping writes a `justfile` into a repo that has none, and a probe running after that would report the factory's own recipes as if they were yours. Three flags steer the profile half:

| Flag | What it does |
|---|---|
| `--profile NAME` | skip detection and apply that profile by name (`dotnet-svelte` ships in the box) |
| `--no-profile` | stamp the factory only, wire nothing |
| `--doctor` | re-probe and print what *would* be wired, writing nothing — run it whenever your repo's layout changes |

With no flag the installer tries every profile and applies the one whose declared frameworks **all** match. More than one match stops the install and asks rather than guessing. No match is reported out loud, and `quality.py` keeps its `echo` placeholders.

Re-running `install.py` is mostly safe. It skips every stamped file that already exists and reports what it skipped, so a second run doubles as a drift check — but the three **generated** files are rewritten on every profiled run, deliberately, because they describe your repo as it is right now. `--force` refreshes stamped code to the skill's current version, and it overwrites **all** stamped files including your `sssf.config.yaml` and your prompts, so commit first.

Green on the smoke test means the whole path works: config validated, session minted, the coding agent ran, envelope parsed, events landed in `adws/adw_data/sssf.db`. Fix it there before composing anything larger, because every multi-agent chain rides this exact path.

### Upgrading an existing installation

The per-agent session directory was renamed from `pi_sessions/` to `sessions/`. A run
resumed with `--adw-id` from before the rename will find an empty directory — and pi's
`--session-id` creates-or-continues, so it starts a fresh session rather than failing,
and that agent silently loses its history. Before resuming an older run, rename the
directory under each agent:

    adws/adw_data/sessions/<adw_id>/<agent>/pi_sessions  ->  .../sessions

Or simply start the run again. New installations are unaffected.

**A profile cannot be applied over an older stamped tree.** Stamping skips files that
already exist, so installing a newer skill into a repo that already has `adws/` would
leave the old runtime in place while generation writes the new files beside it — a
factory that reports itself wired and enforces nothing. The installer checks three
symbols before it generates anything, and exits non-zero naming the stale module:

    adws/adw_modules/quality.py   needs _import_generated_blocks
    adws/adw_modules/gates.py     needs profile_gates
    adws/adw_modules/utils.py     needs claimed_files

Re-run with `--force` to refresh them, and commit first, because `--force` also
overwrites your roster and your prompts. The check is by symbol, not by version, and it
does not reach your prompts: a `builder/system.md` that predates `{{profile_overlay}}`
still installs cleanly and then never receives the overlay. Diff
`adws/adw_data/prompt_engineering/` against the skill's `templates/prompt_engineering/`
after an upgrade.

### Which API keys you actually need

That depends on your roster, not on this repo. Every `model:` in `sssf.config.yaml` is written `provider/model-id`, and the provider half decides the key. Which key pi reads for a given provider comes from `~/.pi/agent/models.json`.

The starter roster deliberately mixes providers to show the point, so out of the box it wants three:

| Model in the starter roster | Provider | Key |
|---|---|---|
| `google/gemini-3.6-flash` (default, builder, scout) | served via openrouter | `OPENROUTER_API_KEY` |
| `fireworks/accounts/fireworks/models/kimi-k3` (planner) | fireworks | `FIREWORKS_API_KEY` |
| `openai/gpt-5.6-terra`, `openai/gpt-5.6-luna` (reviewer, documenter) | openai | `OPENAI_API_KEY` |

**Want one key instead of three?** Delete the per-agent `model:` lines and let every agent inherit `defaults.model`. The whole roster then runs on one provider. Cheapest way to get a first green run.

One sharp edge worth knowing: `agents.validate()` checks that a model is *written* as `provider/id`, not that the provider is reachable or that its key is set. A missing key does not fail at startup. It fails when that agent runs, partway into a chain.


---

## Three principles

Everything here is built to be **observable**, **customizable**, and **reusable**. Those are not adjectives, they are the reason the parts are shaped the way they are.

**Observable.** If you cannot measure your agents, you cannot improve them. Every event goes into SQLite as it happens, so you can watch a run mid-flight, not read about it afterwards.

**Customizable.** One YAML file sets the core four for every agent: context, model, prompt, tools. Different models at different price and speed points, in the same run. It is not about which model is best anymore, it is about which model is right for that one phase.

**Reusable.** The whole thing is a skill you stamp into any repo, then bend to fit. The tests it ships are not your tests. The prompts it ships are starters. It is designed to be edited.

There are three actors here, and the design keeps them separate on purpose: **the engineer**, **the code**, and **the agents**. The trick is not running more agents. The trick is using all three at the right moment.

---

## The skill is the product

<p align="center">
  <img src="images/03_skill_stamp.svg" alt="The sssf skill directory on the left stamping config, adws, and prompt_engineering into three different target repos" width="780">
</p>

Everything lives in `.claude/skills/sssf/`. `SKILL.md` carries the hard rules and routes each request to one of nine cookbooks. `references/` holds the deep specs, `scripts/` holds the generators, and `templates/` holds what gets stamped plus the profile machinery that generates the rest — `templates/profiles/` is installer-side, and only its `gates/` modules ever land in your repo.

| What lands in your repo | Where it comes from | Tracked |
|---|---|---|
| `adws/adw_sssf_config/sssf.config.yaml` | `templates/sssf.config.yaml` | yes, it is your agent roster |
| `adws/adw_*.py` | `templates/adws/` | yes, twelve starter workflows |
| `adws/adw_modules/` | `templates/adws/adw_modules/` | yes, all low-level logic |
| `adws/adw_data/prompt_engineering/` | `templates/prompt_engineering/` | yes, **your prompts live here** |
| `adws/adw_data/harness_engineering/` | `templates/harness_engineering/` | yes, pi extensions |
| `.env.sample` | `templates/env.sample` | yes |
| `justfile` | `templates/justfile` | yes, starter recipes to run and watch |
| `adws/adw_modules/quality_blocks.py` | **generated** by the profile | yes, **your real commands** |
| `adws/adw_modules/profile_gates.py` | **generated** by the profile | yes, the stack gates that are wired |
| `adws/adw_modules/gates_<framework>.py` | `templates/profiles/gates/` | yes, one per framework the profile names |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | **generated** by the profile | yes, injected as `{{profile_overlay}}` |
| `adws/adw_data/sessions/`, `sssf.db` | created at runtime | no, gitignored |

The prompts are yours the moment they land. Edit them in `adws/adw_data/prompt_engineering/{agent}/`, never back inside the skill.

There is no DSL here. No framework to learn. It is Python, YAML, agents, and a skill, which is exactly what these models are already trained on. Staying in distribution is a feature.

---

## Stack profiles

A factory that does not know your stack cannot check your work. Out of the box `quality.py` carries `echo` placeholders that exit 0, and a test phase built on those is theatre. So the installer probes the repo and **generates** the real thing: your commands, your gates, and a prompt fragment that tells every agent what it is working on.

The mechanism is composable on purpose, because whole-stack profiles multiply. A self-contained `dotnet-svelte` package and a `dotnet-angular` package would be about seventy percent the same file — frontends and backends are a matrix, not a list. So the pieces are split three ways:

| Piece | Where | What it owns |
|---|---|---|
| **Framework** | `templates/profiles/frameworks/<name>.py` | one technology: how to find it, what to run, what to gate, what to tell the agents |
| **Profile** | `templates/profiles/<dir>/profile.yaml` | three lines naming which frameworks a stack is made of, of which only `frameworks:` is required |
| **Driver** | `templates/profiles/composite.py` | generic composition. No framework name appears anywhere in its code — a test strips the comments and docstrings and greps the rest |

A framework module exposes eight names — `NAME`, `GATE_MODULE`, `OVERLAY`, `matches`, `detect`, `blocks`, `describe`, `gate_wiring` — and **never imports another framework**. Everything shared goes through `probes.py` (finding things) and `emit.py` (writing things).

**Adding a stack is one YAML file** dropped in its own directory beside the others; `registry` globs `*/profile.yaml`, so there is nothing to register. Adding a *technology* is four things: the framework module, its gate module in `profiles/gates/`, its prompt fragment in `profiles/prompts/`, and two lines in `frameworks/__init__.py`. The acceptance test for this design adds a third framework in a 64-line module (`tests/fake_framework.py`) without changing `probes.py`, `emit.py`, `composite.py`, `registry.py`, or `facts.py` — the two registration lines in `frameworks/__init__.py` are the only shared lines it touches, and that is the whole claim.

A profiled install writes three files and stamps one more per framework:

| File | Kind | Survives a re-install |
|---|---|---|
| `adws/adw_modules/quality_blocks.py` | generated | no — rewritten by every profiled run |
| `adws/adw_modules/profile_gates.py` | generated | no — delete a line to stop enforcing that gate, and the next install puts it back |
| `adws/adw_data/prompt_engineering/profile_overlay.md` | generated | no |
| `adws/adw_modules/gates_<framework>.py` | stamped | **yes** — a gate is code you are invited to edit, so an existing copy is left alone without `--force` |

Run `install.py --doctor` any time to re-probe and see what the profile would wire now, without writing anything. It is the right thing to run after you move a project, rename a directory, or add a package.

### Fast and full

Every quality block carries a **tier**, and the tier decides when it costs you.

`fast` blocks are cheap enough to pay for on every retry, so they are what runs inside a bounded fix loop — that is `quality.run_tests(run)`. `full` blocks are the slow ones: Docker, Testcontainers, an integration suite. They run exactly once, after the loop, as final verification — that is `quality.run_quality(run)`, which runs *every* tier. Tagging a slow block `full` is how you stop paying for it on every repair round.

An empty tier **raises**. If every block you wrote is tagged `full`, `run_tests` does not quietly report green on zero commands, it stops and names the tier it found nothing in. A green loop on an empty command list, followed by a commit, is precisely the failure this subsystem exists to prevent.

Each block's output lands at `context_handoff/quality/<seq>_<name>/command.log`, and block names must be unique case-insensitively, because the name *is* that directory.

---

## The agent roster

`adws/adw_sssf_config/sssf.config.yaml` answers one question per entry: who is this agent. One agent, one prompt, one purpose.

```yaml
defaults:
  coding_agent: pi                 # pi (default) or claude_code — both run for real
  model: google/gemini-3.6-flash   # provider/model-id, a bare id can match several providers
  thinking: medium                 # off | minimal | low | medium | high | xhigh | max
  protected_files:                 # no agent may edit the machinery that grades it
    - adws/adw_modules/
    - adws/adw_sssf_config/
    - adws/adw_*.py
  data_dir: adws/adw_data

doc_policy:                        # optional; empty means the doc_policy gate never fires
  - when: "apps/api/**/Auth*.cs"   # a changed file matching this...
    require: ["docs/AUTH.md"]      # ...obliges EVERY entry here to change too

agents:
  - name: planner
    model: fireworks/accounts/fireworks/models/kimi-k3
    thinking: high                 # per-agent overrides win over defaults
    color: "#a78bfa"               # this agent's lane swatch in the trace
    purpose: Turn a request into a plan the builder can implement without asking questions.
    prompt_engineering:
      system: adws/adw_data/prompt_engineering/planner/system.md
      user: adws/adw_data/prompt_engineering/planner/user.md
    harness_engineering:
      - adws/adw_data/harness_engineering/subagents.ts   # this agent can spawn subagents
    writes:                        # the plan is all it may leave in the repo
      - specs/
```

Five starter agents ship in the box: `planner`, `builder`, `scout` (read-only recon), `reviewer`, and `documenter`. There is no tester, because running a suite is a known command and therefore code.

Every agent gets its own model, thinking level, prompts, tools, and harness. That is the core four, and it is the whole surface you tune. Give the planner a frontier model and the builder a cheap fast one. Give the scout subagents. Give the reviewer no ability to write code at all.

**`tools` is a capability list. `writes` is the boundary.** They are not the same thing, and the difference matters: `bash` runs anything, including `git checkout`, and `write` reaches any path. So "this agent changes nothing" is enforced in code, after every call, by comparing the repo before and after. Unauthorized changes are rolled back and the phase fails. A read-only agent is read-only with respect to your repo, never unable to write its own report.

Config defines who an agent **is**. The ADW call site defines how it is **used**. That split is what lets one agent serve many different calls. **ADW scripts never name a model, they name an agent.**

---

## Phases: three lanes, one primitive

<p align="center">
  <img src="images/04_phase_lanes.svg" alt="Swim lanes for engineer, git, planner, builder, and reviewer with phase blocks placed on a time axis and one dashed queued block" width="780">
</p>

Every run is a sequence of phases, and every phase is the same context manager no matter who owns it.

```python
REQUIRED_AGENTS = ["planner", "builder", "reviewer"]   # names, never models

cfg = agents.load_config(config)
agents.validate(cfg, REQUIRED_AGENTS)   # a missing agent fails before anything spawns
run = session.ensure(cfg, adw_id)       # pin-or-create the session

with run.phase(PhaseParams(name="plan", kind="agent", owner="planner",
                           description="Turn the request into an implementable plan")) as ph:
    plan = ph.call(AgentCall(output_type=PlanOutput, prompt=prompt,
                             gates=[gates.artifacts_exist, gates.files_non_empty]))

with run.phase(PhaseParams(name="commit", kind="code", owner="git",
                           description="Commit the working tree")) as ph:
    message = build.commit_message or f"sssf({run.adw_id}): {build.summary}"
    ph.log(sha=git_helper.commit_all(message), message=message)

return run.finish(accepted=review.approved, reason="the reviewer never approved")
```

Three kinds, three swim lanes. **engineer** is the human lane. **agent** is `ph.call(...)`: prompt in, typed envelope out, gates verified. **code** is a deterministic step that stands on its own, like a commit or a migration, and it is never buried inside an agent phase, so the trace shows exactly when code ran and when an agent was working.

That commit phase is the whole pattern in miniature. The builder proposes the message as a field on its envelope. Code decides whether to use it, falls back when it is empty, and performs the write. The agent never runs `git commit` itself.

**Success must be earned.** Every phase defaults to `fail`. A clean exit flips it, and an agent phase also needs its envelope to parse and every gate to come back green. `run.finish(accepted=...)` adds the second question, because phases passing is not the same as the run being acceptable: a test phase that ran a red suite did its job perfectly. One call settles the exit code, the session status, and the banner together, so they cannot disagree.

---

## Envelopes and gates

<p align="center">
  <img src="images/05_envelope_gates.svg" alt="An agent's final JSON parsed against its output type, checked by gates, with violations looping back into the same session as a correction" width="780">
</p>

An agent has exactly two output channels: reference files written into `context_handoff/`, and a final valid-JSON response parsed against the output type the call declared. Code persists that response as `envelope.json`, records it, and injects it into the next agent's prompt. Context transfers in code, not in conversation.

```python
class EnvelopeBase(BaseModel):
    status: Literal["success", "fail"]
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    notes_for_next_agent: str = ""

class BuildOutput(EnvelopeBase):
    changed_files: list[str] = Field(default_factory=list)
    commit_message: str = ""        # consumed by the git commit phase
```

Determinism is wired into every step. Agents must return a specific structure, every time. If it does not parse, they get asked again until it does.

Gates verify claims, never predictions. Nobody knows which files an agent will touch before it finishes, so gates run **after** the fact against the envelope's own declarations: `artifacts_exist`, `files_non_empty`, `json_parses`, `diff_matches_claims`, `verdict_consistent`, `tests_pass(...)`. A gate is a callable with the signature `gate(envelope, run) -> GateReport`, one `check(item, ok, note)` per thing it examined, so a green gate tells you *what* it verified.

Two more are in `gates.py` but are not written there. **`doc_policy`** is a function whose *rules* are configured rather than coded: each rule in `sssf.config.yaml` says that a change matching one glob requires changes matching every glob it names, so "touching auth means updating `docs/AUTH.md`" is four lines of YAML instead of a new function. **`profile_gates()`** splats in whatever your [stack profile](#stack-profiles) generated — the EF migration triad, a CSP check, an `.env.example` sync. Every `BuildOutput` phase in every shipped ADW runs `[diff_matches_claims, doc_policy, *profile_gates()]`, and a new ADW should too.

When JSON does not parse or a gate returns violations, **nothing restarts**. The harness re-prompts the same session with a correction naming exactly what was wrong, and the context window stays intact. Pi treats `--session-id` as create-or-continue, so running an agent and continuing it are the same call. A cold restart throws away everything the agent learned. A correction costs one message.

The output contract lives in three places and they are one thing: the type in `data_types.py`, the JSON example in that agent's `user.md` `## Report` section, and `output_type=` at the call site. **Change one, change all three in the same edit.**

---

## The trace

<p align="center">
  <img src="images/06_trace_path.svg" alt="Running agents to tracer.py to a WAL SQLite db with seven tables, read by a cursor poll query, with no websocket and no ingest endpoint" width="780">
</p>

One data path, no exceptions: **agents write to SQLite, readers poll SQLite.** Each backend tails its own coding agent's JSONL stdout line by line — `agent_pi.py` for pi, `agent_cc.py` for Claude Code — and the tracer inserts each event while the agent is still working, so tool calls are visible mid-run instead of batched at the end.

Ten event types land across seven tables: `sessions`, `phases`, `events`, `envelopes`, `gate_results`, `agent_sessions`, and `processes` (adw_id to pid, so a stuck run can be found and stopped). Every event logs against both its `adw_id` and its `phase_id`, and `parent_id` nests spans, so an agent phase expands into its own tool calls.

Pi announces a tool call across three raw events, so the interface folds them into exactly **one** `tool_call` row per real call. Each row is named the way you would read it aloud (`bash: ls -la src`) and carries `{tool, tool_call_id, args, result_snippet, ok, duration_ms, agent}`.

Code phases use the same row type. Every quality block emits one `tool_call` named `quality:<block>`, carrying `{area, operation, cwd, tier, command, returncode, passed, output_artifact}` instead — same table, different payload, so a consumer reading `tool_call` rows has to branch on which shape it got.

```sql
select * from events where adw_id = ? and rowid > ? order by rowid limit 500;
```

That one cursor query is the entire transport. Live view and full history are the same query at different cadence, which is why there is no ingest endpoint, no WebSocket, no backfill, and no separate replay path. Every connection opens WAL, so reads never block the running writers.

Files stay the raw record (`raw_output.jsonl`, `envelope.json`, `agent_map.json`). The db is the queryable mirror. Losing it loses nothing you cannot rebuild.

The skill ships a read-only UI for this db at `.claude/skills/sssf/apps/visualizer/`: Vue and Vite on Bun, with sessions, a trace waterfall, and per-phase tool-call detail. Two ports — the API on **4600**, the Vite dev server on **4601**. Open `http://localhost:4601`.

```bash
cd .claude/skills/sssf/apps/visualizer && bun install
SSSF_DB=/abs/path/to/your-repo/adws/adw_data/sssf.db bun run server/index.ts &
bunx vite
```

It resolves its target through `--db`, then `SSSF_DB`, then `<cwd>/adws/adw_data/sssf.db`, so one instance can point at any stamped repo. Pass the db explicitly, because the server runs from the app dir.

---

## What is in this branch

```
super-simple-software-factory/          # the deployable factory, and nothing else
└── .claude/skills/sssf/
    ├── SKILL.md                        # hard rules + request routing table
    ├── cookbooks/                      # 9 orchestrator playbooks, loaded lazily
    ├── references/                     # config / handoff / observability specs
    ├── scripts/                        # install.py, make_config.py, make_adw.py
    ├── apps/visualizer/                # the read-only trace UI (Vue + Vite on Bun)
    └── templates/                      # what install.py stamps, plus what generates the rest
        ├── sssf.config.yaml            # the starter roster
        ├── env.sample                  # lands as .env.sample
        ├── justfile                    # starter recipes
        ├── prompt_engineering/{agent}/ # system.md + user.md per agent
        ├── harness_engineering/        # pi extensions
        ├── adws/
        │   ├── adw_*.py                # the twelve starter workflows
        │   └── adw_modules/            # ALL low-level logic, ADW scripts stay thin
        └── profiles/                   # INSTALLER-SIDE: none of this is stamped...
            ├── facts.py                #   the typed vocabulary a probe reports in
            ├── probes.py               #   shared "how do I find it" helpers
            ├── emit.py                 #   shared "how do I write it" helpers
            ├── composite.py            #   the generic driver, no framework names in code
            ├── registry.py             #   globs */profile.yaml, so nothing registers
            ├── frameworks/*.py         #   one module per technology
            ├── prompts/*.md            #   one overlay fragment per technology
            ├── gates/gates_*.py        #   ...except these, stamped per framework
            └── dotnet_svelte/profile.yaml
```

The skill is also what an agent reads to *operate* the factory. `SKILL.md` is the central idea, and the cookbooks are lazily loaded recipes it pulls in one at a time: set up the factory, create an ADW, modify a chain, add an agent, run and monitor. If you can teach an agent to do something, teach it, then go build the thing it cannot.

---

## The twelve starter workflows

Every ADW takes the same shape:

```bash
uv run adws/adw_*.py "<prompt or path/to/prompt.md>" [--config adws/adw_sssf_config/sssf.config.yaml] [--adw-id a1b2c3d4]
```

| ADW | Chain | Reach for it when |
|---|---|---|
| `adw_prompt` | engineer to \<agent\> | one agent, one prompt, `--agent NAME` picks who |
| `adw_scout` | engineer to scout | read-only recon, nothing changes |
| `adw_plan` | engineer to planner | you want the spec before any code |
| `adw_build` | engineer to builder | the plan already exists |
| `adw_quality` | engineer to code(quality) | verify the repo with no agents at all — every block, both tiers |
| `adw_plan_build` | planner, builder, git(commit) | small, well-understood work |
| `adw_build_test` | builder, code(test), bounded fix loop | there is a fast-tier suite to satisfy |
| `adw_build_review` | builder, reviewer, bounded revise loop | "is this what was asked for" matters more than "does it run" |
| `adw_plan_build_test` | plan, build, code(test), git(commit) | the standard chain |
| `adw_plan_build_test_quality` | same, plus one every-tier pass after the loop | the slow checks (Docker, integration) have to pass before the commit |
| `adw_document` | code(git diff), documenter | write up what just shipped |
| `adw_simple_sdlc` | plan, build, test, review, document | the work is real and its shape is not obvious |

`adw_simple_sdlc` lands three commits from three authors. The plan, the code, and the write-up each get their own, and each message is the words of the agent that produced it.

`--adw-id` is optional everywhere. Omit it and a fresh id is minted and printed. Supply it and the run joins that session: same dirs, same `context_handoff/`, and each agent **resumes its existing context window** through `agent_map.json` instead of starting cold. That is how you chain workflows.

```bash
uv run adws/adw_plan.py "add a /health endpoint"              # prints adw_id a1b2c3d4
uv run adws/adw_build_test.py "implement the plan" --adw-id a1b2c3d4
```

Watch a run with the trace db directly — `adw_trace.py` reads it with the stdlib `sqlite3` module, so there is no `sqlite3` CLI to install:

```bash
uv run adws/adw_trace.py sessions --limit 10
uv run adws/adw_trace.py phases a1b2c3d4
uv run adws/adw_trace.py processes
```

Reads never block a running workflow, the db is WAL. `install.py` stamps a `justfile` wrapping all of the above, so in a fresh repo these are `just sessions`, `just phases <adw_id>`, `just tail <adw_id>`, and `just procs <adw_id>`.

---

## Where it can still fail

Honest edges, because knowing them is cheaper than discovering them.

| Failure | What actually happens | What to do |
|---|---|---|
| The test phase reports green on a fresh install | Only without a matching profile. `install.py` probes the repo and generates `adws/adw_modules/quality_blocks.py` with its real commands; with no profile match, those blocks stay `quality.py`'s `echo` placeholders that exit 0 | Run `install.py --doctor` to see what was wired. If no profile matched, write the specs into `quality_blocks.py` by hand before trusting `adw_build_test`, `adw_plan_build_test`, or `adw_simple_sdlc` |
| A bare model pattern | On `pi`, the same model sits under several providers, so `gemini-3.6-flash` matches three catalog entries and `agents.validate()` refuses to spawn. On `claude_code` a bare pattern fails the same validation for a simpler reason — there is no catalog, so anything without a `/` is rejected outright | Always write `provider/model-id` |
| `just` is not installed | The stamped `justfile` is a convenience wrapper, nothing depends on it | Every recipe is a one-line `uv run` command. Open the justfile and run the line yourself |
| A coding agent hangs silently | No events, no tokens, an empty `raw_output.jsonl`. The trace goes quiet rather than red | Query `processes` for what is alive and kill it children-first. A killed run finalizes its own trace to `fail` |
| The synced triad drifts | Type, `## Report` example, and `output_type=` disagree, so every call burns correction rounds | Grep the type name and fix all three in one edit |
| Gates pass, output is bad | Gates check what a predicate can check, not plan quality or code taste | Run the `reviewer`, or read it yourself |
| An agent edits something it should not | Detected and rolled back after the call, and the phase fails | Expected. Widen that agent's `writes` if the change was legitimate |
| Commit phase has nothing to commit | `commit_all` raises if the cwd is not a git repo or nothing changed | `git init` with one commit first. A no-op build fails the phase rather than committing nothing |
| `install.py --force` | Overwrites **all** stamped files, config and prompts included | Commit before you force |
| The banner prints `?` instead of `▶` and box-drawing | A cp1252 Windows console cannot encode them. stdout runs with `errors="replace"`, so they degrade rather than raising — this used to kill the run mid-phase and leave the session stuck at `running` | Cosmetic. Set `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`, or use a UTF-8 code page, if you want the real glyphs. The trace is UTF-8 either way, so the visualizer always shows them |
| Installing a profile over an older stamped tree | Refused, non-zero, naming the stale module. `stamp()` skips existing files, so without this check the old runtime would sit under new generated files and enforce nothing | Commit, then re-run with `--force`. Diff your prompts afterwards — the check does not cover them |
| `RuntimeError: no quality blocks in tier(s) ['fast']` | Every block you wrote is tagged `full`, so the fix loop had nothing to run. It refuses rather than reporting green on an empty list | Tag at least one cheap block `fast`, or call `run_quality` instead of `run_tests` |
| A quality block fails and the message is too short | The full stdout and stderr are on disk, not in the phase log | Read `context_handoff/quality/<seq>_<name>/command.log` in that session's directory |
| A `claude_code` agent declares `harness_engineering` | Rejected at validation, before anything spawns | Extensions are pi-only. Remove the key, or run that agent on `coding_agent: pi` |

Also missing on purpose, so you know what to add: this runs on your current branch. For real work you want a branch per run, a sandbox around the agent, and a merge step at the end.

**Is this overkill for a one-off feature?** Yes. Prompt an agent and move on. This earns its keep when the same workflow runs a hundred times, when validation is the only thing standing between you and a bad merge, and when you need the thousandth run to look like the first.

---

## Built to be Observed, Customized, and Reused

This is a starting point, not a product. Nothing here is meant to survive contact with your codebase unchanged.

The tests it ships are not your tests. The prompts it ships describe a demo app, not your domain. The roster names the models that were good the week it was written. All of that is supposed to be replaced, and the whole thing is shaped so that replacing it is a small edit in an obvious file instead of a rewrite. That is what those three properties are for. **Observable** so you can see which part is actually costing you. **Customizable** so the fix is one file. **Reusable** so you do it once and stamp it everywhere.

Where to start, roughly in the order that pays off fastest:

| Change | File | Why |
|---|---|---|
| Your real commands | `adws/adw_modules/quality_blocks.py` | Generated from a [stack profile](#stack-profiles) at install time (`install.py --profile <name>`). Plain Python: open it and correct anything the probe got wrong — but the file says `GENERATED` at the top and means it, so a hand edit is gone after the next profiled install. Teach the framework module instead if you want the fix to stick. No matching profile means `quality.py` falls back to `echo` placeholders, and your test phase is theater until you fix that |
| Your prompts | `adws/adw_data/prompt_engineering/{agent}/` | Where your standards live: what a good plan looks like, what a review has to catch |
| Your roster | `adws/adw_sssf_config/sssf.config.yaml` | Models, thinking levels, tools, what each agent is allowed to write, and the `doc_policy` rules |
| Your chains | `adws/adw_*.py` | Copy the closest workflow and edit the phase list. They are 40 to 180 lines on purpose |
| Your definition of done | `adws/adw_modules/gates.py`, `gates_<framework>.py`, `profile_gates.py`, `doc_policy:` | Four doors into one idea. A hand-written gate is one function in `gates.py`. A stack gate lives in `gates_<framework>.py` and **survives re-install**. `profile_gates.py` is the generated wiring — delete a line to stop enforcing one, and know it comes back. `doc_policy:` in the roster is the one you configure instead of code |
| Your stack | `templates/profiles/` in the skill | A new stack is one `profile.yaml` naming frameworks that already exist. A new technology is one framework module, its gate and prompt files, and two registration lines in `frameworks/__init__.py`. This is where a fix goes if you want it in every repo you stamp |
| Your agent capabilities | `adws/adw_data/harness_engineering/` | Pi extensions, a different set per agent if that is what the job needs |

And what it deliberately does not do. It runs on your current branch. There is no sandbox, no branch per run, no merge step, no cloud, and no human-in-the-loop approval phase. Those are the obvious next things to build. They are left out so the core stays small enough to read in one sitting, which is the only reason you would trust it enough to change it.

So take it. Fork it, strip the parts you do not need, rename the agents, throw out half the workflows, and roll what is left into the factory your product actually needs. The specific chains in here matter far less than the shape: code owns the loop, agents own the phases, and every run leaves a trace you can go read.

---

## See it in a real repo

The [`example` branch](../../tree/example) is this same skill with the factory already stamped in: a populated `adws/`, a `justfile`, a demo app the factory planned, built, tested, reviewed, and documented, and the specs, docs, and traces those runs produced.

```bash
git clone <this-repo> sssf && cd sssf
git checkout example
```

---

## License

MIT, see [`LICENSE`](LICENSE).

---

## Master Agentic Coding

<p align="center">
  <img src="images/08_rise_with_the_ceiling.svg" alt="Vibe coding sits inside a narrow band with a short arrow of headroom above it, agentic engineering rises far above that band with a tall one" width="850">
</p>

Vibe coding is not knowing how your system works, and not looking. Agentic engineering is knowing how your system works so well that you do not have to look.

Master agentic coding by gaining a deeper understanding of the foundational units of the software factory.

Learn tactical agentic coding patterns with [Tactical Agentic Coding](https://agenticengineer.com/tactical-agentic-coding?y=sssf).

Follow the [IndyDevDan YouTube channel](https://www.youtube.com/@indydevdan) to improve your agentic coding advantage.

---

Stay Focused and Keep Building

- IndyDevDan
