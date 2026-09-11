"""ef_migration_triad: a pure function over a changeset."""

from types import SimpleNamespace

from adw_modules.data_types import BuildOutput
from adw_modules.gates_dotnet import ef_migration_triad

MIGRATION = "apps/api/Api/Migrations/20260911120000_AddThing.cs"
DESIGNER = "apps/api/Api/Migrations/20260911120000_AddThing.Designer.cs"
SNAPSHOT = "apps/api/Api/Migrations/AppDbContextModelSnapshot.cs"


def _run(tmp_path):
    return SimpleNamespace(repo_root=str(tmp_path), cfg=SimpleNamespace())


def _touch(tmp_path, *relatives):
    for relative in relatives:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("// generated\n")


def _envelope(files):
    return BuildOutput(status="success", changed_files=files)


def test_a_change_with_no_migration_is_silent(tmp_path):
    report = ef_migration_triad(_envelope(["apps/api/Api/Program.cs"]), _run(tmp_path))
    assert report.passed
    assert report.checks == []


def test_a_complete_triad_passes(tmp_path):
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, DESIGNER, SNAPSHOT]), _run(tmp_path))
    assert report.passed
    assert len(report.checks) == 2


def test_a_migration_with_no_designer_fails(tmp_path):
    _touch(tmp_path, MIGRATION, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, SNAPSHOT]), _run(tmp_path))
    assert not report.passed
    assert "Designer.cs" in report.violations[0]


def test_a_migration_with_an_unchanged_snapshot_fails(tmp_path):
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, DESIGNER]), _run(tmp_path))
    assert not report.passed
    assert "snapshot" in report.violations[0].lower()


def test_the_designer_may_be_on_disk_without_being_in_the_change(tmp_path):
    """Editing an existing migration does not rewrite its Designer file."""
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    assert ef_migration_triad(_envelope([MIGRATION, SNAPSHOT]), _run(tmp_path)).passed


def test_a_designer_file_is_not_itself_treated_as_a_migration(tmp_path):
    _touch(tmp_path, DESIGNER)
    assert ef_migration_triad(_envelope([DESIGNER]), _run(tmp_path)).checks == []


def test_a_snapshot_file_is_not_itself_treated_as_a_migration(tmp_path):
    _touch(tmp_path, SNAPSHOT)
    assert ef_migration_triad(_envelope([SNAPSHOT]), _run(tmp_path)).checks == []


def test_a_non_cs_file_in_a_migrations_folder_is_ignored(tmp_path):
    other = "apps/api/Api/Migrations/README.md"
    _touch(tmp_path, other)
    assert ef_migration_triad(_envelope([other]), _run(tmp_path)).checks == []


def test_the_migrations_folder_may_live_anywhere(tmp_path):
    """EF Core's convention is the folder NAME, not a location in the tree."""
    elsewhere = "src/Data/Migrations/20260101_Init.cs"
    snapshot = "src/Data/Migrations/CtxModelSnapshot.cs"
    _touch(tmp_path, elsewhere, snapshot)
    report = ef_migration_triad(_envelope([elsewhere, snapshot]), _run(tmp_path))
    assert len(report.checks) == 2
    assert not report.passed          # no Designer.cs beside it


def test_two_migrations_in_one_change_are_each_checked(tmp_path):
    second = "apps/api/Api/Migrations/20260912130000_AddOther.cs"
    _touch(tmp_path, MIGRATION, DESIGNER, second, SNAPSHOT)
    report = ef_migration_triad(_envelope([MIGRATION, second, SNAPSHOT]), _run(tmp_path))
    assert len(report.checks) == 4
    assert len(report.violations) == 1       # only the second lacks a Designer
    assert "AddOther" in report.violations[0]


def test_windows_separators_in_changed_files_are_handled(tmp_path):
    _touch(tmp_path, MIGRATION, DESIGNER, SNAPSHOT)
    windows = [p.replace("/", "\\") for p in (MIGRATION, DESIGNER, SNAPSHOT)]
    assert ef_migration_triad(_envelope(windows), _run(tmp_path)).passed
