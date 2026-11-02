"""Shared SQLite fixtures: a temporary database seeded with synthetic records.

Relative to AS_OF (2026-10-26): F001/F006/F007 are overdue, F002/F003 are due soon
(lab 3 days, referral and recheck 14 days), F004 is unassigned (no scheduled date),
and F005 is done. Every follow-up has an assigned staff member.
"""

from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.main import app
from scripts.table_generate import table_generate

AS_OF = "2026-10-26"
MANAGER_EMAIL = "manager@clinic.test"


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
            "INSERT INTO staff (staff_id, name, role, email) VALUES (?, ?, ?, ?)",
            [("S001", "Dr. Example", "doctor", "example@clinic.test"),
             ("S002", "Nurse Sample", "nurse", "sample@clinic.test"),
             ("S003", "Dr. Duplicate", "doctor", None), ("S004", "Dr. Duplicate", "doctor", None),
             ("S005", "Manager Example", "manager", MANAGER_EMAIL)],
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
            "INSERT INTO followups (followup_id, visit_id, action_type, due_date, assigned_staff_id, status, completed_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("F001", "V001", "lab", "2026-10-25", "S003", "open", None),
             ("F002", "V001", "lab", "2026-10-26", "S001", "open", None),
             ("F003", "V002", "recheck", "2026-11-02", "S002", "open", None),
             ("F004", "V002", "referral", None, "S003", "open", None),
             ("F005", "V001", "lab", "2026-10-20", "S004", "done", "2026-10-21T12:00:00Z"),
             ("F006", "V002", "referral", "2026-10-24", "S001", "open", None),
             ("F007", "V002", "lab", "2026-10-25", "S001", "open", None)],
        )
        connection.commit()
    return path


@pytest.fixture
def client(database):
    """A client signed in as the clinic manager, who sees and edits every record."""
    with TestClient(app) as client:
        response = client.post("/api/session", json={"email": MANAGER_EMAIL})
        assert response.status_code == 200, response.text
        yield client
