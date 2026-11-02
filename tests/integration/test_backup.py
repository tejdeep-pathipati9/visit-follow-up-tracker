"""A backup is a verified copy that restores to the same records."""

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from scripts import backup_db
from scripts.backup_db import backup, main, row_counts


def test_backup_is_checked_and_restorable(database, tmp_path, capsys):
    assert main(["--db-path", str(database), "--output", str(tmp_path / "backups")]) == 0
    output = capsys.readouterr().out
    assert "integrity_check ok, test restore matched" in output and "7 followups" in output
    [copy] = (tmp_path / "backups").glob("followups-*.db")
    assert row_counts(copy) == row_counts(database)


def test_backup_reads_a_database_that_is_in_use(database, tmp_path):
    with closing(sqlite3.connect(database)) as live:
        live.execute("BEGIN")
        live.execute("SELECT COUNT(*) FROM followups").fetchone()  # a reader holds a lock
        copy = backup(database, tmp_path)
    assert row_counts(copy)["patients"] == 2


def test_missing_database_fails_clearly(tmp_path, capsys):
    assert main(["--db-path", str(tmp_path / "missing.db"), "--output", str(tmp_path / "b")]) == 1
    assert "does not exist" in capsys.readouterr().err


def changing_copy(monkeypatch, database, change, when_source_is_live):
    """Run `change` on the file just written by copy_database: after the snapshot of the
    live database, or after the test restore."""
    real_copy = backup_db.copy_database

    def copy(source, target):
        real_copy(source, target)
        if (Path(source) == Path(database)) == when_source_is_live:
            with closing(sqlite3.connect(database if when_source_is_live else target)) as connection, connection:
                connection.execute(change)

    monkeypatch.setattr(backup_db, "copy_database", copy)


def test_records_saved_after_the_snapshot_do_not_fail_the_check(database, tmp_path, monkeypatch):
    # Someone adds a staff member while the backup is being checked.
    changing_copy(monkeypatch, database, "INSERT INTO staff (staff_id, name, role) VALUES ('S900', 'New Nurse', 'nurse')",
                  when_source_is_live=True)
    copy = backup(database, tmp_path)
    assert row_counts(copy)["staff"] == 5 and row_counts(database)["staff"] == 6


@pytest.mark.parametrize("change", [
    "DELETE FROM followups WHERE followup_id = 'F007'",
    "UPDATE followups SET status = 'done' WHERE followup_id = 'F001'",  # same count, different contents
])
def test_a_restore_that_differs_from_the_backup_fails(database, tmp_path, monkeypatch, change):
    changing_copy(monkeypatch, database, change, when_source_is_live=False)
    with pytest.raises(ValueError, match="differs from the backup"):
        backup(database, tmp_path)
