"""Record-change endpoints: create and update every record type through fixed SQL."""

from contextlib import closing
import sqlite3

import pytest

from tests.conftest import AS_OF


def send(client, method, path, body, status=200):
    response = client.request(method, path, json=body, params={"as_of_date": AS_OF})
    assert response.status_code == status, response.text
    return response.json()


def error_code(client, method, path, body):
    response = client.request(method, path, json=body, params={"as_of_date": AS_OF})
    return response.status_code, response.json()["detail"]


def stored(database, sql, *parameters):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(sql, parameters).fetchone()


def test_create_records_end_to_end_with_generated_ids(client, database):
    patient = send(client, "POST", "/api/patients", {"name": "Bob Sample", "phone": "555-0199"}, 201)
    assert (patient["patient_id"], patient["visit_count"]) == ("P003", 0)
    staff = send(client, "POST", "/api/staff", {"name": "Dr. New", "role": "doctor"}, 201)
    assert staff["staff_id"] == "S006"
    episode = send(client, "POST", "/api/episodes", {
        "patient_id": "P003", "description": "Synthetic sprain", "opened_at": "2026-10-26",
    }, 201)
    assert (episode["episode_id"], episode["status"]) == ("E003", "open")
    visit = send(client, "POST", "/api/visits", {
        "episode_id": "E003", "staff_id": "S006", "visit_date": "2026-10-26", "notes": "First visit",
    }, 201)
    assert (visit["visit_id"], visit["patient_id"]) == ("V003", "P003")
    followup = send(client, "POST", "/api/followups", {
        "visit_id": "V003", "action_type": "recheck", "due_date": "2026-10-30", "assigned_staff_id": "S006",
    }, 201)
    assert followup["followup_id"] == "F008"
    assert (followup["status"], followup["flags"]) == ("open", ["due_soon"])
    assert send(client, "GET", "/api/patients/P003", None)["patient"]["open_followups"] == 1


def test_caller_supplied_id_is_kept_and_duplicates_conflict(client):
    assert send(client, "POST", "/api/staff", {"staff_id": "S100", "name": "Nurse New", "role": "nurse"}, 201)["staff_id"] == "S100"
    assert send(client, "POST", "/api/staff", {"name": "Next", "role": "nurse"}, 201)["staff_id"] == "S101"
    status, detail = error_code(client, "POST", "/api/patients", {"patient_id": "P001", "name": "Copy"})
    assert (status, detail["code"]) == (409, "already_exists")


def test_partial_update_changes_only_sent_fields(client, database):
    patient = send(client, "PATCH", "/api/patients/P001", {"phone": None})
    assert (patient["name"], patient["phone"], patient["email"]) == ("Alice Example", None, "alice@example.test")
    send(client, "PATCH", "/api/staff/S002", {"role": "senior nurse"})
    assert stored(database, "SELECT name, role FROM staff WHERE staff_id = 'S002'") == ("Nurse Sample", "senior nurse")


def test_followup_completion_assignment_and_reopen(client, database):
    done = send(client, "PATCH", "/api/followups/F001", {"status": "done", "assigned_staff_id": "S002"})
    assert (done["status"], done["assigned_staff_id"], done["flags"]) == ("done", "S002", [])
    assert done["completed_at"].endswith("Z")
    reopened = send(client, "PATCH", "/api/followups/F001", {"status": "open"})
    assert (reopened["completed_at"], reopened["assigned_staff_id"], reopened["flags"]) == (None, "S002", ["overdue"])
    assert stored(database, "SELECT status, completed_at FROM followups WHERE followup_id = 'F001'") == ("open", None)


def test_followup_always_has_a_staff_member(client):
    missing = client.post("/api/followups", json={"visit_id": "V001", "action_type": "lab", "due_date": "2026-11-01"})
    assert missing.status_code == 422
    cleared = client.patch("/api/followups/F001", json={"assigned_staff_id": None})
    assert cleared.status_code == 422


def test_followup_without_a_scheduled_date_is_unassigned(client, database):
    created = send(client, "POST", "/api/followups", {"visit_id": "V001", "action_type": "referral", "assigned_staff_id": "S001"}, 201)
    assert (created["due_date"], created["days_until_due"], created["flags"]) == (None, None, ["unassigned"])
    scheduled = send(client, "PATCH", f"/api/followups/{created['followup_id']}", {"due_date": "2026-11-01"})
    assert scheduled["flags"] == ["due_soon"]
    cleared = send(client, "PATCH", f"/api/followups/{created['followup_id']}", {"due_date": None})
    assert cleared["flags"] == ["unassigned"]
    assert stored(database, f"SELECT due_date FROM followups WHERE followup_id = '{created['followup_id']}'") == (None,)


def test_episode_close_and_reopen(client):
    closed = send(client, "PATCH", "/api/episodes/E001", {"closed_at": "2026-10-26"})
    assert closed["status"] == "closed"
    assert send(client, "PATCH", "/api/episodes/E001", {"closed_at": None})["status"] == "open"
    status, detail = error_code(client, "PATCH", "/api/episodes/E001", {"closed_at": "2026-01-01"})
    assert (status, detail["code"]) == (422, "invalid_change")


@pytest.mark.parametrize("method, path, body, status, code", [
    ("PATCH", "/api/patients/P999", {"name": "Nobody"}, 404, "not_found"),
    ("PATCH", "/api/followups/F999", {"status": "done"}, 404, "not_found"),
    ("POST", "/api/episodes", {"patient_id": "P999", "description": "x", "opened_at": "2026-10-01"}, 422, "unknown_reference"),
    ("POST", "/api/visits", {"episode_id": "E999", "staff_id": "S001", "visit_date": "2026-10-01"}, 422, "unknown_reference"),
    ("POST", "/api/followups", {"visit_id": "V001", "action_type": "lab", "due_date": "2026-11-01",
                                "assigned_staff_id": "S999"}, 422, "unknown_reference"),
    ("PATCH", "/api/visits/V001", {"staff_id": "S999"}, 422, "unknown_reference"),
])
def test_missing_records_are_clear_errors(client, method, path, body, status, code):
    response_status, detail = error_code(client, method, path, body)
    assert (response_status, detail["code"]) == (status, code)


@pytest.mark.parametrize("method, path, body", [
    ("PATCH", "/api/patients/P001", {}),                              # nothing to change
    ("PATCH", "/api/patients/P001", {"name": None}),                  # NOT NULL column
    ("PATCH", "/api/patients/P001", {"patient_id": "P777"}),          # IDs never change
    ("PATCH", "/api/followups/F001", {"completed_at": "2026-01-01"}), # server-controlled
    ("PATCH", "/api/followups/F001", {"status": "cancelled"}),
    ("POST", "/api/followups", {"visit_id": "V001", "action_type": "x-ray", "due_date": "2026-11-01"}),
    ("POST", "/api/visits", {"episode_id": "E001", "visit_date": "not-a-date"}),
    ("POST", "/api/patients", {"name": "   "}),
])
def test_invalid_changes_are_rejected_without_writing(client, database, method, path, body):
    before = stored(database, "SELECT group_concat(name) FROM patients")
    assert client.request(method, path, json=body).status_code == 422
    assert stored(database, "SELECT group_concat(name) FROM patients") == before
    assert stored(database, "SELECT COUNT(*) FROM followups") == (7,)


def test_failed_change_rolls_back(client, database, monkeypatch):
    from app import writes

    original = writes.update

    def fail_after_update(connection, kind, record_id, values):
        original(connection, kind, record_id, values)
        raise RuntimeError("simulated failure after the UPDATE ran")

    monkeypatch.setattr(writes, "update", fail_after_update)
    with pytest.raises(RuntimeError):
        client.patch("/api/patients/P001", json={"name": "Changed"})
    assert stored(database, "SELECT name FROM patients WHERE patient_id = 'P001'") == ("Alice Example",)


def test_values_are_bound_not_interpolated(client, database):
    name = "Robert'); DROP TABLE patients; --"
    created = send(client, "POST", "/api/patients", {"name": name}, 201)
    assert created["name"] == name
    assert stored(database, "SELECT COUNT(*) FROM patients") == (3,)


def history(database, followup_id):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(
            "SELECT field, old_value, new_value, changed_by, note FROM followup_history"
            " WHERE followup_id = ? ORDER BY change_id",
            (followup_id,),
        ).fetchall()


def test_every_status_change_is_kept_in_history(client, database):
    send(client, "PATCH", "/api/followups/F002", {"status": "done"})
    send(client, "PATCH", "/api/followups/F002", {"status": "open", "notes": "Result lost; repeat the lab"})
    closed = send(client, "PATCH", "/api/followups/F002", {"status": "closed", "notes": "Patient unreachable after three calls"})
    assert (closed["status"], closed["notes"], closed["flags"]) == ("closed", "Patient unreachable after three calls", [])
    assert closed["completed_at"].endswith("Z")
    # The signed-in manager (S005) made every change.
    assert history(database, "F002") == [
        ("status", "open", "done", "S005", None),
        ("status", "done", "open", "S005", "Result lost; repeat the lab"),
        ("status", "open", "closed", "S005", "Patient unreachable after three calls"),
    ]
    detail = send(client, "GET", "/api/followups/F002", None)
    assert [(c["old_value"], c["new_value"], c["changed_by_name"]) for c in detail["history"]] == [
        ("open", "done", "Manager Example"), ("done", "open", "Manager Example"), ("open", "closed", "Manager Example"),
    ]


def test_reschedules_and_staff_changes_are_kept_too(client, database):
    send(client, "PATCH", "/api/followups/F002", {"due_date": "2026-11-05", "notes": "Patient asked for a later date"})
    send(client, "PATCH", "/api/followups/F002", {"assigned_staff_id": "S002"})
    send(client, "PATCH", "/api/followups/F002", {"due_date": None})
    assert history(database, "F002") == [
        ("due_date", "2026-10-26", "2026-11-05", "S005", "Patient asked for a later date"),
        ("assigned_staff_id", "S001", "S002", "S005", None),
        ("due_date", "2026-11-05", None, "S005", None),
    ]


def test_one_change_of_several_fields_adds_a_row_for_each(client, database):
    send(client, "PATCH", "/api/followups/F002", {"status": "done", "assigned_staff_id": "S002"})
    assert [row[:3] for row in history(database, "F002")] == [("status", "open", "done"), ("assigned_staff_id", "S001", "S002")]


def test_changes_that_keep_tracked_fields_add_no_history(client, database):
    send(client, "PATCH", "/api/followups/F002", {"notes": "Bring the previous results"})
    send(client, "PATCH", "/api/followups/F002", {"status": "open", "due_date": "2026-10-26", "action_type": "recheck"})
    assert history(database, "F002") == []


@pytest.mark.parametrize("body", [{"status": "closed"}, {"status": "closed", "notes": "   "}])
def test_closing_needs_a_reason(client, database, body):
    status, detail = error_code(client, "PATCH", "/api/followups/F002", body)
    assert (status, detail["code"]) == (422, "invalid_change")
    assert stored(database, "SELECT status FROM followups WHERE followup_id = 'F002'") == ("open",)
    assert history(database, "F002") == []


def test_status_change_and_history_are_saved_together_or_not_at_all(client, database):
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            "CREATE TRIGGER refuse_history BEFORE INSERT ON followup_history BEGIN SELECT RAISE(ABORT, 'history unavailable'); END"
        )
        connection.commit()
    response = client.patch("/api/followups/F002", json={"status": "done"}, params={"as_of_date": AS_OF})
    assert response.status_code == 409
    assert stored(database, "SELECT status, completed_at FROM followups WHERE followup_id = 'F002'") == ("open", None)
    assert history(database, "F002") == []
