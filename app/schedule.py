"""Calendar events: important dates that are not follow-ups, such as a team meeting or a
day the clinic is closed (release 1.1.0).

An event is for one staff member or, with no staff member, for the whole clinic.
Managers see and change every event. Other staff see the clinic's events and their own,
and add, change, or delete only their own. Events are not patient records, so unlike
follow-ups they can be deleted. Plain-English questions do not read them.
"""

import sqlite3

from app.models import EventCreate, EventItem, EventRange, EventUpdate
from app.repository import QueryError
from app.writes import insert, referenced, update

EVENT_SELECT = """
    SELECT e.event_id, e.title, e.event_date, e.start_time, e.staff_id, s.name AS staff_name,
           e.notes, e.created_by, c.name AS created_by_name
    FROM schedule_events e
    LEFT JOIN staff s ON s.staff_id = e.staff_id
    LEFT JOIN staff c ON c.staff_id = e.created_by
"""
# A staff member's own events and the clinic's; NULL scope (a manager) sees all.
VISIBLE = "(:scope IS NULL OR e.staff_id IS NULL OR e.staff_id = :scope)"


def list_events(connection: sqlite3.Connection, query: EventRange, scope: str | None = None) -> list[EventItem]:
    rows = connection.execute(
        f"""{EVENT_SELECT}
        WHERE e.event_date BETWEEN :date_from AND :date_to AND {VISIBLE}
        ORDER BY e.event_date, e.start_time IS NOT NULL, e.start_time, e.title, e.event_id""",
        {"date_from": query.date_from.isoformat(), "date_to": query.date_to.isoformat(), "scope": scope},
    ).fetchall()
    return [EventItem(**row) for row in rows]


def get_event(connection: sqlite3.Connection, event_id: str, scope: str | None = None) -> EventItem:
    row = connection.execute(
        f"{EVENT_SELECT} WHERE e.event_id = :event_id AND {VISIBLE}", {"event_id": event_id, "scope": scope},
    ).fetchone()
    if row is None:
        raise QueryError("not_found", f"Event {event_id} was not found.", 404)
    return EventItem(**row)


def changeable(connection: sqlite3.Connection, event_id: str, scope: str | None) -> EventItem:
    """The event, if this reader may change it: a manager any, other staff their own."""
    event = get_event(connection, event_id, scope)
    if scope is not None and event.staff_id != scope:
        raise QueryError("managers_only", "Only a manager changes events for the whole clinic.", 403)
    return event


def check_owner(staff_id: str | None, scope: str | None) -> None:
    if scope is not None and staff_id != scope:
        raise QueryError("managers_only", "Only a manager adds or moves events for others or the whole clinic.", 403)


def create_event(
    connection: sqlite3.Connection, body: EventCreate, scope: str | None = None, created_by: str | None = None,
) -> str:
    """Add an event in the caller's transaction. Staff who are not managers add their own,
    so their events default to themselves."""
    staff_id = body.staff_id if body.staff_id is not None or scope is None else scope
    check_owner(staff_id, scope)
    referenced(connection, "staff", staff_id)
    return insert(connection, "event", body, staff_id=staff_id, created_by=created_by)


def update_event(connection: sqlite3.Connection, event_id: str, body: EventUpdate, scope: str | None = None) -> None:
    changeable(connection, event_id, scope)
    values = body.changes()
    if "staff_id" in values:
        check_owner(values["staff_id"], scope)
        referenced(connection, "staff", values["staff_id"])
    update(connection, "event", event_id, values)


def delete_event(connection: sqlite3.Connection, event_id: str, scope: str | None = None) -> None:
    changeable(connection, event_id, scope)
    connection.execute("DELETE FROM schedule_events WHERE event_id = ?", [event_id])
