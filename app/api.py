"""Predefined search and record-change endpoints, and read-only natural-language questions.

Callers send filter values, record fields, or a question, never SQL. Search SQL is
fixed in app/search.py and change SQL in app/writes.py; natural-language SQL is
generated and executed inside the server on a read-only connection.
"""

from datetime import date
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app import service
from app.ai import QueryAssistant, get_assistant
from app.db import get_db, get_write_db
from app.models import (
    AskRequest, AskResponse, Dashboard, EpisodeCreate, EpisodeDetail, EpisodeSearch,
    EpisodeSummary, EpisodeUpdate, FollowUpCreate, FollowUpDetail, FollowUpItem, FollowUpSearch,
    FollowUpStats, FollowUpStatsQuery, FollowUpUpdate, Page, PatientCreate, PatientDetail,
    PatientSearch, PatientSummary, PatientUpdate, RecordId, SearchOptions, StaffCreate,
    StaffDetail, StaffSearch, StaffSummary, StaffUpdate, VisitCreate, VisitDetail, VisitSearch,
    VisitSummary, VisitUpdate,
)

router = APIRouter(prefix="/api")
Database = Annotated[sqlite3.Connection, Depends(get_db)]
WritableDatabase = Annotated[sqlite3.Connection, Depends(get_write_db)]
Assistant = Annotated[QueryAssistant, Depends(get_assistant)]
AsOfDate = Annotated[date | None, Query(description="Evaluate flags as of this date (default: today).")]


def today(as_of_date: date | None) -> date:
    return as_of_date or date.today()


@router.get("/schema", response_class=PlainTextResponse, tags=["Schema"])
def schema(connection: Database) -> str:
    """Return current CREATE TABLE/INDEX statements, including column relationships."""
    return service.schema(connection)


@router.get("/options", tags=["Search"])
def options(connection: Database, as_of_date: AsOfDate = None) -> SearchOptions:
    """Dropdown values, staff list, date bounds for sliders, presets, and sort options."""
    return service.options(connection, today(as_of_date))


@router.get("/dashboard", tags=["Search"])
def dashboard(connection: Database, as_of_date: AsOfDate = None) -> Dashboard:
    """Headline counts for the home screen."""
    return service.dashboard(connection, today(as_of_date))


@router.get("/followups", tags=["Follow-ups"])
def search_followups(connection: Database, filters: Annotated[FollowUpSearch, Query()]) -> Page[FollowUpItem]:
    """Filter, sort, and page follow-ups; every filter is optional and filters combine with AND."""
    return service.search_followups(connection, filters)


@router.get("/followups/stats", tags=["Follow-ups"])
def followup_stats(connection: Database, filters: Annotated[FollowUpStatsQuery, Query()]) -> FollowUpStats:
    """Counts for the filtered follow-ups, optionally grouped for charts and summaries."""
    return service.followup_stats(connection, filters)


@router.get("/followups/{followup_id}", tags=["Follow-ups"])
def followup_detail(connection: Database, followup_id: RecordId, as_of_date: AsOfDate = None) -> FollowUpDetail:
    return service.followup_detail(connection, followup_id, today(as_of_date))


@router.get("/patients", tags=["Patients"])
def search_patients(connection: Database, filters: Annotated[PatientSearch, Query()]) -> Page[PatientSummary]:
    return service.search_patients(connection, filters)


@router.get("/patients/{patient_id}", tags=["Patients"])
def patient_detail(connection: Database, patient_id: RecordId, as_of_date: AsOfDate = None) -> PatientDetail:
    """Patient summary with every episode, visit, and follow-up."""
    return service.patient_detail(connection, patient_id, today(as_of_date))


@router.get("/staff", tags=["Staff"])
def search_staff(connection: Database, filters: Annotated[StaffSearch, Query()]) -> Page[StaffSummary]:
    """Staff with visit counts and the workload of follow-ups assigned to them."""
    return service.search_staff(connection, filters)


@router.get("/staff/{staff_id}", tags=["Staff"])
def staff_detail(connection: Database, staff_id: RecordId, as_of_date: AsOfDate = None) -> StaffDetail:
    return service.staff_detail(connection, staff_id, today(as_of_date))


@router.get("/visits", tags=["Visits"])
def search_visits(connection: Database, filters: Annotated[VisitSearch, Query()]) -> Page[VisitSummary]:
    return service.search_visits(connection, filters)


@router.get("/visits/{visit_id}", tags=["Visits"])
def visit_detail(connection: Database, visit_id: RecordId, as_of_date: AsOfDate = None) -> VisitDetail:
    return service.visit_detail(connection, visit_id, today(as_of_date))


@router.get("/episodes", tags=["Episodes"])
def search_episodes(connection: Database, filters: Annotated[EpisodeSearch, Query()]) -> Page[EpisodeSummary]:
    return service.search_episodes(connection, filters)


@router.get("/episodes/{episode_id}", tags=["Episodes"])
def episode_detail(connection: Database, episode_id: RecordId, as_of_date: AsOfDate = None) -> EpisodeDetail:
    return service.episode_detail(connection, episode_id, today(as_of_date))


# --- Record changes: create and update only; records are never deleted. --------

@router.post("/patients", status_code=201, tags=["Patients"])
def create_patient(connection: WritableDatabase, body: PatientCreate, as_of_date: AsOfDate = None) -> PatientSummary:
    """Omit patient_id to receive the next free ID."""
    return service.create_patient(connection, body, today(as_of_date))


@router.patch("/patients/{patient_id}", tags=["Patients"])
def update_patient(
    connection: WritableDatabase, patient_id: RecordId, body: PatientUpdate, as_of_date: AsOfDate = None,
) -> PatientSummary:
    """Send only the fields to change; null clears phone or email."""
    return service.update_patient(connection, patient_id, body, today(as_of_date))


@router.post("/staff", status_code=201, tags=["Staff"])
def create_staff(connection: WritableDatabase, body: StaffCreate, as_of_date: AsOfDate = None) -> StaffSummary:
    return service.create_staff(connection, body, today(as_of_date))


@router.patch("/staff/{staff_id}", tags=["Staff"])
def update_staff(
    connection: WritableDatabase, staff_id: RecordId, body: StaffUpdate, as_of_date: AsOfDate = None,
) -> StaffSummary:
    return service.update_staff(connection, staff_id, body, today(as_of_date))


@router.post("/episodes", status_code=201, tags=["Episodes"])
def create_episode(connection: WritableDatabase, body: EpisodeCreate, as_of_date: AsOfDate = None) -> EpisodeSummary:
    return service.create_episode(connection, body, today(as_of_date))


@router.patch("/episodes/{episode_id}", tags=["Episodes"])
def update_episode(
    connection: WritableDatabase, episode_id: RecordId, body: EpisodeUpdate, as_of_date: AsOfDate = None,
) -> EpisodeSummary:
    """Set closed_at to close the episode, or null to reopen it."""
    return service.update_episode(connection, episode_id, body, today(as_of_date))


@router.post("/visits", status_code=201, tags=["Visits"])
def create_visit(connection: WritableDatabase, body: VisitCreate, as_of_date: AsOfDate = None) -> VisitSummary:
    """The visit's patient is taken from its episode."""
    return service.create_visit(connection, body, today(as_of_date))


@router.patch("/visits/{visit_id}", tags=["Visits"])
def update_visit(
    connection: WritableDatabase, visit_id: RecordId, body: VisitUpdate, as_of_date: AsOfDate = None,
) -> VisitSummary:
    return service.update_visit(connection, visit_id, body, today(as_of_date))


@router.post("/followups", status_code=201, tags=["Follow-ups"])
def create_followup(connection: WritableDatabase, body: FollowUpCreate, as_of_date: AsOfDate = None) -> FollowUpItem:
    """New follow-ups start open."""
    return service.create_followup(connection, body, today(as_of_date))


@router.patch("/followups/{followup_id}", tags=["Follow-ups"])
def update_followup(
    connection: WritableDatabase, followup_id: RecordId, body: FollowUpUpdate, as_of_date: AsOfDate = None,
) -> FollowUpItem:
    """status "done" records the completion time; "open" reopens; null assigned_staff_id unassigns."""
    return service.update_followup(connection, followup_id, body, today(as_of_date))


@router.post("/ask", tags=["Natural-language search"])
def ask(request: AskRequest, connection: Database, assistant: Assistant) -> AskResponse:
    """Answer a read-only question; prompts asking to change data are rejected before SQL is generated."""
    return service.ask(connection, assistant, request)
