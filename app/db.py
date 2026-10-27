"""SQLite connections: read-only for searches and questions, writable for record changes."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def database_path() -> Path:
    return Path(
        os.environ.get("FOLLOWUP_DB_PATH") or PROJECT_ROOT / "data" / "followups.db"
    ).expanduser().resolve()


def connect(mode: str) -> sqlite3.Connection:
    # mode=ro/rw never creates a missing DB; mode=ro also prohibits writes.
    connection = sqlite3.connect(
        database_path().as_uri() + f"?mode={mode}", uri=True, check_same_thread=False, timeout=5
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def read_database() -> Iterator[sqlite3.Connection]:
    connection = connect("ro")
    try:
        # Each query request reads one consistent snapshot.
        connection.execute("BEGIN")
        yield connection
    finally:
        connection.rollback()
        connection.close()


@contextmanager
def write_database() -> Iterator[sqlite3.Connection]:
    """One transaction per request. The caller commits before responding; anything
    left uncommitted, including after an error, is rolled back."""
    connection = connect("rw")
    try:
        # IMMEDIATE takes the write lock up front, so ID generation and checks cannot race.
        connection.execute("BEGIN IMMEDIATE")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def get_db() -> Iterator[sqlite3.Connection]:
    with read_database() as connection:
        yield connection


def get_write_db() -> Iterator[sqlite3.Connection]:
    with write_database() as connection:
        yield connection
