"""Read-only SQLite connections for search requests."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def read_database() -> Iterator[sqlite3.Connection]:
    db_path = Path(
        os.environ.get("FOLLOWUP_DB_PATH") or PROJECT_ROOT / "data" / "followups.db"
    ).expanduser().resolve()
    # mode=ro prevents accidental creation of a missing DB and prohibits writes.
    connection = sqlite3.connect(
        db_path.as_uri() + "?mode=ro", uri=True, check_same_thread=False, timeout=5
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        # Each query request reads one consistent snapshot.
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def get_db() -> Iterator[sqlite3.Connection]:
    with read_database() as connection:
        yield connection
