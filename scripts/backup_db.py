"""Back up the database while the app runs, and prove the copy can be restored.

Uses sqlite3.Connection.backup (a file copy of a live database can be torn), checks the
copy with PRAGMA integrity_check, then restores it into a scratch file and checks the
restore holds exactly what the backup holds. The live database is only read, and records
saved after the snapshot do not affect the check.
"""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLES = ("patients", "staff", "episodes", "visits", "followups", "followup_history", "schedule_events")


def present(connection: sqlite3.Connection) -> list[str]:
    """The tables in TABLES this database has; a 1.0.0 database has no schedule_events."""
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")}
    return [table for table in TABLES if table in names]


def row_counts(path: Path) -> dict[str, int]:
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in present(connection)}


def contents(path: Path) -> dict[str, tuple[int, str]]:
    """Each table's row count and a digest of its rows, to compare two copies."""
    result = {}
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        for table in present(connection):
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid"):
                digest.update(repr(row).encode("utf-8"))
                count += 1
            result[table] = (count, digest.hexdigest())
    return result


def copy_database(source: Path, target: Path) -> None:
    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as live, closing(sqlite3.connect(target)) as copy:
        live.backup(copy)


def integrity(path: Path) -> str:
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as connection:
        return connection.execute("PRAGMA integrity_check").fetchone()[0]


def backup(source: Path, backup_dir: Path) -> Path:
    """Write a verified backup and return its path; raise ValueError if any check fails."""
    if not source.exists():
        raise ValueError(f"{source} does not exist")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"followups-{stamp}.db"
    copy_database(source, target)
    if (result := integrity(target)) != "ok":
        raise ValueError(f"integrity_check on {target} returned {result!r}")
    with tempfile.TemporaryDirectory() as scratch:
        restored = Path(scratch) / "restored.db"
        copy_database(target, restored)
        # Compare with the backup, not the live database, which may have changed since.
        if contents(restored) != contents(target):
            raise ValueError("the test restore differs from the backup")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, help="SQLite file (default: FOLLOWUP_DB_PATH or data/followups.db).")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "backups", help="Backup folder (default: backups/).")
    args = parser.parse_args(argv)
    source = (args.db_path or Path(os.environ.get("FOLLOWUP_DB_PATH") or PROJECT_ROOT / "data" / "followups.db")).resolve()
    try:
        target = backup(source, args.output)
    except (ValueError, sqlite3.Error) as error:
        print(f"Backup failed: {error}", file=sys.stderr)
        return 1
    counts = ", ".join(f"{count} {table}" for table, count in row_counts(target).items())
    print(f"Backed up {source} to {target}: integrity_check ok, test restore matched ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
