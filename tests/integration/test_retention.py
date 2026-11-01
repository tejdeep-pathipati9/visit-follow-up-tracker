"""The clinic keeps records for 10 years, then deletes them."""

from contextlib import closing
from datetime import date
import sqlite3

import pytest

from app.writes import retention_cutoff
from scripts.delete_old_records import main as delete_script


@pytest.fixture
def with_old_records(database):
    """Adds patient P009, whose only visit (2015) is more than 10 years before 2026-10-26,
    and a 2015 visit for P001, who also has recent visits."""
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript("""
            INSERT INTO patients (patient_id, name) VALUES ('P009', 'Old Patient');
            INSERT INTO episodes VALUES ('E009', 'P009', 'Synthetic old case', '2015-03-01', '2015-04-01');
            INSERT INTO visits VALUES ('V009', 'P009', 'E009', 'S001', '2015-03-02', NULL);
            INSERT INTO visits VALUES ('V008', 'P001', 'E001', 'S001', '2015-06-01', NULL);
            INSERT INTO followups (followup_id, visit_id, action_type, due_date, assigned_staff_id, status, completed_at)
                VALUES ('F009', 'V009', 'lab', '2015-03-10', 'S001', 'done', '2015-03-09T10:00:00Z'),
                       ('F008', 'V008', 'lab', '2015-06-10', 'S001', 'done', '2015-06-09T10:00:00Z');
            INSERT INTO followup_history (followup_id, field, old_value, new_value, changed_at)
                VALUES ('F009', 'status', 'open', 'done', '2015-03-09T10:00:00Z');
        """)
        connection.commit()
    return database


def ids(database, table, column):
    with closing(sqlite3.connect(database)) as connection:
        return sorted(row[0] for row in connection.execute(f"SELECT {column} FROM {table}"))


def test_cutoff_is_the_same_day_ten_years_earlier():
    assert retention_cutoff(date(2026, 10, 26), 10) == date(2016, 10, 26)
    assert retention_cutoff(date(2028, 2, 29), 10) == date(2018, 2, 28)


def test_old_records_are_deleted_and_recent_ones_kept(with_old_records, capsys):
    assert delete_script(["--as-of", "2026-10-26"]) == 0
    assert "Deleted records from before 2016-10-26: 1 followup_history, 2 followups, 2 visits, 1 episodes, 1 patients" in capsys.readouterr().out
    assert ids(with_old_records, "patients", "patient_id") == ["P001", "P002"]  # P001 keeps its recent visits
    assert ids(with_old_records, "visits", "visit_id") == ["V001", "V002"]
    assert ids(with_old_records, "followups", "followup_id") == ["F001", "F002", "F003", "F004", "F005", "F006", "F007"]
    assert ids(with_old_records, "staff", "staff_id") == ["S001", "S002", "S003", "S004", "S005"]


def test_dry_run_changes_nothing(with_old_records, capsys):
    assert delete_script(["--as-of", "2026-10-26", "--dry-run"]) == 0
    assert capsys.readouterr().out.startswith("Would delete records from before 2016-10-26: 1 followup_history, 2 followups")
    assert "P009" in ids(with_old_records, "patients", "patient_id")
    assert len(ids(with_old_records, "visits", "visit_id")) == 4


def test_nothing_recent_is_touched(database, capsys):
    assert delete_script(["--as-of", "2026-10-26"]) == 0
    assert "0 followup_history, 0 followups, 0 visits, 0 episodes, 0 patients" in capsys.readouterr().out
