"""CSV downloads of search results: every row matching the list's filters, in its sort order.

Each export pages through the same fixed searches the UI uses, so the read-only
authorizer, bound parameters, and rule flags are identical to what the screen shows.
"""

from collections.abc import Callable
import csv
import io
import sqlite3
from typing import Any

from app.models import Page
from app.search import MAX_ROWS

# Upper bound for one download; larger result sets should be narrowed with filters.
EXPORT_MAX_ROWS = 100_000
# Spreadsheets run cells starting with these characters as formulas.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")

Getter = str | Callable[[dict[str, Any]], Any]
Columns = list[tuple[str, Getter]]


def has_flag(flag: str) -> Callable[[dict[str, Any]], str]:
    return lambda row: "Yes" if flag in row["flags"] else ""


COUNT_COLUMNS: Columns = [
    ("Open follow-ups", "open_followups"), ("Overdue", "overdue_followups"),
    ("Due soon", "due_soon_followups"), ("Unassigned (no date)", "unassigned_followups"),
    ("Next scheduled", "next_due_date"),
]

COLUMNS: dict[str, Columns] = {
    "followups": [
        ("Follow-up ID", "followup_id"), ("Patient ID", "patient_id"), ("Patient", "patient_name"),
        ("Action", "action_type"), ("Scheduled date", "due_date"), ("Days until scheduled", "days_until_due"),
        ("Status", "status"), ("Overdue", has_flag("overdue")), ("Due soon", has_flag("due_soon")),
        ("Unassigned (no date)", has_flag("unassigned")), ("Assigned to", "assigned_staff_name"),
        ("Seen by", "visit_staff_name"), ("Visit ID", "visit_id"), ("Visit date", "visit_date"),
        ("Episode", "episode_description"), ("Done or closed at", "completed_at"), ("Notes", "notes"),
    ],
    "patients": [
        ("Patient ID", "patient_id"), ("Name", "name"), ("Phone", "phone"), ("Email", "email"),
        ("Visits", "visit_count"), ("Open episodes", "open_episode_count"), *COUNT_COLUMNS,
        ("Last visit", "last_visit_date"),
    ],
    "staff": [
        ("Staff ID", "staff_id"), ("Name", "name"), ("Role", "role"), ("Visits", "visit_count"),
        ("Patients", "patient_count"), *COUNT_COLUMNS, ("Last visit", "last_visit_date"),
    ],
    "visits": [
        ("Visit ID", "visit_id"), ("Visit date", "visit_date"), ("Patient ID", "patient_id"),
        ("Patient", "patient_name"), ("Seen by", "staff_name"), ("Episode", "episode_description"),
        ("Notes", "notes"), ("Follow-ups", "followup_count"), *COUNT_COLUMNS,
    ],
    "episodes": [
        ("Episode ID", "episode_id"), ("Patient ID", "patient_id"), ("Patient", "patient_name"),
        ("Description", "description"), ("Status", "status"), ("Opened", "opened_at"),
        ("Closed", "closed_at"), ("Days open", "days_open"), ("Visits", "visit_count"), *COUNT_COLUMNS,
    ],
}


def cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith(FORMULA_STARTS):
        return "'" + value  # shown as text instead of being run as a formula
    return value


def all_items(search: Callable[[sqlite3.Connection, Any], Page], connection: sqlite3.Connection, filters: Any) -> list:
    """Every matching item, ignoring the caller's page, up to EXPORT_MAX_ROWS."""
    items: list = []
    while len(items) < EXPORT_MAX_ROWS:
        page = search(connection, filters.model_copy(update={"limit": MAX_ROWS, "offset": len(items)}))
        items.extend(page.items)
        if not page.items or len(items) >= page.total:
            break
    return items[:EXPORT_MAX_ROWS]


def to_csv(kind: str, items: list) -> bytes:
    """UTF-8 with a byte-order mark so spreadsheet apps keep accented names intact."""
    columns = COLUMNS[kind]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header for header, _ in columns)
    for item in items:
        row = item.model_dump(mode="json")
        writer.writerow(cell(get(row) if callable(get) else row[get]) for _, get in columns)
    return ("\ufeff" + out.getvalue()).encode("utf-8")
