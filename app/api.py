"""Schema discovery and a single SQL query API for every application table."""

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app import service
from app.db import get_db
from app.models import QueryRequest, QueryResponse

router = APIRouter(prefix="/api", tags=["Database queries"])
Database = Annotated[sqlite3.Connection, Depends(get_db)]


@router.get("/schema", response_class=PlainTextResponse)
def schema(connection: Database) -> str:
    """Return current CREATE TABLE/INDEX statements, including column relationships."""
    return service.schema(connection)


@router.post("/query", response_model=QueryResponse)
def query(request: QueryRequest, connection: Database) -> QueryResponse:
    """Run one read-only SQL statement and return columns and ordered row values."""
    return service.query(connection, request)
