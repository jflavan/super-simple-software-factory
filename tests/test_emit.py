"""Emitters: shared by every framework, owned by none."""

import ast

from profiles import emit
from profiles.facts import Frontend, GateWiring, ProfileFacts, QualityBlock

SCRIPTS = [
    ("check", ["check-{name}", "check-frontend"], "typecheck", "check"),
    ("test", ["test-{name}"], "test", "test"),
    ("build", ["build-{name}"], "build", "build"),
]


def _repo(**kwargs):
    return ProfileFacts(profile="p", repo_root=".", **kwargs)


# ── recipe preference ────────────────────────────────────────────────────────

def test_no_runner_means_no_recipe():
    argv, source = emit.recipe(_repo(), ["test-unit"])
    assert argv == []
    assert source == ""


def test_the_first_candidate_the_runner_knows_wins():
    repo = _repo(task_runner="just", recipes=["build", "test-api", "test-unit"])
    argv, source = emit.recipe(repo, ["test-unit", "test-api"])
    assert argv == ["just", "test-unit"]
    assert "test-unit" in source


def test_a_candidate_the_runner_does_not_know_is_skipped():
    repo = _repo(task_runner="just", recipes=["test-api"])
    assert emit.recipe(repo, ["test-unit", "test-api"])[0] == ["just", "test-api"]


def test_the_name_placeholder_is_substituted():
    repo = _repo(task_runner="just", recipes=["check-web"])
    assert emit.recipe(repo, ["check-{name}"], name="web")[0] == ["just", "check-web"]


# ── labels ───────────────────────────────────────────────────────────────────

def test_a_unique_directory_name_is_the_label():
    assert emit.labels(["apps/web", "apps/admin"]) == {"apps/web": "web",
                                                       "apps/admin": "admin"}


def test_colliding_names_fall_back_to_the_full_path():
    assert emit.labels(["apps/web", "packages/web"]) == {
        "apps/web": "apps-web", "packages/web": "packages-web"}


def test_the_repo_root_is_labelled_root():
    assert emit.labels(["."]) == {".": "root"}


def test_a_transform_collision_that_survives_flattening_gets_an_index():
    """`a/b/web` and `a-b/web` both flatten to `a-b-web` - the transform itself collides."""
    names = emit.labels(["a/b/web", "a-b/web"])
    assert len(set(names.values())) == 2
    assert names["a/b/web"] != names["a-b/web"]


# ── script blocks ────────────────────────────────────────────────────────────

def test_a_script_becomes_a_block_in_its_own_directory():
    frontends = [Frontend(directory="apps/web", package_manager="npm",
                          scripts={"check": "svelte-check", "build": "vite build"})]
    blocks, unresolved = emit.script_blocks(frontends, _repo(), SCRIPTS)
    by_name = {b.name: b for b in blocks}

    assert by_name["check-web"].argv == ["npm", "run", "check"]
    assert by_name["check-web"].cwd == "apps/web"
    assert by_name["check-web"].area == "frontend"
    assert by_name["check-web"].operation == "typecheck"
    assert "test-web" not in by_name          # no `test` script declared
    assert unresolved == []


def test_the_package_manager_is_honoured():
    frontends = [Frontend(directory="web", package_manager="pnpm",
                          scripts={"build": "vite build"})]
    blocks, _ = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks[0].argv == ["pnpm", "run", "build"]


def test_a_recipe_beats_the_package_manager_and_runs_from_the_root():
    repo = _repo(task_runner="just", recipes=["check-web"])
    frontends = [Frontend(directory="apps/web", scripts={"check": "svelte-check"})]
    block = emit.script_blocks(frontends, repo, SCRIPTS)[0][0]
    assert block.argv == ["just", "check-web"]
    assert block.cwd == "."


def test_a_package_declaring_none_of_the_scripts_is_reported_unresolved():
    frontends = [Frontend(directory="apps/web", scripts={"dev": "vite dev"})]
    blocks, unresolved = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks == []
    assert "apps/web" in unresolved[0]


def test_colliding_package_names_produce_unique_block_names():
    frontends = [Frontend(directory="apps/web", scripts={"build": "vite build"}),
                 Frontend(directory="packages/web", scripts={"build": "vite build"})]
    names = [b.name for b in emit.script_blocks(frontends, _repo(), SCRIPTS)[0]]
    assert sorted(names) == ["build-apps-web", "build-packages-web"]


def test_colliding_packages_do_not_share_one_recipe():
    """Unique names are not enough if both run the SAME check.

    With a runner declaring `build-web`, a naive per-package label resolves it
    twice: two differently-named blocks, one identical command, one package
    actually checked. The duplicate-name guard cannot see it, because the names
    differ.

    Correct behaviour is to decline the ambiguous recipe — neither
    `build-apps-web` nor `build-packages-web` is declared — and fall through to
    per-package commands. Those argvs are then IDENTICAL, which is exactly what
    `cwd` exists for, so the pair is what has to be distinct rather than the
    argv alone.
    """
    repo = _repo(task_runner="just", recipes=["build-web"])
    frontends = [Frontend(directory="apps/web", scripts={"build": "vite build"}),
                 Frontend(directory="packages/web", scripts={"build": "vite build"})]

    blocks, _ = emit.script_blocks(frontends, repo, SCRIPTS)

    assert len({(tuple(b.argv), b.cwd) for b in blocks}) == 2
    assert {b.cwd for b in blocks} == {"apps/web", "packages/web"}
    # The point of the test: the ambiguous recipe is borrowed by neither.
    assert all("build-web" not in block.argv for block in blocks)


def test_the_area_default_can_be_overridden_for_a_non_frontend_package():
    frontends = [Frontend(directory="apps/api", scripts={"build": "vite build"})]
    blocks, _ = emit.script_blocks(frontends, _repo(), SCRIPTS, area="backend")
    assert blocks[0].area == "backend"


# ── a broad recipe covers every frontend at once ────────────────────────────

def test_a_repo_wide_recipe_covering_several_packages_emits_one_block():
    """`check-frontend` names no package - it is "every package", by construction.

    Emitting it once per declaring package would run the same command twice,
    into two artifact directories holding one command's output.
    """
    repo = _repo(task_runner="just", recipes=["check-frontend"])
    frontends = [Frontend(directory="apps/web", scripts={"check": "svelte-check"}),
                 Frontend(directory="apps/admin", scripts={"check": "svelte-check"})]

    blocks, unresolved = emit.script_blocks(frontends, repo, SCRIPTS)

    assert [b.name for b in blocks] == ["check-frontend"]
    assert blocks[0].argv == ["just", "check-frontend"]
    assert blocks[0].cwd == "."
    assert "covers 2 package(s)" in blocks[0].source
    assert unresolved == []


def test_a_single_frontend_still_gets_a_named_block_with_a_shared_recipe():
    """A per-package command and a repo-wide recipe are equivalent for one
    package - the specific name is more useful, so it wins."""
    repo = _repo(task_runner="just", recipes=["check-frontend"])
    frontends = [Frontend(directory="apps/web", scripts={"check": "svelte-check"})]

    blocks, _ = emit.script_blocks(frontends, repo, SCRIPTS)

    assert blocks[0].name == "check-web"
    assert blocks[0].argv == ["just", "check-frontend"]


def test_a_repo_wide_recipe_does_not_swallow_a_package_declaring_nothing():
    """The 'declares none of the scripts' note must still fire after the
    restructure that lets a shared recipe cover several packages at once."""
    repo = _repo(task_runner="just", recipes=["check-frontend"])
    frontends = [Frontend(directory="apps/web", scripts={"check": "svelte-check"}),
                 Frontend(directory="apps/silent", scripts={"dev": "vite dev"})]

    blocks, unresolved = emit.script_blocks(frontends, repo, SCRIPTS)

    assert [b.name for b in blocks] == ["check-web"]
    assert "apps/silent" in unresolved[0]


# ── tier follows the command, not the script name ───────────────────────────

def test_a_slow_command_is_tagged_the_full_tier():
    frontends = [Frontend(directory="apps/web", scripts={"test": "playwright test"})]
    blocks, _ = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks[0].tier == "full"


def test_a_fast_command_stays_in_the_fast_tier():
    frontends = [Frontend(directory="apps/web", scripts={"test": "vitest run"})]
    blocks, _ = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks[0].tier == "fast"


# ── rendering ────────────────────────────────────────────────────────────────

def test_a_rendered_blocks_module_is_valid_python_that_builds_specs():
    from adw_modules.data_types import QualityCheckSpec
    facts = _repo(task_runner="just")
    blocks = [QualityBlock(name="t", area="backend", operation="build",
                           argv=["dotnet", "test", "a/B.csproj"], tier="full",
                           timeout_seconds=1800, source="project role unit-tests"),
              QualityBlock(name="check-web", area="frontend", operation="typecheck",
                           argv=["npm", "run", "check"], cwd="apps/web",
                           tier="fast", timeout_seconds=600,
                           source="npm script 'check'")]

    text = emit.render_blocks_module(facts, blocks)

    ast.parse(text)
    assert "GENERATED" in text
    assert "from .data_types import QualityCheckSpec" in text
    namespace = {"QualityCheckSpec": QualityCheckSpec}
    exec(text.split("from .data_types import QualityCheckSpec", 1)[1], namespace)
    assert namespace["BLOCKS"] == [
        QualityCheckSpec(name="t", area="backend", operation="build",
                         argv=["dotnet", "test", "a/B.csproj"], cwd=".",
                         tier="full", timeout_seconds=1800),
        QualityCheckSpec(name="check-web", area="frontend", operation="typecheck",
                         argv=["npm", "run", "check"], cwd="apps/web",
                         tier="fast", timeout_seconds=600),
    ]


def test_a_rendered_gates_module_imports_only_what_it_wires():
    facts = _repo()
    wirings = [GateWiring(module="gates_dotnet", name="ef_migration_triad",
                          call="ef_migration_triad"),
               GateWiring(module="gates_sveltekit", name="env_example_sync",
                          call="env_example_sync([('a', 'a/.env.example')], ['PUBLIC_'])")]

    text = emit.render_gates_module(facts, wirings)

    ast.parse(text)
    assert "from .gates_dotnet import ef_migration_triad" in text
    assert "from .gates_sveltekit import env_example_sync" in text
    assert "sveltekit_csp" not in text
    assert "PROFILE_GATES" in text


def test_two_gates_from_one_module_share_an_import_line():
    facts = _repo()
    wirings = [GateWiring(module="gates_sveltekit", name="env_example_sync",
                          call="env_example_sync([], [])"),
               GateWiring(module="gates_sveltekit", name="sveltekit_csp",
                          call="sveltekit_csp([])")]
    text = emit.render_gates_module(facts, wirings)
    assert text.count("from .gates_sveltekit import") == 1
    assert "env_example_sync, sveltekit_csp" in text


def test_two_wirings_sharing_a_module_and_name_still_get_two_entries():
    """Two DIFFERENT calls behind the same imported name - dedupe is the import, not the entry."""
    facts = _repo()
    wirings = [GateWiring(module="gates_dotnet", name="ef_migration_triad",
                          call="ef_migration_triad(['a/A.csproj'])"),
               GateWiring(module="gates_dotnet", name="ef_migration_triad",
                          call="ef_migration_triad(['b/B.csproj'])")]
    text = emit.render_gates_module(facts, wirings)
    assert text.count("from .gates_dotnet import") == 1
    assert text.count("ef_migration_triad(['a/A.csproj'])") == 1
    assert text.count("ef_migration_triad(['b/B.csproj'])") == 1


# ── summary ──────────────────────────────────────────────────────────────────

def test_the_summary_lines_reach_the_generated_docstring():
    facts = _repo(task_runner="just", default_branch="trunk",
                  conventions=["CLAUDE.md"])
    text = emit.render_blocks_module(facts, [], summary=["  solution: A.sln"])
    assert "  solution: A.sln" in text
    assert "task runner: just" in text
    assert "default branch: trunk" in text
    assert "conventions: CLAUDE.md" in text


def test_a_hostile_discovered_string_still_renders_an_importable_module():
    """A package.json script key and a branch name are both arbitrary text."""
    facts = _repo(default_branch='a"""b')
    text = emit.render_blocks_module(
        facts, [], summary=['  frontend: web (scripts: build:\\Unit, """)'])
    ast.parse(text)          # would raise before the fix
    assert '"""' not in text.split('"""', 2)[1]     # docstring body is clean


def test_writing_records_the_path_it_wrote(tmp_path):
    written = []
    emit.write_file(tmp_path, "adws/adw_modules/x.py", "BLOCKS = []\n", written)
    assert (tmp_path / "adws" / "adw_modules" / "x.py").read_text() == "BLOCKS = []\n"
    assert len(written) == 1


def test_writing_overwrites_an_existing_file(tmp_path):
    written = []
    emit.write_file(tmp_path, "x.py", "BLOCKS = [1]\n", written)
    emit.write_file(tmp_path, "x.py", "BLOCKS = [2]\n", written)
    assert (tmp_path / "x.py").read_text() == "BLOCKS = [2]\n"


def test_writing_round_trips_non_ascii_content(tmp_path):
    written = []
    text = "# café — emdash\nBLOCKS = []\n"
    emit.write_file(tmp_path, "x.py", text, written)
    assert (tmp_path / "x.py").read_text(encoding="utf-8") == text


def test_writing_uses_lf_newlines_even_on_windows(tmp_path):
    written = []
    emit.write_file(tmp_path, "x.py", "x = 1\ny = 2\n", written)
    raw = (tmp_path / "x.py").read_bytes()
    assert b"\r\n" not in raw
