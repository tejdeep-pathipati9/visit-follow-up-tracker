"""Application services for UI searches, record changes, and natural-language questions."""

from datetime import date
import logging
import sqlite3

from pydantic import ValidationError

from app import repository, search, writes
from app.ai import QueryAssistant
from app.models import (
    AskRequest, AskResponse, Dashboard, EpisodeCreate, EpisodeDetail, EpisodeHistory,
    EpisodeSearch, EpisodeSummary, EpisodeUpdate, FollowUpCreate, FollowUpDetail, FollowUpItem,
    FollowUpSearch, FollowUpStats, FollowUpStatsQuery, FollowUpUpdate, Page, PatientCreate,
    PatientDetail, PatientSearch, PatientSummary, PatientUpdate, QueryRequest, QueryResponse,
    SearchOptions, StaffCreate, StaffDetail, StaffSearch, StaffSummary, StaffUpdate, VisitCreate,
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


def search_followups(connection: sqlite3.Connection, filters: FollowUpSearch) -> Page[FollowUpItem]:
    return search.search_followups(connection, filters)


def followup_stats(connection: sqlite3.Connection, filters: FollowUpStatsQuery) -> FollowUpStats:
    return search.followup_stats(connection, filters)


def search_patients(connection: sqlite3.Connection, filters: PatientSearch) -> Page[PatientSummary]:
    return search.search_patients(connection, filters)


def search_staff(connection: sqlite3.Connection, filters: StaffSearch) -> Page[StaffSummary]:
    return search.search_staff(connection, filters)


def search_visits(connection: sqlite3.Connection, filters: VisitSearch) -> Page[VisitSummary]:
    return search.search_visits(connection, filters)


def search_episodes(connection: sqlite3.Connection, filters: EpisodeSearch) -> Page[EpisodeSummary]:
    return search.search_episodes(connection, filters)


def dashboard(connection: sqlite3.Connection, as_of: date) -> Dashboard:
    return search.dashboard(connection, as_of)


def options(connection: sqlite3.Connection, as_of: date) -> SearchOptions:
    return search.options(connection, as_of)


def only(items: list, kind: str, record_id: str):
    if not items:
        raise QueryError("not_found", f"{kind} {record_id} was not found.", 404)
    return items[0]


def histories(connection: sqlite3.Connection, as_of: date, **match: list[str]) -> list[EpisodeHistory]:
    """Episodes with their visits and follow-ups, oldest first, for one patient or episode."""
    limit = search.MAX_ROWS
    episodes = search.search_episodes(connection, EpisodeSearch(**match, as_of_date=as_of, limit=limit, sort="opened_at"))
    visits = search.search_visits(connection, VisitSearch(**match, as_of_date=as_of, limit=limit, sort="visit_date"))
    followups = search.search_followups(connection, FollowUpSearch(**match, as_of_date=as_of, limit=limit))
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


def followup_detail(connection: sqlite3.Connection, followup_id: str, as_of: date) -> FollowUpDetail:
    found = search.search_followups(connection, FollowUpSearch(followup_id=[followup_id], as_of_date=as_of, limit=1))
    followup = only(found.items, "Follow-up", followup_id)
    patient = search.search_patients(connection, PatientSearch(patient_id=[followup.patient_id], as_of_date=as_of, limit=1))
    episode = search.search_followups(
        connection, FollowUpSearch(episode_id=[followup.episode_id], as_of_date=as_of, limit=search.MAX_ROWS),
    )
    return FollowUpDetail(
        followup=followup,
        patient=patient.items[0],
        episode_followups=[item for item in episode.items if item.followup_id != followup_id],
    )


def patient_detail(connection: sqlite3.Connection, patient_id: str, as_of: date) -> PatientDetail:
    found = search.search_patients(connection, PatientSearch(patient_id=[patient_id], as_of_date=as_of, limit=1))
    return PatientDetail(
        patient=only(found.items, "Patient", patient_id),
        episodes=histories(connection, as_of, patient_id=[patient_id]),
    )


def staff_detail(connection: sqlite3.Connection, staff_id: str, as_of: date) -> StaffDetail:
    found = search.search_staff(connection, StaffSearch(staff_id=[staff_id], as_of_date=as_of, limit=1))
    staff = only(found.items, "Staff member", staff_id)
    assigned = search.search_followups(connection, FollowUpSearch(
        assigned_staff_id=[staff_id], status=["open"], as_of_date=as_of, limit=search.MAX_ROWS,
    ))
    visits = search.search_visits(connection, VisitSearch(
        staff_id=[staff_id], as_of_date=as_of, limit=RECENT_VISITS, sort="-visit_date",
    ))
    return StaffDetail(staff=staff, open_followups=assigned.items, recent_visits=visits.items)


def episode_detail(connection: sqlite3.Connection, episode_id: str, as_of: date) -> EpisodeDetail:
    episodes = histories(connection, as_of, episode_id=[episode_id])
    return EpisodeDetail(episode=only(episodes, "Episode", episode_id))


def visit_detail(connection: sqlite3.Connection, visit_id: str, as_of: date) -> VisitDetail:
    found = search.search_visits(connection, VisitSearch(visit_id=[visit_id], as_of_date=as_of, limit=1))
    visit = only(found.items, "Visit", visit_id)
    followups = search.search_followups(connection, FollowUpSearch(visit_id=[visit_id], as_of_date=as_of, limit=search.MAX_ROWS))
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


def update_followup(connection: sqlite3.Connection, followup_id: str, body: FollowUpUpdate, as_of: date) -> FollowUpItem:
    writes.update_followup(connection, followup_id, body)
    return saved_followup(connection, followup_id, as_of)


def ask(connection: sqlite3.Connection, assistant: QueryAssistant, request: AskRequest) -> AskResponse:
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
    )
    logger.info("Ask sql=%r parameters=%r", generated.sql, generated.parameters)
    try:
        query_request = QueryRequest(query=generated.sql, parameters=generated.parameters, max_rows=request.max_rows)
    except ValidationError as error:
        raise QueryError("invalid_generated_query", "The generated query was not usable; rephrase the question.") from error
    result = repository.execute_query(connection, query_request, hidden_columns=repository.SENSITIVE_COLUMNS)
    return AskResponse(
        question=request.question,
        decision=decision,
        sql=query_request.query,
        parameters=query_request.parameters,
        explanation=generated.explanation,
        result=result,
    )
