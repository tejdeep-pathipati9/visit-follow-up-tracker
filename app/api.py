"""Predefined search and record-change endpoints, and read-only natural-language questions.

Callers send filter values, record fields, or a question, never SQL. Search SQL is
fixed in app/search.py and change SQL in app/writes.py; natural-language SQL is
generated and executed inside the server on a read-only connection.

Every endpoint needs a signed-in staff member (app/auth.py). Searches, details,
downloads, and the report are limited to the reader's own follow-ups unless they are
a manager, and so are answers to questions. Only a manager creates or edits records;
other staff change the follow-ups assigned to them.
"""

from datetime import date
from functools import partial
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Body, Cookie, Depends, Query, Response
from fastapi.responses import PlainTextResponse

from app import auth, export, service
from app.ai import QueryAssistant, get_assistant
from app.auth import CurrentViewer, Manager
from app.db import get_db, get_write_db
from app.models import (
    AskRequest, AskResponse, Dashboard, ImportResult, EpisodeCreate, EpisodeDetail, EpisodeSearch,
    EpisodeSummary, EpisodeUpdate, FollowUpCreate, FollowUpDetail, FollowUpItem, FollowUpSearch,
    FollowUpStats, FollowUpStatsQuery, FollowUpUpdate, Page, PatientCreate, PatientDetail,
    PatientSearch, PatientSummary, PatientUpdate, RecordId, Report, SearchOptions, SessionInfo,
    SignIn, StaffCreate, StaffDetail, StaffSearch, StaffSummary, StaffUpdate, VisitCreate,
    VisitDetail, VisitSearch, VisitSummary, VisitUpdate,
)

router = APIRouter(prefix="/api", dependencies=[Depends(auth.current_viewer)])
session_router = APIRouter(prefix="/api/session", tags=["Sign-in"])
Database = Annotated[sqlite3.Connection, Depends(get_db)]
WritableDatabase = Annotated[sqlite3.Connection, Depends(get_write_db)]
Assistant = Annotated[QueryAssistant, Depends(get_assistant)]
AsOfDate = Annotated[date | None, Query(description="Evaluate flags as of this date (default: today).")]
SessionToken = Annotated[str | None, Cookie(alias=auth.SESSION_COOKIE)]


def today(as_of_date: date | None) -> date:
    return as_of_date or date.today()


# --- Sign-in: staff email only in this release; passwords come later. ----------

def session_info(viewer: auth.Viewer) -> SessionInfo:
    return SessionInfo(
        staff_id=viewer.staff_id, name=viewer.name, role=viewer.role, email=viewer.email,
        is_manager=viewer.is_manager,
    )


@session_router.post("")
def sign_in(body: SignIn, response: Response) -> SessionInfo:
    """Sign in with a staff member's email; the session cookie identifies them afterwards."""
    token, viewer = auth.sign_in(body.email)
    response.set_cookie(auth.SESSION_COOKIE, token, httponly=True, samesite="lax", path="/")
    return session_info(viewer)


@session_router.get("")
def current_session(viewer: CurrentViewer) -> SessionInfo:
    return session_info(viewer)


@session_router.delete("", status_code=204, response_class=Response)
def sign_out(response: Response, token: SessionToken = None) -> None:
    auth.sign_out(token)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


# --- Searches, details, downloads, and the report -------------------------------

CSV = {"response_class": Response, "responses": {200: {"content": {"text/csv": {}}}}}


def csv_download(kind: str, search, connection: sqlite3.Connection, filters, viewer: auth.Viewer) -> Response:
    """Every row matching the filters, in the list's sort order; paging is ignored."""
    content = export.to_csv(kind, export.all_items(partial(search, scope=viewer.scope), connection, filters))
    filename = f"{kind}-{filters.as_of_date.isoformat()}.csv"
    return Response(content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/schema", response_class=PlainTextResponse, tags=["Schema"])
def schema(connection: Database) -> str:
    """Return current CREATE TABLE/INDEX statements, including column relationships."""
    return service.schema(connection)


@router.get("/options", tags=["Search"])
def options(connection: Database, as_of_date: AsOfDate = None) -> SearchOptions:
    """Dropdown values, staff list, date bounds for sliders, presets, and sort options."""
    return service.options(connection, today(as_of_date))


@router.get("/dashboard", tags=["Search"])
def dashboard(connection: Database, viewer: CurrentViewer, as_of_date: AsOfDate = None) -> Dashboard:
    """Headline counts for the home screen."""
    return service.dashboard(connection, today(as_of_date), viewer.scope)


@router.get("/report", tags=["Report"])
def report(connection: Database, viewer: CurrentViewer, as_of_date: AsOfDate = None) -> Report:
    """Open follow-ups that are overdue, due soon, or unassigned, grouped by flag (printable at /report)."""
    return service.report(connection, today(as_of_date), viewer.name, viewer.scope)


@router.get("/followups", tags=["Follow-ups"])
def search_followups(
    connection: Database, viewer: CurrentViewer, filters: Annotated[FollowUpSearch, Query()],
) -> Page[FollowUpItem]:
    """Filter, sort, and page follow-ups; every filter is optional and filters combine with AND."""
    return service.search_followups(connection, filters, viewer.scope)


@router.get("/followups/export", tags=["Follow-ups"], **CSV)
def export_followups(connection: Database, viewer: CurrentViewer, filters: Annotated[FollowUpSearch, Query()]) -> Response:
    """Download every matching row as CSV, with the same filters and sort as the list."""
    return csv_download("followups", service.search_followups, connection, filters, viewer)


@router.get("/followups/stats", tags=["Follow-ups"])
def followup_stats(
    connection: Database, viewer: CurrentViewer, filters: Annotated[FollowUpStatsQuery, Query()],
) -> FollowUpStats:
    """Counts for the filtered follow-ups, optionally grouped for charts and summaries."""
    return service.followup_stats(connection, filters, viewer.scope)


@router.get("/followups/{followup_id}", tags=["Follow-ups"])
def followup_detail(
    connection: Database, viewer: CurrentViewer, followup_id: RecordId, as_of_date: AsOfDate = None,
) -> FollowUpDetail:
    return service.followup_detail(connection, followup_id, today(as_of_date), viewer.scope)


@router.get("/patients", tags=["Patients"])
def search_patients(
    connection: Database, viewer: CurrentViewer, filters: Annotated[PatientSearch, Query()],
) -> Page[PatientSummary]:
    return service.search_patients(connection, filters, viewer.scope)


@router.get("/patients/export", tags=["Patients"], **CSV)
def export_patients(connection: Database, viewer: CurrentViewer, filters: Annotated[PatientSearch, Query()]) -> Response:
    """Download every matching row as CSV, with the same filters and sort as the list."""
    return csv_download("patients", service.search_patients, connection, filters, viewer)


@router.get("/patients/{patient_id}", tags=["Patients"])
def patient_detail(
    connection: Database, viewer: CurrentViewer, patient_id: RecordId, as_of_date: AsOfDate = None,
) -> PatientDetail:
    """Patient summary with every episode, visit, and follow-up."""
    return service.patient_detail(connection, patient_id, today(as_of_date), viewer.scope)


@router.get("/staff", tags=["Staff"])
def search_staff(connection: Database, viewer: CurrentViewer, filters: Annotated[StaffSearch, Query()]) -> Page[StaffSummary]:
    """Staff with visit counts and the workload of follow-ups assigned to them."""
    return service.search_staff(connection, filters, viewer.scope)


@router.get("/staff/export", tags=["Staff"], **CSV)
def export_staff(connection: Database, viewer: CurrentViewer, filters: Annotated[StaffSearch, Query()]) -> Response:
    """Download every matching row as CSV, with the same filters and sort as the list."""
    return csv_download("staff", service.search_staff, connection, filters, viewer)


@router.get("/staff/{staff_id}", tags=["Staff"])
def staff_detail(
    connection: Database, viewer: CurrentViewer, staff_id: RecordId, as_of_date: AsOfDate = None,
) -> StaffDetail:
    return service.staff_detail(connection, staff_id, today(as_of_date), viewer.scope)


@router.get("/visits", tags=["Visits"])
def search_visits(connection: Database, viewer: CurrentViewer, filters: Annotated[VisitSearch, Query()]) -> Page[VisitSummary]:
    return service.search_visits(connection, filters, viewer.scope)


@router.get("/visits/export", tags=["Visits"], **CSV)
def export_visits(connection: Database, viewer: CurrentViewer, filters: Annotated[VisitSearch, Query()]) -> Response:
    """Download every matching row as CSV, with the same filters and sort as the list."""
    return csv_download("visits", service.search_visits, connection, filters, viewer)


@router.get("/visits/{visit_id}", tags=["Visits"])
def visit_detail(
    connection: Database, viewer: CurrentViewer, visit_id: RecordId, as_of_date: AsOfDate = None,
) -> VisitDetail:
    return service.visit_detail(connection, visit_id, today(as_of_date), viewer.scope)


@router.get("/episodes", tags=["Episodes"])
def search_episodes(
    connection: Database, viewer: CurrentViewer, filters: Annotated[EpisodeSearch, Query()],
) -> Page[EpisodeSummary]:
    return service.search_episodes(connection, filters, viewer.scope)


@router.get("/episodes/export", tags=["Episodes"], **CSV)
def export_episodes(connection: Database, viewer: CurrentViewer, filters: Annotated[EpisodeSearch, Query()]) -> Response:
    """Download every matching row as CSV, with the same filters and sort as the list."""
    return csv_download("episodes", service.search_episodes, connection, filters, viewer)


@router.get("/episodes/{episode_id}", tags=["Episodes"])
def episode_detail(
    connection: Database, viewer: CurrentViewer, episode_id: RecordId, as_of_date: AsOfDate = None,
) -> EpisodeDetail:
    return service.episode_detail(connection, episode_id, today(as_of_date), viewer.scope)


# --- Record changes: create and update only; records are never deleted. --------
# A manager creates and edits records; other staff change their own follow-ups.

@router.post("/patients", status_code=201, tags=["Patients"])
def create_patient(connection: WritableDatabase, _: Manager, body: PatientCreate, as_of_date: AsOfDate = None) -> PatientSummary:
    """Omit patient_id to receive the next free ID."""
    return service.create_patient(connection, body, today(as_of_date))


@router.patch("/patients/{patient_id}", tags=["Patients"])
def update_patient(
    connection: WritableDatabase, _: Manager, patient_id: RecordId, body: PatientUpdate, as_of_date: AsOfDate = None,
) -> PatientSummary:
    """Send only the fields to change; null clears phone or email."""
    return service.update_patient(connection, patient_id, body, today(as_of_date))


@router.post("/staff", status_code=201, tags=["Staff"])
def create_staff(connection: WritableDatabase, _: Manager, body: StaffCreate, as_of_date: AsOfDate = None) -> StaffSummary:
    """Give the staff member an email so they can sign in; role "manager" sees every follow-up."""
    return service.create_staff(connection, body, today(as_of_date))


@router.patch("/staff/{staff_id}", tags=["Staff"])
def update_staff(
    connection: WritableDatabase, _: Manager, staff_id: RecordId, body: StaffUpdate, as_of_date: AsOfDate = None,
) -> StaffSummary:
    return service.update_staff(connection, staff_id, body, today(as_of_date))


@router.post("/episodes", status_code=201, tags=["Episodes"])
def create_episode(connection: WritableDatabase, _: Manager, body: EpisodeCreate, as_of_date: AsOfDate = None) -> EpisodeSummary:
    return service.create_episode(connection, body, today(as_of_date))


@router.patch("/episodes/{episode_id}", tags=["Episodes"])
def update_episode(
    connection: WritableDatabase, _: Manager, episode_id: RecordId, body: EpisodeUpdate, as_of_date: AsOfDate = None,
) -> EpisodeSummary:
    """Set closed_at to close the episode, or null to reopen it."""
    return service.update_episode(connection, episode_id, body, today(as_of_date))


@router.post("/visits", status_code=201, tags=["Visits"])
def create_visit(connection: WritableDatabase, _: Manager, body: VisitCreate, as_of_date: AsOfDate = None) -> VisitSummary:
    """The visit's patient is taken from its episode."""
    return service.create_visit(connection, body, today(as_of_date))


@router.patch("/visits/{visit_id}", tags=["Visits"])
def update_visit(
    connection: WritableDatabase, _: Manager, visit_id: RecordId, body: VisitUpdate, as_of_date: AsOfDate = None,
) -> VisitSummary:
    return service.update_visit(connection, visit_id, body, today(as_of_date))


@router.post("/followups", status_code=201, tags=["Follow-ups"])
def create_followup(connection: WritableDatabase, _: Manager, body: FollowUpCreate, as_of_date: AsOfDate = None) -> FollowUpItem:
    """New follow-ups start open."""
    return service.create_followup(connection, body, today(as_of_date))


@router.patch("/followups/{followup_id}", tags=["Follow-ups"])
def update_followup(
    connection: WritableDatabase, viewer: CurrentViewer, followup_id: RecordId, body: FollowUpUpdate,
    as_of_date: AsOfDate = None,
) -> FollowUpItem:
    """Change status ("closed" needs a reason in notes), scheduled date, staff member, or notes.
    Staff who are not managers can change only the follow-ups assigned to them."""
    return service.update_followup(connection, followup_id, body, today(as_of_date), viewer.scope, viewer.staff_id)


@router.post("/import", tags=["Import"])
def import_file(
    connection: WritableDatabase, _: Manager, data: Annotated[Any, Body()], response: Response,
) -> ImportResult:
    """Send an import file's JSON as the body. Any rejected record rejects the whole file
    (status 422, every reason listed) and nothing is saved."""
    result = service.import_records(connection, data)
    if not result.saved:
        response.status_code = 422
    return result


@router.post("/ask", tags=["Natural-language search"])
def ask(viewer: CurrentViewer, request: AskRequest, connection: Database, assistant: Assistant) -> AskResponse:
    """Answer a read-only question. Staff who are not managers get answers from their own
    follow-ups only. Prompts asking to change data are rejected before SQL is generated."""
    return service.ask(connection, assistant, request, viewer.scope, viewer.staff_id)
