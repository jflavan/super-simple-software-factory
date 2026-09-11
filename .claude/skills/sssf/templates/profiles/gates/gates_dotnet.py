"""Gates that come with .NET.

STAMPED into adws/adw_modules/ by `install.py`, which is why the imports below
are relative: this file is part of that package once it lands.

Every rule here is a fact about a FRAMEWORK, never about a repository. EF Core
writes three files per migration - that is true in every repo that uses it, and
in none that does not.
"""

from __future__ import annotations

from pathlib import Path

from .data_types import EnvelopeBase, GateReport
from .utils import claimed_files

# EF Core's own file convention, and the only thing this gate knows.
MIGRATIONS_DIR = "Migrations"
DESIGNER_SUFFIX = ".Designer.cs"
SNAPSHOT_SUFFIX = "ModelSnapshot.cs"


def ef_migration_triad(envelope: EnvelopeBase, run) -> GateReport:
    """An EF Core migration is three files. Two of them are easy to forget.

    Without the sibling `.Designer.cs`, `Database.Migrate()` SKIPS the migration
    rather than failing - the schema silently does not change. Without an
    updated `*ModelSnapshot.cs`, the next migration is generated against a stale
    model and re-emits changes that are already applied. Both break far from
    where they were caused, which is exactly what a gate is for.

    The designer is checked on DISK, not in the changeset: editing an existing
    migration legitimately leaves its designer untouched. The snapshot is
    checked in the CHANGESET, because a migration that alters the model and
    leaves the snapshot alone is wrong however old the migration is.
    """
    report = GateReport()
    changed = claimed_files(envelope, run)
    for path in changed:
        parts = path.split("/")
        name = parts[-1]
        if MIGRATIONS_DIR not in parts[:-1] or not name.endswith(".cs"):
            continue
        if name.endswith(DESIGNER_SUFFIX) or name.endswith(SNAPSHOT_SUFFIX):
            continue

        directory = "/".join(parts[:-1])
        designer = f"{directory}/{name[:-3]}{DESIGNER_SUFFIX}"
        exists = (Path(run.repo_root) / designer).is_file()
        report.check(designer, exists,
                     "exists beside the migration" if exists else
                     f"{name} has no {DESIGNER_SUFFIX} - EF Core skips a migration "
                     f"with no model metadata instead of failing")

        snapshots = [f for f in changed
                     if f.startswith(f"{directory}/") and f.endswith(SNAPSHOT_SUFFIX)]
        report.check(f"{directory}/*{SNAPSHOT_SUFFIX}", bool(snapshots),
                     f"snapshot updated: {snapshots[0]}" if snapshots else
                     f"{name} changes the model but no model snapshot in "
                     f"{directory}/ was updated - the next migration will be "
                     f"generated against a stale model")
    return report
