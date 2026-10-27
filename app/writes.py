"""Fixed, parameterized INSERT and UPDATE statements behind the record-change endpoints.

Table and column names come from this module and the request models, never from
callers; every value is a bound parameter. Records are never deleted. Callers run
these inside db.write_database() and commit once the change succeeds.
"""

from datetime import date, datetime, timezone
import sqlite3

from app.models import (
    Change, EpisodeCreate, EpisodeUpdate, FollowUpCreate, FollowUpUpdate, PatientCreate,
    PatientUpdate, StaffCreate, StaffUpdate, VisitCreate, VisitUpdate,
)
from app.repository import QueryError

# kind: (label, table, id column, ID prefix)
RECORDS = {
    "patient": ("Patient", "patients", "patient_id", "P"),
    "staff": ("Staff member", "staff", "staff_id", "S"),
    "episode": ("Episode", "episodes", "episode_id", "E"),
    "visit": ("Visit", "visits", "visit_id", "V"),
    "followup": ("Follow-up", "followups", "followup_id", "F"),
}


def stored(value: object) -> object:
    return value.isoformat() if isinstance(value, date) else value


def find(connection: sqlite3.Connection, kind: str, record_id: str) -> sqlite3.Row | None:
    _, table, id_column, _ = RECORDS[kind]
    return connection.execute(f"SELECT * FROM {table} WHERE {id_column} = ?", (record_id,)).fetchone()


def existing(connection: sqlite3.Connection, kind: str, record_id: str) -> sqlite3.Row:
    """The record named in the URL; missing is 404."""
    row = find(connection, kind, record_id)
    if row is None:
        raise QueryError("not_found", f"{RECORDS[kind][0]} {record_id} was not found.", 404)
    return row


def referenced(connection: sqlite3.Connection, kind: str, record_id: str | None) -> sqlite3.Row | None:
    """A record named in the request body; missing is a 422 with a clear reason."""
    if record_id is None:
        return None
    row = find(connection, kind, record_id)
    if row is None:
        raise QueryError("unknown_reference", f"{RECORDS[kind][0]} {record_id} does not exist.")
    return row


def next_id(connection: sqlite3.Connection, kind: str) -> str:
    _, table, id_column, prefix = RECORDS[kind]
    (highest,) = connection.execute(
        f"SELECT MAX(CAST(substr({id_column}, 2) AS INTEGER)) FROM {table} WHERE {id_column} GLOB ?",
        (f"{prefix}[0-9]*",),
    ).fetchone()
    return f"{prefix}{(highest or 0) + 1:03d}"


def insert(connection: sqlite3.Connection, kind: str, body: Change, **extra: object) -> str:
    label, table, id_column, _ = RECORDS[kind]
    values = {**body.changes(), **extra}
    record_id = values.get(id_column) or next_id(connection, kind)
    if find(connection, kind, record_id) is not None:
        raise QueryError("already_exists", f"{label} {record_id} already exists.", 409)
    values[id_column] = record_id
    columns = list(values)
    connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [stored(values[column]) for column in columns],
    )
    return record_id


def update(connection: sqlite3.Connection, kind: str, record_id: str, values: dict[str, object]) -> None:
    _, table, id_column, _ = RECORDS[kind]
    columns = list(values)
    connection.execute(
        f"UPDATE {table} SET {', '.join(f'{column} = ?' for column in columns)} WHERE {id_column} = ?",
        [*(stored(values[column]) for column in columns), record_id],
    )


def check_episode_dates(opened_at: date | str, closed_at: date | str | None) -> None:
    if closed_at is not None and str(stored(closed_at)) < str(stored(opened_at)):
        raise QueryError("invalid_change", "closed_at cannot be before opened_at.")


def create_patient(connection: sqlite3.Connection, body: PatientCreate) -> str:
    return insert(connection, "patient", body)


def update_patient(connection: sqlite3.Connection, patient_id: str, body: PatientUpdate) -> None:
    existing(connection, "patient", patient_id)
    update(connection, "patient", patient_id, body.changes())


def create_staff(connection: sqlite3.Connection, body: StaffCreate) -> str:
    return insert(connection, "staff", body)


def update_staff(connection: sqlite3.Connection, staff_id: str, body: StaffUpdate) -> None:
    existing(connection, "staff", staff_id)
    update(connection, "staff", staff_id, body.changes())


def create_episode(connection: sqlite3.Connection, body: EpisodeCreate) -> str:
    referenced(connection, "patient", body.patient_id)
    check_episode_dates(body.opened_at, body.closed_at)
    return insert(connection, "episode", body)


def update_episode(connection: sqlite3.Connection, episode_id: str, body: EpisodeUpdate) -> None:
    episode = existing(connection, "episode", episode_id)
    merged = {**dict(episode), **body.changes()}
    check_episode_dates(merged["opened_at"], merged["closed_at"])
    update(connection, "episode", episode_id, body.changes())


def create_visit(connection: sqlite3.Connection, body: VisitCreate) -> str:
    episode = referenced(connection, "episode", body.episode_id)
    referenced(connection, "staff", body.staff_id)
    return insert(connection, "visit", body, patient_id=episode["patient_id"])


def update_visit(connection: sqlite3.Connection, visit_id: str, body: VisitUpdate) -> None:
    existing(connection, "visit", visit_id)
    referenced(connection, "staff", body.staff_id)
    update(connection, "visit", visit_id, body.changes())


def create_followup(connection: sqlite3.Connection, body: FollowUpCreate) -> str:
    referenced(connection, "visit", body.visit_id)
    referenced(connection, "staff", body.assigned_staff_id)
    return insert(connection, "followup", body, status="open")


def update_followup(connection: sqlite3.Connection, followup_id: str, body: FollowUpUpdate) -> None:
    followup = existing(connection, "followup", followup_id)
    referenced(connection, "staff", body.assigned_staff_id)
    values = body.changes()
    # completed_at is server-controlled: set when a follow-up becomes done, cleared when reopened.
    if values.get("status") == "done" and followup["status"] != "done":
        values["completed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif values.get("status") == "open":
        values["completed_at"] = None
    update(connection, "followup", followup_id, values)
