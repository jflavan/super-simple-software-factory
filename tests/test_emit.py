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


# ── script blocks ────────────────────────────────────────────────────────────

def test_a_script_becomes_a_block_in_its_own_directory():
    frontends = [Frontend(directory="apps/web", package_manager="npm",
                          scripts=["check", "build"])]
    blocks, unresolved = emit.script_blocks(frontends, _repo(), SCRIPTS)
    by_name = {b.name: b for b in blocks}

    assert by_name["check-web"].argv == ["npm", "run", "check"]
    assert by_name["check-web"].cwd == "apps/web"
    assert by_name["check-web"].area == "frontend"
    assert by_name["check-web"].operation == "typecheck"
    assert "test-web" not in by_name          # no `test` script declared
    assert unresolved == []


def test_the_package_manager_is_honoured():
    frontends = [Frontend(directory="web", package_manager="pnpm", scripts=["build"])]
    blocks, _ = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks[0].argv == ["pnpm", "run", "build"]


def test_a_recipe_beats_the_package_manager_and_runs_from_the_root():
    repo = _repo(task_runner="just", recipes=["check-web"])
    frontends = [Frontend(directory="apps/web", scripts=["check"])]
    block = emit.script_blocks(frontends, repo, SCRIPTS)[0][0]
    assert block.argv == ["just", "check-web"]
    assert block.cwd == "."


def test_a_package_declaring_none_of_the_scripts_is_reported_unresolved():
    frontends = [Frontend(directory="apps/web", scripts=["dev"])]
    blocks, unresolved = emit.script_blocks(frontends, _repo(), SCRIPTS)
    assert blocks == []
    assert "apps/web" in unresolved[0]


def test_colliding_package_names_produce_unique_block_names():
    frontends = [Frontend(directory="apps/web", scripts=["build"]),
                 Frontend(directory="packages/web", scripts=["build"])]
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
    frontends = [Frontend(directory="apps/web", scripts=["build"]),
                 Frontend(directory="packages/web", scripts=["build"])]

    blocks, _ = emit.script_blocks(frontends, repo, SCRIPTS)

    assert len({(tuple(b.argv), b.cwd) for b in blocks}) == 2
    assert {b.cwd for b in blocks} == {"apps/web", "packages/web"}
    # The point of the test: the ambiguous recipe is borrowed by neither.
    assert all("build-web" not in block.argv for block in blocks)


# ── rendering ────────────────────────────────────────────────────────────────

def test_a_rendered_blocks_module_is_valid_python_that_builds_specs():
    from adw_modules.data_types import QualityCheckSpec
    facts = _repo(task_runner="just")
    blocks = [QualityBlock(name="t", area="backend", operation="build",
                           argv=["dotnet", "test", "a/B.csproj"], tier="full",
                           timeout_seconds=1800, source="project role unit-tests")]

    text = emit.render_blocks_module(facts, blocks)

    ast.parse(text)
    assert "GENERATED" in text
    assert "from .data_types import QualityCheckSpec" in text
    namespace = {"QualityCheckSpec": QualityCheckSpec}
    exec(text.split("from .data_types import QualityCheckSpec", 1)[1], namespace)
    assert namespace["BLOCKS"][0].tier == "full"
    assert namespace["BLOCKS"][0].timeout_seconds == 1800


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


def test_writing_records_the_path_it_wrote(tmp_path):
    written = []
    emit.write_file(tmp_path, "adws/adw_modules/x.py", "BLOCKS = []\n", written)
    assert (tmp_path / "adws" / "adw_modules" / "x.py").read_text() == "BLOCKS = []\n"
    assert len(written) == 1
