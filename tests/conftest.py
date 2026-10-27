"""Shared SQLite fixtures: a temporary database seeded with synthetic records.

Relative to AS_OF (2026-10-26): F001/F006/F007 are overdue, F002/F003 are due
soon, F001/F004 are unassigned, and F005 is done.
"""

from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.main import app
from scripts.table_generate import table_generate

AS_OF = "2026-10-26"


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = table_generate(tmp_path / "search.db")
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(path))
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            "INSERT INTO patients VALUES (?, ?, ?, ?)",
            [("P001", "Alice Example", "555-0101", "alice@example.test"), ("P002", "Zoë Tëst", None, None)],
        )
        connection.executemany(
            "INSERT INTO staff VALUES (?, ?, ?)",
            [("S001", "Dr. Example", "doctor"), ("S002", "Nurse Sample", "nurse"),
             ("S003", "Dr. Duplicate", "doctor"), ("S004", "Dr. Duplicate", "doctor")],
        )
        connection.executemany(
            "INSERT INTO episodes VALUES (?, ?, ?, ?, ?)",
            [("E001", "P001", "Synthetic injury", "2026-10-15", None),
             ("E002", "P002", "Synthetic recheck", "2026-10-20", None)],
        )
        connection.executemany(
            "INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?)",
            [("V001", "P001", "E001", "S002", "2026-10-15", "Synthetic 100%_ note"),
             ("V002", "P002", "E002", "S001", "2026-10-20", "Synthetic visit")],
        )
        connection.executemany(
            "INSERT INTO followups VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("F001", "V001", "lab", "2026-10-25", None, "open", None),
             ("F002", "V001", "lab", "2026-10-26", "S001", "open", None),
             ("F003", "V002", "recheck", "2026-11-02", "S002", "open", None),
             ("F004", "V002", "referral", "2026-11-03", None, "open", None),
             ("F005", "V001", "lab", "2026-10-20", None, "done", "2026-10-21T12:00:00Z"),
             ("F006", "V002", "referral", "2026-10-24", "S001", "open", None),
             ("F007", "V002", "lab", "2026-10-25", "S001", "open", None)],
        )
        connection.commit()
    return path


@pytest.fixture
def client(database):
    with TestClient(app) as client:
        yield client
