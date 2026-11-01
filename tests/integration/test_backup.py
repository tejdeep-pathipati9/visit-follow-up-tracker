"""A backup is a verified copy that restores to the same records."""

from contextlib import closing
import sqlite3

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
