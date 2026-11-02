"""Calendar events (1.1.0): who sees and changes them, their checks, and the upgrade."""

from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.db import add_missing_tables
from app.main import app
from scripts.backup_db import backup, row_counts
from tests.conftest import MANAGER_EMAIL

NURSE_EMAIL = "sample@clinic.test"  # S002
RANGE = {"date_from": "2026-11-01", "date_to": "2026-11-30"}


def signed_in(email):
    client = TestClient(app)
    assert client.post("/api/session", json={"email": email}).status_code == 200
    return client


def add(client, **body):
    response = client.post("/api/events", json={"title": "Event", "event_date": "2026-11-10", **body})
    assert response.status_code == 201, response.text
    return response.json()


def titles(client, **params):
    response = client.get("/api/events", params={**RANGE, **params})
    assert response.status_code == 200, response.text
    return [event["title"] for event in response.json()]


def test_manager_adds_events_for_the_clinic_or_one_person(database):
    manager = signed_in(MANAGER_EMAIL)
    clinic = add(manager, title="Clinic closed", event_date="2026-11-11")
    assert (clinic["event_id"], clinic["staff_id"], clinic["created_by"]) == ("C001", None, "S005")
    personal = add(manager, title="Dr. Example on leave", staff_id="S001", start_time="09:30", notes="Synthetic")
    assert (personal["staff_name"], personal["created_by_name"], personal["start_time"]) == ("Dr. Example", "Manager Example", "09:30")
    assert titles(manager) == ["Dr. Example on leave", "Clinic closed"]


def test_staff_see_the_clinics_events_and_their_own(database):
    manager = signed_in(MANAGER_EMAIL)
    add(manager, title="Clinic closed")
    add(manager, title="For Dr. Example", staff_id="S001")
    add(manager, title="For the nurse", staff_id="S002")
    nurse = signed_in(NURSE_EMAIL)
    own = add(nurse, title="Call the lab")
    assert own["staff_id"] == "S002"  # staff add their own events
    assert set(titles(nurse)) == {"Clinic closed", "For the nurse", "Call the lab"}
    assert len(titles(manager)) == 4


def test_staff_change_only_their_own_events(database):
    manager = signed_in(MANAGER_EMAIL)
    clinic = add(manager, title="Clinic closed")
    other = add(manager, title="For Dr. Example", staff_id="S001")
    nurse = signed_in(NURSE_EMAIL)
    own = add(nurse, title="Call the lab")

    assert nurse.patch(f"/api/events/{clinic['event_id']}", json={"title": "Open"}).status_code == 403
    assert nurse.delete(f"/api/events/{clinic['event_id']}").status_code == 403
    assert nurse.delete(f"/api/events/{other['event_id']}").status_code == 404  # not visible to her
    for body in ({"title": "Clinic", "event_date": "2026-11-12", "staff_id": "S001"},):
        assert nurse.post("/api/events", json=body).status_code == 403
    assert nurse.patch(f"/api/events/{own['event_id']}", json={"staff_id": "S001"}).status_code == 403

    moved = nurse.patch(f"/api/events/{own['event_id']}", json={"event_date": "2026-11-20", "start_time": "14:00"})
    assert (moved.status_code, moved.json()["event_date"], moved.json()["start_time"]) == (200, "2026-11-20", "14:00")
    assert nurse.delete(f"/api/events/{own['event_id']}").status_code == 204
    assert "Call the lab" not in titles(manager)
    assert manager.delete(f"/api/events/{clinic['event_id']}").status_code == 204


def test_all_day_events_come_first_then_by_time(database):
    manager = signed_in(MANAGER_EMAIL)
    add(manager, title="Afternoon", start_time="15:00")
    add(manager, title="Morning", start_time="08:30")
    add(manager, title="All day")
    add(manager, title="Next day", event_date="2026-11-11")
    add(manager, title="Outside the range", event_date="2026-12-01")
    assert titles(manager) == ["All day", "Morning", "Afternoon", "Next day"]


@pytest.mark.parametrize("body", [
    {"title": " ", "event_date": "2026-11-10"},
    {"title": "Late", "event_date": "2026-11-10", "start_time": "25:00"},
    {"title": "No date"},
    {"title": "Bad date", "event_date": "2026-02-30"},
    {"title": "Extra", "event_date": "2026-11-10", "colour": "red"},
])
def test_invalid_events_are_rejected(database, body):
    assert signed_in(MANAGER_EMAIL).post("/api/events", json=body).status_code == 422


def test_unknown_staff_and_events_are_clear_errors(database):
    manager = signed_in(MANAGER_EMAIL)
    response = manager.post("/api/events", json={"title": "X", "event_date": "2026-11-10", "staff_id": "S999"})
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "unknown_reference")
    assert manager.patch("/api/events/C999", json={"title": "X"}).status_code == 404
    assert manager.patch("/api/events/C999", json={}).status_code == 422  # nothing to change


@pytest.mark.parametrize("params", [
    {"date_from": "2026-11-30", "date_to": "2026-11-01"},
    {"date_from": "2026-01-01", "date_to": "2027-02-01"},
    {"date_from": "2026-11-01"},
])
def test_ranges_are_checked(database, params):
    assert signed_in(MANAGER_EMAIL).get("/api/events", params=params).status_code == 422


def test_signed_out_requests_are_refused(database):
    assert TestClient(app).get("/api/events", params=RANGE).status_code == 401


def drop_events_table(database):
    """Make the database look like one written by release 1.0.0."""
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("DROP TABLE schedule_events")


def test_starting_the_app_adds_the_new_table_and_keeps_the_records(database):
    drop_events_table(database)
    with TestClient(app) as client:  # startup runs add_missing_tables
        client.post("/api/session", json={"email": MANAGER_EMAIL})
        assert client.get("/api/events", params=RANGE).json() == []
        assert client.get("/api/followups").json()["total"] == 7


def test_a_missing_database_is_not_created_at_startup(tmp_path, monkeypatch):
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(missing))
    assert add_missing_tables() is False
    assert not missing.exists()


def test_a_database_without_the_new_table_still_backs_up(database, tmp_path):
    drop_events_table(database)
    copy = backup(database, tmp_path)
    assert "schedule_events" not in row_counts(copy) and row_counts(copy)["followups"] == 7
