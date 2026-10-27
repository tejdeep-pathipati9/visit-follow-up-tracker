"""UI search endpoints: filters, presets, sorting, paging, counts, and detail views."""

from contextlib import closing
import sqlite3
from typing import get_args

import pytest

from app.models import FollowUpGroup, FollowUpPreset
from tests.conftest import AS_OF


def get(client, path, **params):
    response = client.get(path, params={"as_of_date": AS_OF, **params})
    assert response.status_code == 200, response.text
    return response.json()


def ids(page, key="followup_id"):
    return [item[key] for item in page["items"]]


def followup_ids(client, **params):
    return sorted(ids(get(client, "/api/followups", limit=1000, **params)))


def test_followups_default_to_due_date_order_with_rule_flags(client):
    page = get(client, "/api/followups")
    assert page["total"] == 7
    assert ids(page) == ["F005", "F006", "F001", "F007", "F002", "F003", "F004"]
    flags = {item["followup_id"]: item["flags"] for item in page["items"]}
    assert flags == {
        "F001": ["overdue", "unassigned"], "F002": ["due_soon"], "F003": ["due_soon"],
        "F004": ["unassigned"], "F005": [], "F006": ["overdue"], "F007": ["overdue"],
    }
    first = page["items"][1]
    assert first["patient_name"] == "Zoë Tëst"
    assert first["assigned_staff_name"] == "Dr. Example"
    assert first["visit_staff_name"] == "Dr. Example"
    assert first["days_until_due"] == -2


@pytest.mark.parametrize(("flag", "expected"), [
    ("overdue", ["F001", "F006", "F007"]),
    ("due_soon", ["F002", "F003"]),
    ("unassigned", ["F001", "F004"]),
])
def test_flag_filters_match_rule_flags(client, flag, expected):
    assert followup_ids(client, flag=flag) == expected
    every = get(client, "/api/followups")["items"]
    assert sorted(item["followup_id"] for item in every if flag in item["flags"]) == expected


@pytest.mark.parametrize(("params", "expected"), [
    ({"status": ["open", "done"]}, ["F001", "F002", "F003", "F004", "F005", "F006", "F007"]),
    ({"status": "done"}, ["F005"]),
    ({"action_type": ["referral", "recheck"]}, ["F003", "F004", "F006"]),
    ({"flag": ["overdue", "due_soon"]}, ["F001", "F002", "F003", "F006", "F007"]),
    ({"patient_id": "P001"}, ["F001", "F002", "F005"]),
    ({"visit_id": "V002", "action_type": "lab"}, ["F007"]),
    ({"episode_id": "E001", "status": "open"}, ["F001", "F002"]),
    ({"assigned_staff_id": ["S001", "S002"]}, ["F002", "F003", "F006", "F007"]),
    ({"unassigned": "true"}, ["F001", "F004", "F005"]),
    ({"unassigned": "false", "status": "open"}, ["F002", "F003", "F006", "F007"]),
    ({"staff_id": "S002"}, ["F001", "F002", "F003", "F005"]),
    ({"staff_name": "example"}, ["F002", "F003", "F004", "F006", "F007"]),
    ({"visit_staff_role": "nurse"}, ["F001", "F002", "F005"]),
    ({"assigned_staff_role": "doctor"}, ["F002", "F006", "F007"]),
    ({"q": "zoë"}, ["F003", "F004", "F006", "F007"]),
    ({"q": "F00", "patient_name": "alice"}, ["F001", "F002", "F005"]),
    ({"episode_description": "recheck"}, ["F003", "F004", "F006", "F007"]),
    ({"due_from": "2026-10-25", "due_to": "2026-10-26"}, ["F001", "F002", "F007"]),
    ({"due_within_days": 0}, ["F002"]),
    ({"due_within_days": 7}, ["F002", "F003"]),
    ({"due_within_days": 8}, ["F002", "F003", "F004"]),
    ({"days_overdue_min": 2}, ["F006"]),
    ({"days_overdue_max": 1}, ["F001", "F007"]),
    ({"days_overdue_min": 0}, ["F001", "F006", "F007"]),
    ({"visit_from": "2026-10-16"}, ["F003", "F004", "F006", "F007"]),
    ({"completed_within_days": 7}, ["F005"]),
    ({"completed_from": "2026-10-22"}, []),
    ({"episode_status": "open"}, ["F001", "F002", "F003", "F004", "F005", "F006", "F007"]),
    ({"episode_status": "closed"}, []),
])
def test_followup_filters_combine(client, params, expected):
    assert followup_ids(client, **params) == expected


@pytest.mark.parametrize("value", ["%", "_", "100%_", "\\"])
def test_text_filters_treat_wildcards_literally(client, value):
    expected = ["F001", "F002", "F005"] if value != "\\" else []
    assert followup_ids(client, notes=value) == expected


@pytest.mark.parametrize("value", ["' OR 1=1 --", "x'); DROP TABLE followups; --", "\" OR \"\"=\""])
def test_injection_attempts_are_plain_values(client, database, value):
    with closing(sqlite3.connect(database)) as connection:
        before = list(connection.iterdump())
    assert followup_ids(client, q=value) == []
    assert followup_ids(client, patient_id=value) == []
    assert get(client, "/api/patients", q=value)["total"] == 0
    with closing(sqlite3.connect(database)) as connection:
        assert list(connection.iterdump()) == before


@pytest.mark.parametrize("preset", get_args(FollowUpPreset))
def test_every_preset_runs(client, preset):
    get(client, "/api/followups", preset=preset)


@pytest.mark.parametrize(("params", "expected"), [
    ({"preset": "overdue"}, ["F001", "F006", "F007"]),
    ({"preset": "overdue", "action_type": "referral"}, ["F006"]),
    ({"preset": "unassigned_overdue"}, ["F001"]),
    ({"preset": "due_today"}, ["F002"]),
    ({"preset": "open_labs"}, ["F001", "F002", "F007"]),
    ({"preset": "completed_last_7_days"}, ["F005"]),
    ({"preset": "overdue_30_plus"}, []),
])
def test_presets_and_filters_combine(client, params, expected):
    assert followup_ids(client, **params) == expected


def test_followup_sorting_and_paging(client):
    page = get(client, "/api/followups", sort="-due_date", limit=2, offset=1)
    assert ids(page) == ["F003", "F002"]
    assert (page["total"], page["limit"], page["offset"]) == (7, 2, 1)
    assert ids(get(client, "/api/followups", sort="assigned_staff_name"))[-3:] == ["F005", "F001", "F004"]
    assert ids(get(client, "/api/followups", sort="-completed_at"))[0] == "F005"


def test_followup_stats_totals_and_groups(client):
    stats = get(client, "/api/followups/stats", group_by="assigned_staff")
    assert stats["totals"] | {} == {
        "followup_count": 7, "open_followups": 6, "done_followups": 1, "overdue_followups": 3,
        "due_today_followups": 1, "due_soon_followups": 2, "unassigned_followups": 2,
        "next_due_date": "2026-10-24",
    }
    groups = [(group["key"], group["label"], group["followup_count"]) for group in stats["groups"]]
    assert groups == [("S001", "Dr. Example", 3), (None, "Unassigned", 3), ("S002", "Nurse Sample", 1)]
    filtered = get(client, "/api/followups/stats", group_by="due_month", status="open")
    assert [(group["key"], group["followup_count"]) for group in filtered["groups"]] == [("2026-10", 4), ("2026-11", 2)]


@pytest.mark.parametrize("group_by", get_args(FollowUpGroup))
def test_every_stats_grouping_runs(client, group_by):
    stats = get(client, "/api/followups/stats", group_by=group_by)
    assert sum(group["followup_count"] for group in stats["groups"]) == 7


def test_patient_search(client):
    page = get(client, "/api/patients")
    assert ids(page, "patient_id") == ["P001", "P002"]
    alice, kim = page["items"]
    assert (alice["open_followups"], alice["overdue_followups"], alice["visit_count"]) == (2, 1, 1)
    assert (kim["open_followups"], kim["overdue_followups"], kim["next_due_date"]) == (4, 2, "2026-10-24")
    assert alice["phone"] == "555-0101"
    assert ids(get(client, "/api/patients", open_followups_min=3), "patient_id") == ["P002"]
    assert ids(get(client, "/api/patients", sort="-open_followups"), "patient_id") == ["P002", "P001"]
    assert ids(get(client, "/api/patients", q="555"), "patient_id") == ["P001"]
    assert ids(get(client, "/api/patients", open_action_type="recheck"), "patient_id") == ["P002"]
    assert ids(get(client, "/api/patients", staff_id="S002"), "patient_id") == ["P001", "P002"]
    assert ids(get(client, "/api/patients", flag="unassigned", overdue_followups_min=2), "patient_id") == ["P002"]
    assert get(client, "/api/patients", has_open_episode="false")["total"] == 0


def test_staff_search_reports_assigned_workload(client):
    page = get(client, "/api/staff", sort="-overdue_followups")
    first = page["items"][0]
    assert (first["staff_id"], first["open_followups"], first["overdue_followups"], first["visit_count"]) == (
        "S001", 3, 2, 1,
    )
    assert ids(get(client, "/api/staff", role="nurse"), "staff_id") == ["S002"]
    assert ids(get(client, "/api/staff", q="duplicate"), "staff_id") == ["S003", "S004"]
    assert ids(get(client, "/api/staff", open_followups_min=1), "staff_id") == ["S001", "S002"]
    assert get(client, "/api/staff", flag="unassigned")["total"] == 0


def test_visit_search(client):
    page = get(client, "/api/visits")
    assert ids(page, "visit_id") == ["V002", "V001"]
    assert page["items"][0]["followup_count"] == 4
    assert ids(get(client, "/api/visits", staff_id="S002"), "visit_id") == ["V001"]
    assert ids(get(client, "/api/visits", followup_count_min=4), "visit_id") == ["V002"]
    assert ids(get(client, "/api/visits", notes="100%"), "visit_id") == ["V001"]
    assert ids(get(client, "/api/visits", followup_action_type="recheck"), "visit_id") == ["V002"]
    assert ids(get(client, "/api/visits", visit_within_days=7), "visit_id") == ["V002"]
    assert ids(get(client, "/api/visits", flag="due_soon", sort="visit_date"), "visit_id") == ["V001", "V002"]


def test_episode_search(client):
    page = get(client, "/api/episodes")
    assert ids(page, "episode_id") == ["E002", "E001"]
    assert {item["episode_id"]: item["days_open"] for item in page["items"]} == {"E001": 11, "E002": 6}
    assert ids(get(client, "/api/episodes", days_open_min=10), "episode_id") == ["E001"]
    assert ids(get(client, "/api/episodes", status="open", patient_name="alice"), "episode_id") == ["E001"]
    assert ids(get(client, "/api/episodes", staff_id="S001"), "episode_id") == ["E002", "E001"]
    assert get(client, "/api/episodes", status="closed")["total"] == 0


def test_patient_detail_nests_episodes_visits_and_followups(client):
    detail = get(client, "/api/patients/P001")
    assert detail["patient"]["name"] == "Alice Example"
    [episode] = detail["episodes"]
    [visit] = episode["visits"]
    assert (episode["episode_id"], visit["visit_id"]) == ("E001", "V001")
    assert [item["followup_id"] for item in visit["followups"]] == ["F005", "F001", "F002"]


def test_other_detail_views(client):
    followup = get(client, "/api/followups/F001")
    assert followup["patient"]["patient_id"] == "P001"
    assert [item["followup_id"] for item in followup["episode_followups"]] == ["F005", "F002"]
    staff = get(client, "/api/staff/S001")
    assert [item["followup_id"] for item in staff["open_followups"]] == ["F006", "F007", "F002"]
    assert [visit["visit_id"] for visit in staff["recent_visits"]] == ["V002"]
    visit = get(client, "/api/visits/V002")["visit"]
    assert len(visit["followups"]) == 4
    episode = get(client, "/api/episodes/E002")["episode"]
    assert [visit["visit_id"] for visit in episode["visits"]] == ["V002"]


@pytest.mark.parametrize("path", [
    "/api/followups/F999", "/api/patients/P999", "/api/staff/S999", "/api/visits/V999", "/api/episodes/E999",
])
def test_missing_detail_returns_404(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


def test_dashboard(client):
    dashboard = get(client, "/api/dashboard")
    assert dashboard["followups"]["overdue_followups"] == 3
    assert dashboard["completed_last_7_days"] == 1
    assert dashboard["patients_with_overdue"] == 2
    assert dashboard["open_episodes"] == 2
    assert dashboard["visits_last_30_days"] == 2
    assert dashboard["staff_with_overdue"] == 1


def test_options_for_dropdowns_and_sliders(client):
    options = get(client, "/api/options")
    assert options["action_types"] == ["lab", "referral", "recheck"]
    assert [staff["staff_id"] for staff in options["staff"]] == ["S003", "S004", "S001", "S002"]
    assert options["staff_roles"] == ["doctor", "nurse"]
    assert options["date_ranges"]["due"] == {"min": "2026-10-20", "max": "2026-11-03"}
    assert options["date_ranges"]["completed"] == {"min": "2026-10-21", "max": "2026-10-21"}
    assert {preset["name"] for preset in options["presets"]} == set(get_args(FollowUpPreset))
    assert "-due_date" in options["sorts"]["followups"]


@pytest.mark.parametrize(("path", "params"), [
    ("/api/followups", {"limit": 0}),
    ("/api/followups", {"limit": 1001}),
    ("/api/followups", {"sort": "due_date; DROP TABLE followups"}),
    ("/api/followups", {"status": "deleted"}),
    ("/api/followups", {"due_within_days": -1}),
    ("/api/followups", {"as_of_date": "not-a-date"}),
    ("/api/followups", {"unknown_filter": "x"}),
    ("/api/followups", {"q": "x" * 101}),
    ("/api/followups/stats", {"group_by": "patients.phone"}),
    ("/api/patients", {"sort": "phone"}),
    ("/api/staff", {"flag": "late"}),
])
def test_invalid_search_parameters_return_422(client, path, params):
    assert client.get(path, params=params).status_code == 422
