"""Application services for UI searches, record changes, and natural-language questions."""

from datetime import date
from functools import partial
import logging
import sqlite3
from typing import Any

from pydantic import ValidationError

from app import export, repository, schedule, search, writes
from app.ingestion import loader
from app.ingestion.settings import app_settings
from app.ai import QueryAssistant
from app.models import (
    AskRequest, AskResponse, Dashboard, EpisodeCreate, EpisodeDetail, EpisodeHistory,
    EventCreate, EventItem, EventRange, EventUpdate,
    EpisodeSearch, EpisodeSummary, EpisodeUpdate, FollowUpCreate, FollowUpDetail, FollowUpItem,
    FollowUpSearch, FollowUpStats, FollowUpStatsQuery, FollowUpUpdate, Page, PatientCreate,
    PatientDetail, PatientSearch, PatientSummary, PatientUpdate, QueryRequest, QueryResponse,
    ImportResult, Rejection, Report, ReportSection, SearchOptions, StaffCreate, StaffDetail, StaffSearch, StaffSummary, StaffUpdate, VisitCreate,
    VisitDetail, VisitHistory, VisitSearch, VisitSummary, VisitUpdate,
)
from app.repository import QueryError

logger = logging.getLogger(__name__)
RECENT_VISITS = 20


def query(connection: sqlite3.Connection, request: QueryRequest) -> QueryResponse:
    """Run server-built SQL; not exposed as an HTTP endpoint."""
    return repository.execute_query(connection, request)


def schema(connection: sqlite3.Connection) -> str:
    return repository.schema_text(connection)


def search_followups(connection: sqlite3.Connection, filters: FollowUpSearch, scope: str | None = None) -> Page[FollowUpItem]:
    return search.search_followups(connection, filters, scope)


def followup_stats(connection: sqlite3.Connection, filters: FollowUpStatsQuery, scope: str | None = None) -> FollowUpStats:
    return search.followup_stats(connection, filters, scope)


def search_patients(connection: sqlite3.Connection, filters: PatientSearch, scope: str | None = None) -> Page[PatientSummary]:
    return search.search_patients(connection, filters, scope)


def search_staff(connection: sqlite3.Connection, filters: StaffSearch, scope: str | None = None) -> Page[StaffSummary]:
    return search.search_staff(connection, filters, scope)


def search_visits(connection: sqlite3.Connection, filters: VisitSearch, scope: str | None = None) -> Page[VisitSummary]:
    return search.search_visits(connection, filters, scope)


def search_episodes(connection: sqlite3.Connection, filters: EpisodeSearch, scope: str | None = None) -> Page[EpisodeSummary]:
    return search.search_episodes(connection, filters, scope)


def dashboard(connection: sqlite3.Connection, as_of: date, scope: str | None = None) -> Dashboard:
    return search.dashboard(connection, as_of, scope)


def options(connection: sqlite3.Connection, as_of: date) -> SearchOptions:
    return search.options(connection, as_of)


def only(items: list, kind: str, record_id: str):
    if not items:
        raise QueryError("not_found", f"{kind} {record_id} was not found.", 404)
    return items[0]


def histories(connection: sqlite3.Connection, as_of: date, scope: str | None, **match: list[str]) -> list[EpisodeHistory]:
    """Episodes with their visits and follow-ups, oldest first, for one patient or episode."""
    limit = search.MAX_ROWS
    episodes = search.search_episodes(connection, EpisodeSearch(**match, as_of_date=as_of, limit=limit, sort="opened_at"), scope)
    visits = search.search_visits(connection, VisitSearch(**match, as_of_date=as_of, limit=limit, sort="visit_date"), scope)
    followups = search.search_followups(connection, FollowUpSearch(**match, as_of_date=as_of, limit=limit), scope)
    by_visit: dict[str, list[FollowUpItem]] = {}
    for followup in followups.items:
        by_visit.setdefault(followup.visit_id, []).append(followup)
    by_episode: dict[str, list[VisitHistory]] = {}
    for visit in visits.items:
        by_episode.setdefault(visit.episode_id, []).append(
            VisitHistory(**visit.model_dump(), followups=by_visit.get(visit.visit_id, []))
        )
    return [
        EpisodeHistory(**episode.model_dump(), visits=by_episode.get(episode.episode_id, []))
        for episode in episodes.items
    ]


def followup_detail(connection: sqlite3.Connection, followup_id: str, as_of: date, scope: str | None = None) -> FollowUpDetail:
    found = search.search_followups(connection, FollowUpSearch(followup_id=[followup_id], as_of_date=as_of, limit=1), scope)
    followup = only(found.items, "Follow-up", followup_id)
    patient = search.search_patients(connection, PatientSearch(patient_id=[followup.patient_id], as_of_date=as_of, limit=1), scope)
    episode = search.search_followups(
        connection, FollowUpSearch(episode_id=[followup.episode_id], as_of_date=as_of, limit=search.MAX_ROWS), scope,
    )
    return FollowUpDetail(
        followup=followup,
        patient=patient.items[0],
        episode_followups=[item for item in episode.items if item.followup_id != followup_id],
        history=search.followup_history(connection, followup_id),
    )


def patient_detail(connection: sqlite3.Connection, patient_id: str, as_of: date, scope: str | None = None) -> PatientDetail:
    found = search.search_patients(connection, PatientSearch(patient_id=[patient_id], as_of_date=as_of, limit=1), scope)
    return PatientDetail(
        patient=only(found.items, "Patient", patient_id),
        episodes=histories(connection, as_of, scope, patient_id=[patient_id]),
    )


def staff_detail(connection: sqlite3.Connection, staff_id: str, as_of: date, scope: str | None = None) -> StaffDetail:
    found = search.search_staff(connection, StaffSearch(staff_id=[staff_id], as_of_date=as_of, limit=1), scope)
    staff = only(found.items, "Staff member", staff_id)
    assigned = search.search_followups(connection, FollowUpSearch(
        assigned_staff_id=[staff_id], status=["open"], as_of_date=as_of, limit=search.MAX_ROWS,
    ), scope)
    visits = search.search_visits(connection, VisitSearch(
        staff_id=[staff_id], as_of_date=as_of, limit=RECENT_VISITS, sort="-visit_date",
    ), scope)
    return StaffDetail(staff=staff, open_followups=assigned.items, recent_visits=visits.items)


def episode_detail(connection: sqlite3.Connection, episode_id: str, as_of: date, scope: str | None = None) -> EpisodeDetail:
    episodes = histories(connection, as_of, scope, episode_id=[episode_id])
    return EpisodeDetail(episode=only(episodes, "Episode", episode_id))


def visit_detail(connection: sqlite3.Connection, visit_id: str, as_of: date, scope: str | None = None) -> VisitDetail:
    found = search.search_visits(connection, VisitSearch(visit_id=[visit_id], as_of_date=as_of, limit=1), scope)
    visit = only(found.items, "Visit", visit_id)
    followups = search.search_followups(
        connection, FollowUpSearch(visit_id=[visit_id], as_of_date=as_of, limit=search.MAX_ROWS), scope,
    )
    return VisitDetail(visit=VisitHistory(**visit.model_dump(), followups=followups.items))


# --- Record changes: commit, then return the saved record as the searches show it.

def saved_patient(connection: sqlite3.Connection, patient_id: str, as_of: date) -> PatientSummary:
    connection.commit()
    return search.search_patients(connection, PatientSearch(patient_id=[patient_id], as_of_date=as_of, limit=1)).items[0]


def saved_staff(connection: sqlite3.Connection, staff_id: str, as_of: date) -> StaffSummary:
    connection.commit()
    return search.search_staff(connection, StaffSearch(staff_id=[staff_id], as_of_date=as_of, limit=1)).items[0]


def saved_episode(connection: sqlite3.Connection, episode_id: str, as_of: date) -> EpisodeSummary:
    connection.commit()
    return search.search_episodes(connection, EpisodeSearch(episode_id=[episode_id], as_of_date=as_of, limit=1)).items[0]


def saved_visit(connection: sqlite3.Connection, visit_id: str, as_of: date) -> VisitSummary:
    connection.commit()
    return search.search_visits(connection, VisitSearch(visit_id=[visit_id], as_of_date=as_of, limit=1)).items[0]


def saved_followup(connection: sqlite3.Connection, followup_id: str, as_of: date) -> FollowUpItem:
    connection.commit()
    return search.search_followups(
        connection, FollowUpSearch(followup_id=[followup_id], as_of_date=as_of, limit=1),
    ).items[0]


def create_patient(connection: sqlite3.Connection, body: PatientCreate, as_of: date) -> PatientSummary:
    return saved_patient(connection, writes.create_patient(connection, body), as_of)


def update_patient(connection: sqlite3.Connection, patient_id: str, body: PatientUpdate, as_of: date) -> PatientSummary:
    writes.update_patient(connection, patient_id, body)
    return saved_patient(connection, patient_id, as_of)


def create_staff(connection: sqlite3.Connection, body: StaffCreate, as_of: date) -> StaffSummary:
    return saved_staff(connection, writes.create_staff(connection, body), as_of)


def update_staff(connection: sqlite3.Connection, staff_id: str, body: StaffUpdate, as_of: date) -> StaffSummary:
    writes.update_staff(connection, staff_id, body)
    return saved_staff(connection, staff_id, as_of)


def create_episode(connection: sqlite3.Connection, body: EpisodeCreate, as_of: date) -> EpisodeSummary:
    return saved_episode(connection, writes.create_episode(connection, body), as_of)


def update_episode(connection: sqlite3.Connection, episode_id: str, body: EpisodeUpdate, as_of: date) -> EpisodeSummary:
    writes.update_episode(connection, episode_id, body)
    return saved_episode(connection, episode_id, as_of)


def create_visit(connection: sqlite3.Connection, body: VisitCreate, as_of: date) -> VisitSummary:
    return saved_visit(connection, writes.create_visit(connection, body), as_of)


def update_visit(connection: sqlite3.Connection, visit_id: str, body: VisitUpdate, as_of: date) -> VisitSummary:
    writes.update_visit(connection, visit_id, body)
    return saved_visit(connection, visit_id, as_of)


def create_followup(connection: sqlite3.Connection, body: FollowUpCreate, as_of: date) -> FollowUpItem:
    return saved_followup(connection, writes.create_followup(connection, body), as_of)


def update_followup(
    connection: sqlite3.Connection, followup_id: str, body: FollowUpUpdate, as_of: date,
    scope: str | None = None, changed_by: str | None = None,
) -> FollowUpItem:
    writes.update_followup(connection, followup_id, body, scope, changed_by)
    return saved_followup(connection, followup_id, as_of)


def events(connection: sqlite3.Connection, query: EventRange, scope: str | None = None) -> list[EventItem]:
    return schedule.list_events(connection, query, scope)


def create_event(
    connection: sqlite3.Connection, body: EventCreate, scope: str | None = None, created_by: str | None = None,
) -> EventItem:
    event_id = schedule.create_event(connection, body, scope, created_by)
    connection.commit()
    return schedule.get_event(connection, event_id)


def update_event(connection: sqlite3.Connection, event_id: str, body: EventUpdate, scope: str | None = None) -> EventItem:
    schedule.update_event(connection, event_id, body, scope)
    connection.commit()
    return schedule.get_event(connection, event_id)


def delete_event(connection: sqlite3.Connection, event_id: str, scope: str | None = None) -> None:
    schedule.delete_event(connection, event_id, scope)
    connection.commit()


def import_records(connection: sqlite3.Connection, data: Any) -> ImportResult:
    """Save a whole import file, or nothing if any record is rejected (the clinic's rule)."""
    try:
        batch = loader.load(data, writes.existing_records(connection), app_settings())
    except loader.ImportFileError as error:
        raise QueryError("invalid_file", str(error)) from error
    if batch.rejections:
        return ImportResult(saved=False, counts={}, rejections=[Rejection(**vars(r)) for r in batch.rejections])
    counts = writes.save_batch(connection, batch)
    connection.commit()
    return ImportResult(saved=True, counts=counts, rejections=[])


REPORT_SECTIONS = (("overdue", "Overdue"), ("due_soon", "Due soon"), ("unassigned", "Unassigned (no scheduled date)"))


def report(connection: sqlite3.Connection, as_of: date, prepared_for: str, scope: str | None = None) -> Report:
    """Every open follow-up with a flag, grouped by flag, as the reader is allowed to see them."""
    sections = []
    for flag, title in REPORT_SECTIONS:
        filters = FollowUpSearch(flag=[flag], as_of_date=as_of, sort="due_date", limit=search.MAX_ROWS)
        items = export.all_items(partial(search.search_followups, scope=scope), connection, filters)
        sections.append(ReportSection(flag=flag, title=title, followups=items))
    return Report(as_of_date=as_of, prepared_for=prepared_for, all_followups=scope is None, sections=sections)


def asker_note(staff_id: str | None, scope: str | None) -> str:
    """Tells the SQL model who is asking, by staff ID only (no names leave the server)."""
    if staff_id is None:
        return ""
    if scope is None:
        return f"The person asking is staff member {staff_id}, a manager who may see every record."
    return (f"The person asking is staff member {staff_id}. The tables already hold only the follow-ups "
            "assigned to them and those patients' records, so questions about \"my\" follow-ups need no staff filter.")


def ask(
    connection: sqlite3.Connection, assistant: QueryAssistant, request: AskRequest,
    scope: str | None = None, staff_id: str | None = None,
) -> AskResponse:
    """Answer a question with model-generated SQL executed inside the server only."""
    decision = assistant.decide(request.question)
    logger.info(
        "Ask decision=%s modify_probability=%.2f question=%r",
        decision.intent, decision.modify_probability, request.question,
    )
    if decision.intent == "modify":
        raise QueryError(
            "modification_not_allowed",
            "Questions cannot change records; use the edit screens instead.",
        )
    if decision.intent != "read":
        raise QueryError("unsupported_question", "Ask about clinic follow-up records.")

    generated = assistant.generate_sql(
        request.question, repository.schema_text(connection), request.as_of_date, request.max_rows,
        asker_note(staff_id, scope),
    )
    logger.info("Ask sql=%r parameters=%r", generated.sql, generated.parameters)
    try:
        query_request = QueryRequest(query=generated.sql, parameters=generated.parameters, max_rows=request.max_rows)
    except ValidationError as error:
        raise QueryError("invalid_generated_query", "The generated query was not usable; rephrase the question.") from error
    result = repository.execute_query(
        connection, query_request, hidden_columns=repository.SENSITIVE_COLUMNS, scope=scope,
    )
    return AskResponse(
        question=request.question,
        decision=decision,
        sql=query_request.query,
        parameters=query_request.parameters,
        explanation=generated.explanation,
        result=result,
    )
