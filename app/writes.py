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
from app.ingestion.loader import ExistingRecords, ImportBatch
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


def check_email_free(connection: sqlite3.Connection, email: str | None, staff_id: str | None = None) -> None:
    """Each sign-in email belongs to one staff member."""
    if email is None:
        return
    row = connection.execute("SELECT staff_id FROM staff WHERE email = ?", [email]).fetchone()
    if row is not None and row["staff_id"] != staff_id:
        raise QueryError("already_exists", f"Staff member {row['staff_id']} already uses {email}.", 409)


def create_staff(connection: sqlite3.Connection, body: StaffCreate) -> str:
    check_email_free(connection, body.email)
    return insert(connection, "staff", body)


def update_staff(connection: sqlite3.Connection, staff_id: str, body: StaffUpdate) -> None:
    existing(connection, "staff", staff_id)
    check_email_free(connection, body.email, staff_id)
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


TRACKED_FIELDS = ("status", "due_date", "assigned_staff_id")


def update_followup(
    connection: sqlite3.Connection, followup_id: str, body: FollowUpUpdate,
    scope: str | None = None, changed_by: str | None = None,
) -> None:
    """Change a follow-up in the caller's transaction, with one followup_history row for each
    tracked field that changes. With a scope, only a follow-up assigned to that staff member
    can change."""
    followup = existing(connection, "followup", followup_id)
    if scope is not None and followup["assigned_staff_id"] != scope:
        raise QueryError("not_found", f"Follow-up {followup_id} was not found.", 404)
    referenced(connection, "staff", body.assigned_staff_id)
    values = body.changes()
    new_status = values.get("status", followup["status"])
    notes = values.get("notes", followup["notes"])
    if new_status == "closed" and not (notes or "").strip():
        raise QueryError("invalid_change", "Closing a follow-up needs a reason in notes, such as 'patient unreachable'.")
    changed = [
        (field, followup[field], stored(values[field])) for field in TRACKED_FIELDS
        if field in values and stored(values[field]) != followup[field]
    ]
    changed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if new_status != followup["status"]:
        # completed_at is server-controlled: when it became done or closed, cleared when reopened.
        values["completed_at"] = None if new_status == "open" else changed_at
    update(connection, "followup", followup_id, values)
    note = values.get("notes") or (notes if new_status == "closed" else None)
    for field, old_value, new_value in changed:
        connection.execute(
            "INSERT INTO followup_history (followup_id, field, old_value, new_value, changed_at, changed_by, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            [followup_id, field, old_value, new_value, changed_at, changed_by, note],
        )


# --- Importing a file: every record of a checked batch in the caller's transaction. ---

# Table and the record fields saved for each list in an ImportBatch, parents first.
BATCH_TABLES = (
    ("patients", "patients"), ("staff", "staff"), ("episodes", "episodes"),
    ("visits", "visits"), ("followups", "followups"),
)


def existing_records(connection: sqlite3.Connection) -> ExistingRecords:
    def ids(table: str, column: str) -> frozenset[str]:
        return frozenset(row[0] for row in connection.execute(f"SELECT {column} FROM {table}"))

    return ExistingRecords(
        patients=ids("patients", "patient_id"),
        staff=ids("staff", "staff_id"),
        staff_emails=frozenset(row[0] for row in connection.execute("SELECT lower(email) FROM staff WHERE email IS NOT NULL")),
        episodes=dict(connection.execute("SELECT episode_id, patient_id FROM episodes").fetchall()),
        visits=ids("visits", "visit_id"),
        followups=ids("followups", "followup_id"),
    )


def save_batch(connection: sqlite3.Connection, batch: ImportBatch) -> dict[str, int]:
    """Insert a batch with no rejections, parents before children; returns counts per table.
    The caller commits, or rolls back on any error, so a failed save leaves nothing."""
    assert not batch.rejections, "only a batch without rejections is saved"
    counts = {}
    for attribute, table in BATCH_TABLES:
        records = getattr(batch, attribute)
        for record in records:
            values = record.model_dump()
            columns = list(values)
            connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                [stored(values[column]) for column in columns],
            )
        counts[table] = len(records)
    return counts


# --- Retention: the clinic keeps records for RETENTION_YEARS, then deletes them. ------

def retention_cutoff(as_of: date, years: int) -> date:
    """The same day `years` earlier (28 February for 29 February)."""
    try:
        return as_of.replace(year=as_of.year - years)
    except ValueError:
        return as_of.replace(year=as_of.year - years, day=28)


def delete_older_than(connection: sqlite3.Connection, cutoff: date) -> dict[str, int]:
    """Delete visits before the cutoff with their follow-ups and history, then the episodes
    and patients those deletions leave with no visits. Staff are kept. Runs in the caller's
    transaction; returns how many rows each table lost."""
    params = {"cutoff": cutoff.isoformat()}
    connection.execute("CREATE TEMP TABLE old_visits AS SELECT visit_id, episode_id, patient_id FROM visits WHERE visit_date < :cutoff", params)
    try:
        steps = (
            ("followup_history", "DELETE FROM followup_history WHERE followup_id IN "
                                 "(SELECT followup_id FROM followups WHERE visit_id IN (SELECT visit_id FROM old_visits))"),
            ("followups", "DELETE FROM followups WHERE visit_id IN (SELECT visit_id FROM old_visits)"),
            ("visits", "DELETE FROM visits WHERE visit_id IN (SELECT visit_id FROM old_visits)"),
            ("episodes", "DELETE FROM episodes WHERE episode_id IN (SELECT episode_id FROM old_visits)"
                         " AND episode_id NOT IN (SELECT episode_id FROM visits)"),
            ("patients", "DELETE FROM patients WHERE patient_id IN (SELECT patient_id FROM old_visits)"
                         " AND patient_id NOT IN (SELECT patient_id FROM episodes)"),
        )
        return {table: connection.execute(sql).rowcount for table, sql in steps}
    finally:
        connection.execute("DROP TABLE temp.old_visits")
