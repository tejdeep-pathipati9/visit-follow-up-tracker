"""CSV downloads: same filters and sort as the list, every matching row, safe cells."""

import csv
import io

import pytest

from tests.conftest import AS_OF


def download(client, path, **params):
    response = client.get(path, params={"as_of_date": AS_OF, **params})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.content.startswith(b"\xef\xbb\xbf")
    return list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_followup_export_matches_the_filtered_list_with_flag_columns(client):
    response = client.get("/api/followups/export", params={"as_of_date": AS_OF, "flag": "due_soon"})
    assert response.headers["content-disposition"] == f'attachment; filename="followups-{AS_OF}.csv"'
    header, *rows = download(client, "/api/followups/export", flag=["due_soon", "unassigned"])
    assert header[:10] == [
        "Follow-up ID", "Patient ID", "Patient", "Action", "Scheduled date", "Days until scheduled",
        "Status", "Overdue", "Due soon", "Unassigned (no date)",
    ]
    assert [row[0] for row in rows] == ["F002", "F003", "F004"]
    f003, f004 = (dict(zip(header, row)) for row in rows[1:])
    assert (f003["Due soon"], f003["Unassigned (no date)"]) == ("Yes", "")
    assert (f004["Action"], f004["Scheduled date"], f004["Days until scheduled"]) == ("referral", "", "")
    assert (f004["Overdue"], f004["Due soon"], f004["Unassigned (no date)"]) == ("", "", "Yes")
    assert f004["Assigned to"] == "Dr. Duplicate" and f004["Patient"] == "Zoë Tëst"


def test_export_ignores_paging_and_keeps_the_sort(client):
    _, *rows = download(client, "/api/followups/export", limit=1, offset=3, sort="-due_date")
    assert [row[0] for row in rows] == ["F003", "F002", "F001", "F007", "F006", "F005", "F004"]


def test_export_pages_through_more_rows_than_one_search_returns(client, monkeypatch):
    monkeypatch.setattr("app.export.MAX_ROWS", 2)
    _, *rows = download(client, "/api/followups/export")
    assert len(rows) == 7


@pytest.mark.parametrize(("path", "first_header", "count"), [
    ("/api/patients/export", "Patient ID", 2),
    ("/api/staff/export", "Staff ID", 5),
    ("/api/visits/export", "Visit ID", 2),
    ("/api/episodes/export", "Episode ID", 2),
])
def test_every_record_type_exports(client, path, first_header, count):
    header, *rows = download(client, path)
    assert header[0] == first_header
    assert len(rows) == count


def test_cells_that_look_like_formulas_are_exported_as_text(client):
    created = client.post("/api/patients", json={"name": "=HYPERLINK(\"http://example.test\")"})
    assert created.status_code == 201, created.text
    _, *rows = download(client, "/api/patients/export", q="HYPERLINK")
    assert rows[0][1] == "'=HYPERLINK(\"http://example.test\")"


def test_negative_numbers_stay_numbers(client):
    header, *rows = download(client, "/api/followups/export", flag="overdue")
    days = header.index("Days until scheduled")
    assert [row[days] for row in rows] == ["-2", "-1", "-1"]


def test_export_rejects_unknown_filters(client):
    response = client.get("/api/followups/export", params={"surprise": "1"})
    assert response.status_code == 422
