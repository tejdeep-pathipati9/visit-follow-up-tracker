"""Sign-in by staff email, and what each staff member may see and change.

In the fixture, Nurse Sample (S002) is assigned only F003, which belongs to patient P002
(visit V002, episode E002). The manager (S005) sees everything.
"""

from contextlib import contextmanager
import csv
import io

from fastapi.testclient import TestClient
import pytest

from app.main import app
from tests.conftest import AS_OF, MANAGER_EMAIL

NURSE_EMAIL = "sample@clinic.test"


@contextmanager
def signed_in(email):
    with TestClient(app) as client:
        response = client.post("/api/session", json={"email": email})
        assert response.status_code == 200, response.text
        yield client


def get(client, path, **params):
    response = client.get(path, params={"as_of_date": AS_OF, **params})
    assert response.status_code == 200, response.text
    return response.json()


def ids(page, key):
    return [item[key] for item in page["items"]]


# --- signing in and out --------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/followups", "/api/options", "/api/dashboard", "/api/report", "/api/session"])
def test_signed_out_requests_are_refused(database, path):
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_signed_in"


def test_signed_out_report_page_goes_to_sign_in(database):
    with TestClient(app) as client:
        response = client.get("/report", follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/")


@pytest.mark.parametrize("email", ["nobody@clinic.test", "not an email"])
def test_unknown_email_cannot_sign_in(database, email):
    with TestClient(app) as client:
        response = client.post("/api/session", json={"email": email})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unknown_email"


def test_email_is_matched_without_case_and_spaces(database):
    with signed_in("  Sample@Clinic.TEST ") as client:
        session = get(client, "/api/session")
    assert (session["staff_id"], session["is_manager"]) == ("S002", False)


def test_signing_out_ends_the_session(database):
    with signed_in(NURSE_EMAIL) as client:
        response = client.delete("/api/session")
        assert (response.status_code, response.content, "content-type" in response.headers) == (204, b"", False)
        assert client.get("/api/followups").status_code == 401


def test_session_cookie_is_http_only(database):
    with TestClient(app) as client:
        response = client.post("/api/session", json={"email": MANAGER_EMAIL})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


# --- what a staff member sees ---------------------------------------------------


def test_staff_see_only_their_own_follow_ups_and_patients(database):
    with signed_in(NURSE_EMAIL) as client:
        assert ids(get(client, "/api/followups"), "followup_id") == ["F003"]
        assert ids(get(client, "/api/patients"), "patient_id") == ["P002"]
        assert ids(get(client, "/api/visits"), "visit_id") == ["V002"]
        assert ids(get(client, "/api/episodes"), "episode_id") == ["E002"]
        assert ids(get(client, "/api/staff"), "staff_id") == ["S002"]


def test_counts_include_only_the_staff_members_follow_ups(database):
    with signed_in(NURSE_EMAIL) as client:
        patient = get(client, "/api/patients")["items"][0]
        dashboard = get(client, "/api/dashboard")
        stats = get(client, "/api/followups/stats")["totals"]
    # P002 has four follow-ups, but only F003 belongs to this nurse.
    assert (patient["followup_count"], patient["open_followups"], patient["overdue_followups"]) == (1, 1, 0)
    assert (dashboard["followups"]["followup_count"], dashboard["followups"]["due_soon_followups"]) == (1, 1)
    assert dashboard["patients"] == 1
    assert stats["followup_count"] == 1


@pytest.mark.parametrize("path", ["/api/followups/F001", "/api/patients/P001", "/api/visits/V001", "/api/episodes/E001", "/api/staff/S001"])
def test_other_staff_members_records_are_not_found(database, path):
    with signed_in(NURSE_EMAIL) as client:
        response = client.get(path, params={"as_of_date": AS_OF})
    assert response.status_code == 404


def test_patient_history_shows_only_the_staff_members_follow_ups(database):
    with signed_in(NURSE_EMAIL) as client:
        detail = get(client, "/api/patients/P002")
    followups = [f["followup_id"] for e in detail["episodes"] for v in e["visits"] for f in v["followups"]]
    assert followups == ["F003"]


def test_downloads_are_limited_the_same_way(database):
    with signed_in(NURSE_EMAIL) as client:
        response = client.get("/api/followups/export", params={"as_of_date": AS_OF})
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert [row[0] for row in rows[1:]] == ["F003"]


def test_manager_sees_every_follow_up(client):
    assert get(client, "/api/followups")["total"] == 7
    assert get(client, "/api/session")["is_manager"] is True


# --- what a staff member may change ---------------------------------------------


def test_staff_change_their_own_follow_up(database):
    with signed_in(NURSE_EMAIL) as client:
        response = client.patch("/api/followups/F003", json={"status": "done"}, params={"as_of_date": AS_OF})
    assert response.status_code == 200
    assert response.json()["status"] == "done"


def test_staff_cannot_change_someone_elses_follow_up(database):
    with signed_in(NURSE_EMAIL) as client:
        response = client.patch("/api/followups/F002", json={"status": "done"}, params={"as_of_date": AS_OF})
        assert response.status_code == 404
    with signed_in(MANAGER_EMAIL) as manager:
        assert get(manager, "/api/followups/F002")["followup"]["status"] == "open"


@pytest.mark.parametrize(("method", "path", "body"), [
    ("POST", "/api/patients", {"name": "Synthetic Patient"}),
    ("PATCH", "/api/patients/P002", {"name": "Renamed"}),
    ("POST", "/api/staff", {"name": "Dr. New", "role": "doctor"}),
    ("POST", "/api/followups", {"visit_id": "V002", "action_type": "lab", "assigned_staff_id": "S002"}),
    ("PATCH", "/api/visits/V002", {"notes": "Changed"}),
])
def test_only_a_manager_creates_or_edits(database, method, path, body):
    with signed_in(NURSE_EMAIL) as client:
        response = client.request(method, path, json=body, params={"as_of_date": AS_OF})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "managers_only"


def test_staff_email_must_be_unique_and_valid(client):
    duplicate = client.post("/api/staff", json={"name": "Dr. Copy", "role": "doctor", "email": "EXAMPLE@clinic.test"})
    assert (duplicate.status_code, duplicate.json()["detail"]["code"]) == (409, "already_exists")
    assert client.post("/api/staff", json={"name": "Dr. Typo", "role": "doctor", "email": "no-at-sign"}).status_code == 422
    created = client.post("/api/staff", json={"name": "Dr. New", "role": "doctor", "email": " New@Clinic.test "})
    assert created.json()["email"] == "new@clinic.test"


# --- printable report ------------------------------------------------------------


def test_report_groups_flagged_follow_ups_by_flag(client):
    report = get(client, "/api/report")
    assert report["all_followups"] is True
    assert {section["flag"]: [f["followup_id"] for f in section["followups"]] for section in report["sections"]} == {
        "overdue": ["F006", "F001", "F007"], "due_soon": ["F002", "F003"], "unassigned": ["F004"],
    }


def test_report_for_a_staff_member_lists_only_their_follow_ups(database):
    with signed_in(NURSE_EMAIL) as client:
        report = get(client, "/api/report")
    assert report["all_followups"] is False
    assert [f["followup_id"] for section in report["sections"] for f in section["followups"]] == ["F003"]


def test_printable_report_page(client):
    page = client.get("/report", params={"as_of_date": AS_OF})
    assert page.status_code == 200
    for text in ("Follow-up report", "All follow-ups", "Overdue (3)", "Due soon (2)", "Unassigned (no scheduled date) (1)", "F004", "Not scheduled"):
        assert text in page.text


def test_report_with_no_flags_says_so(database):
    with signed_in("example@clinic.test") as client:
        report = get(client, "/api/report", as_of_date="2026-01-01")
        page = client.get("/report", params={"as_of_date": "2026-01-01"})
    assert all(section["followups"] == [] for section in report["sections"])
    assert "No follow-ups need attention" in page.text
