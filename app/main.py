"""Application entry point, read-only search API, and natural-language questions."""

from datetime import date
import logging
from pathlib import Path
import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth, service
from app.api import router, session_router
from app.db import read_database
from app.repository import QueryError

app = FastAPI(title="Visit Follow-Up Tracker", version="0.1.0")
app.include_router(session_router)
app.include_router(router)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.exception_handler(QueryError)
def query_error(request: Request, error: QueryError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": {"code": error.code, "message": str(error)}},
    )


@app.exception_handler(sqlite3.IntegrityError)
def integrity_error(request: Request, error: sqlite3.IntegrityError) -> JSONResponse:
    # Services check references first; this covers races and constraints they do not check.
    return JSONResponse(status_code=409, content={"detail": {"code": "conflict", "message": str(error)}})


@app.exception_handler(sqlite3.Error)
def database_error(request: Request, error: sqlite3.Error) -> JSONResponse:
    logging.getLogger(__name__).error("Database search failed", exc_info=error)
    return JSONResponse(status_code=503, content={"detail": {
        "code": "database_unavailable",
        "message": "Database unavailable. Initialize it with scripts/table_generate.py and check FOLLOWUP_DB_PATH.",
    }})


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/report", response_class=HTMLResponse, include_in_schema=False)
def printable_report(
    request: Request, viewer: Annotated[auth.Viewer | None, Depends(auth.optional_viewer)], as_of_date: date | None = None,
):
    """The clinic manager's report as a page made for printing; signed-out readers go to sign-in."""
    if viewer is None:
        return RedirectResponse("/", status_code=303)
    with read_database() as connection:
        report = service.report(connection, as_of_date or date.today(), viewer.name, viewer.scope)
    return templates.TemplateResponse(request=request, name="report.html", context={"report": report})


@app.get("/health")
def health() -> dict[str, str]:
    """Report process health only; database readiness is not checked yet."""
    return {"status": "ok"}
