"""Application entry point, read-only search API, and natural-language questions."""

import logging
from pathlib import Path
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.api import router
from app.repository import QueryError

app = FastAPI(title="Visit Follow-Up Tracker", version="0.1.0")
app.include_router(router)
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


@app.get("/health")
def health() -> dict[str, str]:
    """Report process health only; database readiness is not checked yet."""
    return {"status": "ok"}
