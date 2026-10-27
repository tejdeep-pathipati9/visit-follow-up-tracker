"""Fixed, parameterized searches behind the UI filter endpoints.

SQL text comes only from this module; request values are always bound as
parameters. Searches still run through repository.execute_query, so the
read-only authorizer and execution limits apply here as well.

Each search defines a `base` CTE with one row per record, then filters,
counts, sorts, and pages that CTE by its column names.
"""

from datetime import date
import sqlite3
from typing import get_args

from app import repository
from app.constants import (
    ALLOWED_ACTION_TYPES, DUE_SOON_DAYS, EPISODE_STATUSES, FOLLOWUP_FLAGS, FOLLOWUP_STATUSES,
)
from app.models import (
    Dashboard, DateRange, EpisodeSearch, EpisodeSort, EpisodeSummary, FollowUpCounts,
    FollowUpFilters, FollowUpGroup, FollowUpItem, FollowUpSearch, FollowUpSort, FollowUpStats,
    FollowUpStatsQuery, Page, PatientSearch, PatientSort, PatientSummary, PresetOption,
    QueryRequest, SearchOptions, SQLValue, StaffOption, StaffSearch, StaffSort, StaffSummary,
    StatsGroup, VisitSearch, VisitSort, VisitSummary,
)
from app.rules import calculate_flags, due_soon_end

MAX_ROWS = 1_000

FOLLOWUP_PRESETS: dict[str, tuple[str, dict[str, object]]] = {
    "overdue": ("Overdue", {"flag": ["overdue"]}),
    "overdue_30_plus": ("Overdue 30+ days", {"days_overdue_min": 30}),
    "due_today": ("Due today", {"status": ["open"], "due_within_days": 0}),
    "due_soon": (f"Due within {DUE_SOON_DAYS} days", {"flag": ["due_soon"]}),
    "due_this_week": ("Due within 7 days", {"status": ["open"], "due_within_days": 7}),
    "due_next_30_days": ("Due within 30 days", {"status": ["open"], "due_within_days": 30}),
    "unassigned": ("Unassigned", {"flag": ["unassigned"]}),
    "unassigned_overdue": ("Unassigned and overdue", {"flag": ["overdue"], "unassigned": True}),
    "open_labs": ("Open labs", {"status": ["open"], "action_type": ["lab"]}),
    "open_referrals": ("Open referrals", {"status": ["open"], "action_type": ["referral"]}),
    "open_rechecks": ("Open rechecks", {"status": ["open"], "action_type": ["recheck"]}),
    "completed_last_7_days": ("Completed in the last 7 days", {"status": ["done"], "completed_within_days": 7}),
    "completed_last_30_days": ("Completed in the last 30 days", {"status": ["done"], "completed_within_days": 30}),
    "open_episode_followups": ("Open follow-ups for active episodes", {"status": ["open"], "episode_status": "open"}),
}

FOLLOWUP_SORTS: dict[str, str] = {
    "due_date": "r.due_date, r.followup_id",
    "-due_date": "r.due_date DESC, r.followup_id",
    "visit_date": "r.visit_date, r.followup_id",
    "-visit_date": "r.visit_date DESC, r.followup_id",
    "patient_name": "r.patient_name, r.due_date, r.followup_id",
    "-patient_name": "r.patient_name DESC, r.due_date, r.followup_id",
    "assigned_staff_name": "r.assigned_staff_name IS NULL, r.assigned_staff_name, r.due_date, r.followup_id",
    "-assigned_staff_name": "r.assigned_staff_name IS NULL, r.assigned_staff_name DESC, r.due_date, r.followup_id",
    "action_type": "r.action_type, r.due_date, r.followup_id",
    "status": "r.status DESC, r.due_date, r.followup_id",
    "completed_at": "r.completed_at IS NULL, r.completed_at, r.followup_id",
    "-completed_at": "r.completed_at IS NULL, r.completed_at DESC, r.followup_id",
    "followup_id": "r.followup_id",
}
PATIENT_SORTS: dict[str, str] = {
    "name": "r.name, r.patient_id",
    "-name": "r.name DESC, r.patient_id",
    "patient_id": "r.patient_id",
    "last_visit_date": "r.last_visit_date IS NULL, r.last_visit_date, r.patient_id",
    "-last_visit_date": "r.last_visit_date IS NULL, r.last_visit_date DESC, r.patient_id",
    "next_due_date": "r.next_due_date IS NULL, r.next_due_date, r.patient_id",
    "-open_followups": "r.open_followups DESC, r.next_due_date, r.patient_id",
    "-overdue_followups": "r.overdue_followups DESC, r.next_due_date, r.patient_id",
    "-visit_count": "r.visit_count DESC, r.patient_id",
}
STAFF_SORTS: dict[str, str] = {
    "name": "r.name, r.staff_id",
    "-name": "r.name DESC, r.staff_id",
    "role": "r.role, r.name, r.staff_id",
    "-open_followups": "r.open_followups DESC, r.name, r.staff_id",
    "-overdue_followups": "r.overdue_followups DESC, r.name, r.staff_id",
    "-visit_count": "r.visit_count DESC, r.name, r.staff_id",
    "next_due_date": "r.next_due_date IS NULL, r.next_due_date, r.staff_id",
}
VISIT_SORTS: dict[str, str] = {
    "visit_date": "r.visit_date, r.visit_id",
    "-visit_date": "r.visit_date DESC, r.visit_id",
    "patient_name": "r.patient_name, r.visit_date DESC, r.visit_id",
    "staff_name": "r.staff_name IS NULL, r.staff_name, r.visit_date DESC, r.visit_id",
    "-followup_count": "r.followup_count DESC, r.visit_date DESC, r.visit_id",
    "-open_followups": "r.open_followups DESC, r.visit_date DESC, r.visit_id",
}
EPISODE_SORTS: dict[str, str] = {
    "opened_at": "r.opened_at, r.episode_id",
    "-opened_at": "r.opened_at DESC, r.episode_id",
    "last_visit_date": "r.last_visit_date IS NULL, r.last_visit_date, r.episode_id",
    "-last_visit_date": "r.last_visit_date IS NULL, r.last_visit_date DESC, r.episode_id",
    "patient_name": "r.patient_name, r.opened_at DESC, r.episode_id",
    "-open_followups": "r.open_followups DESC, r.episode_id",
    "-visit_count": "r.visit_count DESC, r.episode_id",
    "-days_open": "r.days_open DESC, r.episode_id",
}

# Group key expression, display label expression, and whether groups sort by key.
FOLLOWUP_GROUPS: dict[str, tuple[str, str, bool]] = {
    "action_type": ("r.action_type", "r.action_type", False),
    "status": ("r.status", "r.status", False),
    "assigned_staff": ("r.assigned_staff_id", "COALESCE(r.assigned_staff_name, 'Unassigned')", False),
    "assigned_staff_role": ("r.assigned_staff_role", "COALESCE(r.assigned_staff_role, 'Unassigned')", False),
    "visit_staff": ("r.visit_staff_id", "COALESCE(r.visit_staff_name, 'Unknown')", False),
    "patient": ("r.patient_id", "r.patient_name", False),
    "episode": ("r.episode_id", "r.episode_description", False),
    "due_date": ("r.due_date", "r.due_date", True),
    "due_week": ("strftime('%Y-W%W', r.due_date)", "strftime('%Y-W%W', r.due_date)", True),
    "due_month": ("substr(r.due_date, 1, 7)", "substr(r.due_date, 1, 7)", True),
    "visit_month": ("substr(r.visit_date, 1, 7)", "substr(r.visit_date, 1, 7)", True),
    "completed_month": ("substr(r.completed_at, 1, 7)", "substr(r.completed_at, 1, 7)", True),
}

for literal, names in (
    (FollowUpSort, FOLLOWUP_SORTS), (PatientSort, PATIENT_SORTS), (StaffSort, STAFF_SORTS),
    (VisitSort, VISIT_SORTS), (EpisodeSort, EPISODE_SORTS), (FollowUpGroup, FOLLOWUP_GROUPS),
):
    assert set(get_args(literal)) == set(names), f"{literal} and its SQL mapping differ"

# Follow-up counts per group; `f` is the followups table and :as_of/:soon_end are bound.
COUNT_COLUMNS = {
    "followup_count": "COUNT({f}.followup_id)",
    "open_followups": "COALESCE(SUM({f}.status = 'open'), 0)",
    "done_followups": "COALESCE(SUM({f}.status = 'done'), 0)",
    "overdue_followups": "COALESCE(SUM({f}.status = 'open' AND {f}.due_date < :as_of), 0)",
    "due_today_followups": "COALESCE(SUM({f}.status = 'open' AND {f}.due_date = :as_of), 0)",
    "due_soon_followups": "COALESCE(SUM({f}.status = 'open' AND {f}.due_date BETWEEN :as_of AND :soon_end), 0)",
    "unassigned_followups": "COALESCE(SUM({f}.status = 'open' AND {f}.assigned_staff_id IS NULL), 0)",
    "next_due_date": "MIN(CASE WHEN {f}.status = 'open' THEN {f}.due_date END)",
}
FLAG_COUNT_COLUMNS = {
    "overdue": "overdue_followups", "due_soon": "due_soon_followups", "unassigned": "unassigned_followups",
}


def counts_sql(f: str) -> str:
    return ",\n".join(f"{sql.format(f=f)} AS {name}" for name, sql in COUNT_COLUMNS.items())


def joined_counts_sql(alias: str) -> str:
    """Select counts from a LEFT JOINed aggregate, using 0 when it has no row."""
    return ",\n".join(
        f"{alias}.{name}" if name == "next_due_date" else f"COALESCE({alias}.{name}, 0) AS {name}"
        for name in COUNT_COLUMNS
    )


FOLLOWUP_BASE = """
WITH base AS (
    SELECT f.followup_id, f.status, f.action_type, f.due_date, f.completed_at,
           f.visit_id, v.visit_date, v.notes AS visit_notes,
           v.patient_id, p.name AS patient_name,
           v.episode_id, e.description AS episode_description, e.closed_at AS episode_closed_at,
           f.assigned_staff_id, a.name AS assigned_staff_name, a.role AS assigned_staff_role,
           v.staff_id AS visit_staff_id, vs.name AS visit_staff_name, vs.role AS visit_staff_role
    FROM followups f
    JOIN visits v ON v.visit_id = f.visit_id
    JOIN patients p ON p.patient_id = v.patient_id
    JOIN episodes e ON e.episode_id = v.episode_id
    LEFT JOIN staff a ON a.staff_id = f.assigned_staff_id
    LEFT JOIN staff vs ON vs.staff_id = v.staff_id
)
"""

PATIENT_BASE = f"""
WITH visit_stats AS (
    SELECT patient_id, COUNT(*) AS visit_count,
           MIN(visit_date) AS first_visit_date, MAX(visit_date) AS last_visit_date
    FROM visits GROUP BY patient_id
), episode_stats AS (
    SELECT patient_id, COUNT(*) AS episode_count, SUM(closed_at IS NULL) AS open_episode_count
    FROM episodes GROUP BY patient_id
), followup_stats AS (
    SELECT v.patient_id, {counts_sql("f")}
    FROM followups f JOIN visits v ON v.visit_id = f.visit_id
    GROUP BY v.patient_id
), base AS (
    SELECT p.patient_id, p.name, p.phone, p.email,
           COALESCE(es.episode_count, 0) AS episode_count,
           COALESCE(es.open_episode_count, 0) AS open_episode_count,
           COALESCE(vs.visit_count, 0) AS visit_count, vs.first_visit_date, vs.last_visit_date,
           {joined_counts_sql("fs")}
    FROM patients p
    LEFT JOIN visit_stats vs ON vs.patient_id = p.patient_id
    LEFT JOIN episode_stats es ON es.patient_id = p.patient_id
    LEFT JOIN followup_stats fs ON fs.patient_id = p.patient_id
)
"""

STAFF_BASE = f"""
WITH visit_stats AS (
    SELECT staff_id, COUNT(*) AS visit_count, COUNT(DISTINCT patient_id) AS patient_count,
           MAX(visit_date) AS last_visit_date
    FROM visits WHERE staff_id IS NOT NULL GROUP BY staff_id
), followup_stats AS (
    SELECT f.assigned_staff_id AS staff_id, {counts_sql("f")}
    FROM followups f WHERE f.assigned_staff_id IS NOT NULL
    GROUP BY f.assigned_staff_id
), base AS (
    SELECT s.staff_id, s.name, s.role,
           COALESCE(vs.visit_count, 0) AS visit_count,
           COALESCE(vs.patient_count, 0) AS patient_count, vs.last_visit_date,
           {joined_counts_sql("fs")}
    FROM staff s
    LEFT JOIN visit_stats vs ON vs.staff_id = s.staff_id
    LEFT JOIN followup_stats fs ON fs.staff_id = s.staff_id
)
"""

VISIT_BASE = f"""
WITH followup_stats AS (
    SELECT f.visit_id, {counts_sql("f")}
    FROM followups f GROUP BY f.visit_id
), base AS (
    SELECT v.visit_id, v.visit_date, v.notes, v.patient_id, p.name AS patient_name,
           v.episode_id, e.description AS episode_description, e.closed_at AS episode_closed_at,
           v.staff_id, s.name AS staff_name, s.role AS staff_role,
           {joined_counts_sql("fs")}
    FROM visits v
    JOIN patients p ON p.patient_id = v.patient_id
    JOIN episodes e ON e.episode_id = v.episode_id
    LEFT JOIN staff s ON s.staff_id = v.staff_id
    LEFT JOIN followup_stats fs ON fs.visit_id = v.visit_id
)
"""

EPISODE_BASE = f"""
WITH visit_stats AS (
    SELECT episode_id, COUNT(*) AS visit_count,
           MIN(visit_date) AS first_visit_date, MAX(visit_date) AS last_visit_date
    FROM visits GROUP BY episode_id
), followup_stats AS (
    SELECT v.episode_id, {counts_sql("f")}
    FROM followups f JOIN visits v ON v.visit_id = f.visit_id
    GROUP BY v.episode_id
), base AS (
    SELECT e.episode_id, e.patient_id, p.name AS patient_name, e.description,
           e.opened_at, e.closed_at,
           CASE WHEN e.closed_at IS NULL THEN 'open' ELSE 'closed' END AS status,
           CAST(julianday(COALESCE(e.closed_at, :as_of)) - julianday(e.opened_at) AS INTEGER) AS days_open,
           COALESCE(vs.visit_count, 0) AS visit_count, vs.first_visit_date, vs.last_visit_date,
           {joined_counts_sql("fs")}
    FROM episodes e
    JOIN patients p ON p.patient_id = e.patient_id
    LEFT JOIN visit_stats vs ON vs.episode_id = e.episode_id
    LEFT JOIN followup_stats fs ON fs.episode_id = e.episode_id
)
"""


def shift(day: date, days: int) -> date:
    return date.fromordinal(min(max(day.toordinal() + days, 1), date.max.toordinal()))


class Where:
    """Collect AND-ed conditions on `base r` with automatically named parameters."""

    def __init__(self, as_of: date):
        self.clauses: list[str] = []
        self.params: dict[str, SQLValue] = {
            "as_of": as_of.isoformat(), "soon_end": due_soon_end(as_of).isoformat(),
        }

    def bind(self, value: SQLValue | date) -> str:
        name = f"p{len(self.params)}"
        self.params[name] = value.isoformat() if isinstance(value, date) else value
        return ":" + name

    def add(self, clause: str, *values: SQLValue | date) -> None:
        self.clauses.append(clause.format(*(self.bind(value) for value in values)))

    def any_of(self, column: str, values: list) -> None:
        if values:
            self.add(f"{column} IN ({', '.join('{}' for _ in values)})", *values)

    def contains(self, text: str | None, *columns: str) -> None:
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            name = self.bind(f"%{escaped}%")
            self.clauses.append("(" + " OR ".join(f"{column} LIKE {name} ESCAPE '\\'" for column in columns) + ")")

    def range(self, column: str, low: object | None, high: object | None) -> None:
        if low is not None:
            self.add(f"{column} >= {{}}", low)
        if high is not None:
            self.add(f"{column} <= {{}}", high)

    def flagged(self, flags: list[str]) -> None:
        """Keep aggregate rows with at least one open follow-up carrying any flag."""
        if flags:
            self.clauses.append("(" + " OR ".join(f"r.{FLAG_COUNT_COLUMNS[flag]} > 0" for flag in flags) + ")")

    def sql(self) -> str:
        return "WHERE " + "\nAND ".join(self.clauses) if self.clauses else ""


def fetch(connection: sqlite3.Connection, sql: str, params: dict[str, SQLValue], max_rows: int = MAX_ROWS) -> list[dict]:
    result = repository.execute_query(connection, QueryRequest(query=sql, parameters=params, max_rows=max_rows))
    return [dict(zip(result.columns, row)) for row in result.rows]


def page(
    connection: sqlite3.Connection, base: str, where: Where, order_by: str, limit: int, offset: int,
) -> tuple[list[dict], int]:
    condition = where.sql()
    total = fetch(connection, f"{base} SELECT COUNT(*) AS total FROM base r {condition}", where.params)[0]["total"]
    rows = fetch(
        connection,
        f"{base} SELECT r.* FROM base r {condition} ORDER BY {order_by} LIMIT :limit OFFSET :offset",
        {**where.params, "limit": limit, "offset": offset},
        max_rows=limit,
    )
    return rows, total


def staff_involved(where: Where, column: str, staff_ids: list[str]) -> None:
    """Keep rows whose record had a visit by, or a follow-up assigned to, any staff member."""
    if not staff_ids:
        return
    visits = ", ".join(where.bind(staff_id) for staff_id in staff_ids)
    assigned = ", ".join(where.bind(staff_id) for staff_id in staff_ids)
    key = column.split(".")[-1]
    where.clauses.append(
        f"{column} IN (SELECT v.{key} FROM visits v WHERE v.staff_id IN ({visits}) "
        f"UNION SELECT v.{key} FROM followups f JOIN visits v ON v.visit_id = f.visit_id "
        f"WHERE f.assigned_staff_id IN ({assigned}))"
    )


def open_action_types(where: Where, column: str, action_types: list[str], status_open: bool = True) -> None:
    if not action_types:
        return
    key = column.split(".")[-1]
    types = ", ".join(where.bind(action_type) for action_type in action_types)
    status = " AND f.status = 'open'" if status_open else ""
    where.clauses.append(
        f"{column} IN (SELECT v.{key} FROM followups f JOIN visits v ON v.visit_id = f.visit_id "
        f"WHERE f.action_type IN ({types}){status})"
    )


# --- Follow-ups ---------------------------------------------------------------

def followup_where(filters: FollowUpFilters, where: Where) -> None:
    as_of = filters.as_of_date
    where.contains(
        filters.q, "r.followup_id", "r.patient_id", "r.patient_name", "r.assigned_staff_name",
        "r.visit_staff_name", "r.episode_description", "r.visit_notes",
    )
    where.any_of("r.followup_id", filters.followup_id)
    where.any_of("r.patient_id", filters.patient_id)
    where.contains(filters.patient_name, "r.patient_name")
    where.any_of("r.visit_id", filters.visit_id)
    where.any_of("r.episode_id", filters.episode_id)
    where.contains(filters.episode_description, "r.episode_description")
    if filters.episode_status is not None:
        where.add(f"r.episode_closed_at IS {'' if filters.episode_status == 'open' else 'NOT '}NULL")
    where.any_of("r.action_type", filters.action_type)
    where.any_of("r.status", filters.status)
    if filters.flag:
        # Same definitions as app/rules; only open follow-ups carry flags.
        conditions = {
            "overdue": "r.due_date < :as_of",
            "due_soon": "r.due_date BETWEEN :as_of AND :soon_end",
            "unassigned": "r.assigned_staff_id IS NULL",
        }
        where.add("r.status = 'open' AND (" + " OR ".join(conditions[flag] for flag in filters.flag) + ")")
    if filters.staff_id:
        assigned = ", ".join(where.bind(staff_id) for staff_id in filters.staff_id)
        visit = ", ".join(where.bind(staff_id) for staff_id in filters.staff_id)
        where.add(f"(r.assigned_staff_id IN ({assigned}) OR r.visit_staff_id IN ({visit}))")
    where.contains(filters.staff_name, "r.assigned_staff_name", "r.visit_staff_name")
    where.any_of("r.assigned_staff_id", filters.assigned_staff_id)
    where.contains(filters.assigned_staff_name, "r.assigned_staff_name")
    where.any_of("r.assigned_staff_role", filters.assigned_staff_role)
    if filters.unassigned is not None:
        where.add(f"r.assigned_staff_id IS {'' if filters.unassigned else 'NOT '}NULL")
    where.any_of("r.visit_staff_id", filters.visit_staff_id)
    where.contains(filters.visit_staff_name, "r.visit_staff_name")
    where.any_of("r.visit_staff_role", filters.visit_staff_role)
    where.contains(filters.notes, "r.visit_notes")
    where.range("r.due_date", filters.due_from, filters.due_to)
    if filters.due_within_days is not None:
        where.range("r.due_date", as_of, shift(as_of, filters.due_within_days))
    if filters.days_overdue_min is not None or filters.days_overdue_max is not None:
        where.add("r.status = 'open' AND r.due_date < :as_of")
        where.range(
            "r.due_date",
            None if filters.days_overdue_max is None else shift(as_of, -filters.days_overdue_max),
            None if filters.days_overdue_min is None else shift(as_of, -filters.days_overdue_min),
        )
    where.range("r.visit_date", filters.visit_from, filters.visit_to)
    where.range("substr(r.completed_at, 1, 10)", filters.completed_from, filters.completed_to)
    if filters.completed_within_days is not None:
        where.range("substr(r.completed_at, 1, 10)", shift(as_of, -filters.completed_within_days), as_of)
    if filters.preset is not None:
        _, preset = FOLLOWUP_PRESETS[filters.preset]
        followup_where(FollowUpFilters(**preset, as_of_date=as_of), where)


def to_followup(row: dict, as_of: date) -> FollowUpItem:
    item = FollowUpItem(**row, days_until_due=(date.fromisoformat(row["due_date"]) - as_of).days)
    item.flags = calculate_flags(item, as_of)
    return item


def search_followups(connection: sqlite3.Connection, search: FollowUpSearch) -> Page[FollowUpItem]:
    where = Where(search.as_of_date)
    followup_where(search, where)
    rows, total = page(connection, FOLLOWUP_BASE, where, FOLLOWUP_SORTS[search.sort], search.limit, search.offset)
    return Page[FollowUpItem](
        items=[to_followup(row, search.as_of_date) for row in rows],
        total=total, limit=search.limit, offset=search.offset, as_of_date=search.as_of_date,
    )


def followup_stats(connection: sqlite3.Connection, query: FollowUpStatsQuery) -> FollowUpStats:
    where = Where(query.as_of_date)
    followup_where(query, where)
    condition = where.sql()
    counts = counts_sql("r")
    totals = fetch(connection, f"{FOLLOWUP_BASE} SELECT {counts} FROM base r {condition}", where.params)[0]
    groups: list[StatsGroup] = []
    if query.group_by is not None:
        key, label, by_key = FOLLOWUP_GROUPS[query.group_by]
        order = "key IS NULL, key" if by_key else "followup_count DESC, label, key"
        groups = [StatsGroup(**row) for row in fetch(connection, f"""
            {FOLLOWUP_BASE}
            SELECT {key} AS key, MIN({label}) AS label, {counts}
            FROM base r {condition} GROUP BY {key} ORDER BY {order}
        """, where.params)]
    return FollowUpStats(
        as_of_date=query.as_of_date, group_by=query.group_by, totals=FollowUpCounts(**totals), groups=groups,
    )


# --- Patients, staff, visits, episodes ----------------------------------------

def search_patients(connection: sqlite3.Connection, search: PatientSearch) -> Page[PatientSummary]:
    where = Where(search.as_of_date)
    where.contains(search.q, "r.patient_id", "r.name", "r.phone", "r.email")
    where.any_of("r.patient_id", search.patient_id)
    where.contains(search.name, "r.name")
    staff_involved(where, "r.patient_id", search.staff_id)
    where.flagged(search.flag)
    open_action_types(where, "r.patient_id", search.open_action_type)
    if search.has_open_episode is not None:
        where.add(f"r.open_episode_count {'>' if search.has_open_episode else '='} 0")
    where.range("r.open_followups", search.open_followups_min, search.open_followups_max)
    where.range("r.overdue_followups", search.overdue_followups_min, None)
    where.range("r.visit_count", search.visit_count_min, search.visit_count_max)
    where.range("r.last_visit_date", search.last_visit_from, search.last_visit_to)
    where.range("r.next_due_date", search.next_due_from, search.next_due_to)
    rows, total = page(connection, PATIENT_BASE, where, PATIENT_SORTS[search.sort], search.limit, search.offset)
    return Page[PatientSummary](
        items=[PatientSummary(**row) for row in rows],
        total=total, limit=search.limit, offset=search.offset, as_of_date=search.as_of_date,
    )


def search_staff(connection: sqlite3.Connection, search: StaffSearch) -> Page[StaffSummary]:
    where = Where(search.as_of_date)
    where.contains(search.q, "r.staff_id", "r.name")
    where.any_of("r.staff_id", search.staff_id)
    where.any_of("r.role", search.role)
    where.flagged(search.flag)
    where.range("r.open_followups", search.open_followups_min, search.open_followups_max)
    where.range("r.overdue_followups", search.overdue_followups_min, None)
    where.range("r.visit_count", search.visit_count_min, None)
    rows, total = page(connection, STAFF_BASE, where, STAFF_SORTS[search.sort], search.limit, search.offset)
    return Page[StaffSummary](
        items=[StaffSummary(**row) for row in rows],
        total=total, limit=search.limit, offset=search.offset, as_of_date=search.as_of_date,
    )


def search_visits(connection: sqlite3.Connection, search: VisitSearch) -> Page[VisitSummary]:
    where = Where(search.as_of_date)
    where.contains(
        search.q, "r.visit_id", "r.patient_id", "r.patient_name", "r.staff_name",
        "r.episode_description", "r.notes",
    )
    where.any_of("r.visit_id", search.visit_id)
    where.any_of("r.patient_id", search.patient_id)
    where.contains(search.patient_name, "r.patient_name")
    where.any_of("r.episode_id", search.episode_id)
    if search.episode_status is not None:
        where.add(f"r.episode_closed_at IS {'' if search.episode_status == 'open' else 'NOT '}NULL")
    where.any_of("r.staff_id", search.staff_id)
    where.contains(search.staff_name, "r.staff_name")
    where.any_of("r.staff_role", search.staff_role)
    where.contains(search.notes, "r.notes")
    where.range("r.visit_date", search.visit_from, search.visit_to)
    if search.visit_within_days is not None:
        where.range("r.visit_date", shift(search.as_of_date, -search.visit_within_days), search.as_of_date)
    where.flagged(search.flag)
    open_action_types(where, "r.visit_id", search.followup_action_type, status_open=False)
    where.range("r.followup_count", search.followup_count_min, search.followup_count_max)
    where.range("r.open_followups", search.open_followups_min, None)
    rows, total = page(connection, VISIT_BASE, where, VISIT_SORTS[search.sort], search.limit, search.offset)
    return Page[VisitSummary](
        items=[VisitSummary(**row) for row in rows],
        total=total, limit=search.limit, offset=search.offset, as_of_date=search.as_of_date,
    )


def search_episodes(connection: sqlite3.Connection, search: EpisodeSearch) -> Page[EpisodeSummary]:
    where = Where(search.as_of_date)
    where.contains(search.q, "r.episode_id", "r.patient_id", "r.patient_name", "r.description")
    where.any_of("r.episode_id", search.episode_id)
    where.any_of("r.patient_id", search.patient_id)
    where.contains(search.patient_name, "r.patient_name")
    where.contains(search.description, "r.description")
    if search.status is not None:
        where.add("r.status = {}", search.status)
    staff_involved(where, "r.episode_id", search.staff_id)
    where.flagged(search.flag)
    where.range("r.opened_at", search.opened_from, search.opened_to)
    where.range("r.closed_at", search.closed_from, search.closed_to)
    where.range("r.days_open", search.days_open_min, search.days_open_max)
    where.range("r.visit_count", search.visit_count_min, search.visit_count_max)
    where.range("r.open_followups", search.open_followups_min, None)
    rows, total = page(connection, EPISODE_BASE, where, EPISODE_SORTS[search.sort], search.limit, search.offset)
    return Page[EpisodeSummary](
        items=[EpisodeSummary(**row) for row in rows],
        total=total, limit=search.limit, offset=search.offset, as_of_date=search.as_of_date,
    )


# --- Dashboard and dropdown options -------------------------------------------

def dashboard(connection: sqlite3.Connection, as_of: date) -> Dashboard:
    where = Where(as_of)
    params = {
        **where.params,
        "week_start": shift(as_of, -7).isoformat(),
        "month_start": shift(as_of, -30).isoformat(),
    }
    followups = fetch(connection, f"SELECT {counts_sql('f')} FROM followups f", params)[0]
    row = fetch(connection, f"""
        {PATIENT_BASE},
        staff_overdue AS (
            SELECT COUNT(DISTINCT assigned_staff_id) AS count FROM followups
            WHERE status = 'open' AND due_date < :as_of AND assigned_staff_id IS NOT NULL
        )
        SELECT
            (SELECT COUNT(*) FROM followups
             WHERE status = 'done' AND substr(completed_at, 1, 10) BETWEEN :week_start AND :as_of)
                AS completed_last_7_days,
            (SELECT COUNT(*) FROM base) AS patients,
            (SELECT COUNT(*) FROM base WHERE open_followups > 0) AS patients_with_open_followups,
            (SELECT COUNT(*) FROM base WHERE overdue_followups > 0) AS patients_with_overdue,
            (SELECT COUNT(*) FROM episodes WHERE closed_at IS NULL) AS open_episodes,
            (SELECT COUNT(*) FROM visits WHERE visit_date BETWEEN :month_start AND :as_of)
                AS visits_last_30_days,
            (SELECT count FROM staff_overdue) AS staff_with_overdue
    """, params)[0]
    return Dashboard(as_of_date=as_of, followups=FollowUpCounts(**followups), **row)


def options(connection: sqlite3.Connection, as_of: date) -> SearchOptions:
    staff = [StaffOption(**row) for row in fetch(
        connection, "SELECT staff_id, name, role FROM staff ORDER BY name, staff_id", {},
    )]
    bounds = fetch(connection, """
        SELECT (SELECT MIN(due_date) FROM followups) AS due_min,
               (SELECT MAX(due_date) FROM followups) AS due_max,
               (SELECT MIN(visit_date) FROM visits) AS visit_min,
               (SELECT MAX(visit_date) FROM visits) AS visit_max,
               (SELECT MIN(opened_at) FROM episodes) AS opened_min,
               (SELECT MAX(opened_at) FROM episodes) AS opened_max,
               (SELECT MIN(substr(completed_at, 1, 10)) FROM followups) AS completed_min,
               (SELECT MAX(substr(completed_at, 1, 10)) FROM followups) AS completed_max
    """, {})[0]
    return SearchOptions(
        as_of_date=as_of,
        due_soon_days=DUE_SOON_DAYS,
        action_types=list(ALLOWED_ACTION_TYPES),
        followup_statuses=list(FOLLOWUP_STATUSES),
        followup_flags=list(FOLLOWUP_FLAGS),
        episode_statuses=list(EPISODE_STATUSES),
        staff=staff,
        staff_roles=sorted({option.role for option in staff}),
        date_ranges={
            name: DateRange(min=bounds[f"{name}_min"], max=bounds[f"{name}_max"])
            for name in ("due", "visit", "opened", "completed")
        },
        presets=[
            PresetOption(name=name, label=label, filters=filters)
            for name, (label, filters) in FOLLOWUP_PRESETS.items()
        ],
        sorts={
            "followups": list(FOLLOWUP_SORTS), "patients": list(PATIENT_SORTS),
            "staff": list(STAFF_SORTS), "visits": list(VISIT_SORTS), "episodes": list(EPISODE_SORTS),
        },
        followup_groups=list(FOLLOWUP_GROUPS),
        max_limit=MAX_ROWS,
    )
