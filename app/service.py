"""Shared read-only query service for frontend and future AI callers."""

import sqlite3

from app import repository
from app.models import QueryRequest, QueryResponse


def query(connection: sqlite3.Connection, request: QueryRequest) -> QueryResponse:
    return repository.execute_query(connection, request)


def schema(connection: sqlite3.Connection) -> str:
    return repository.schema_text(connection)
