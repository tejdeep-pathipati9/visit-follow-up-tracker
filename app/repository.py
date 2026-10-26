"""Execute caller-supplied SQL with SQLite-enforced read-only permissions."""

import json
import sqlite3
from time import monotonic

from app.models import QueryRequest, QueryResponse

READABLE_TABLES = frozenset({
    "patients", "staff", "episodes", "visits", "followups", "status_changes",
})
ALLOWED_FUNCTIONS = frozenset({
    "abs", "avg", "coalesce", "count", "date", "datetime", "dense_rank",
    "first_value", "glob", "group_concat", "hex", "ifnull", "iif", "instr",
    "julianday", "lag", "last_value", "lead", "length", "like", "lower",
    "ltrim", "max", "min", "nth_value", "ntile", "nullif", "percent_rank",
    "quote", "rank", "replace", "round", "row_number", "rtrim", "strftime",
    "substr", "substring", "sum", "time", "total", "trim", "typeof",
    "unicode", "unixepoch", "upper",
})
QUERY_TIMEOUT_SECONDS = 2.0
MAX_VM_STEPS = 1_000_000
MAX_RESULT_BYTES = 4 * 1024 * 1024


class QueryError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def schema_text(connection: sqlite3.Connection) -> str:
    names = sorted(READABLE_TABLES)
    placeholders = ",".join("?" for _ in names)
    rows = connection.execute(
        "SELECT type, name, sql FROM sqlite_schema "
        f"WHERE tbl_name IN ({placeholders}) AND type IN ('table', 'index') "
        "AND sql IS NOT NULL ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END, name",
        names,
    ).fetchall()
    if not any(row["type"] == "table" for row in rows):
        raise sqlite3.OperationalError("The application schema is not initialized")
    return "-- SQLite application schema (no record data)\n\n" + "\n\n".join(
        row["sql"].rstrip(";") + ";" for row in rows
    ) + "\n"


def execute_query(connection: sqlite3.Connection, request: QueryRequest) -> QueryResponse:
    denied = False
    timed_out = False
    steps = 0
    deadline = monotonic() + QUERY_TIMEOUT_SECONDS

    def authorize(action, arg1, arg2, database, source):
        nonlocal denied
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
            return sqlite3.SQLITE_OK
        # Some SQLite builds omit the database name for COUNT(*) table reads.
        main_table_read = database == "main" or (database is None and arg2 == "")
        if action == sqlite3.SQLITE_READ and main_table_read and arg1 in READABLE_TABLES:
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in ALLOWED_FUNCTIONS:
            return sqlite3.SQLITE_OK
        denied = True
        return sqlite3.SQLITE_DENY

    def progress():
        nonlocal timed_out, steps
        steps += 1_000
        timed_out = steps >= MAX_VM_STEPS or monotonic() >= deadline
        return int(timed_out)

    # Bounds apply to SQL compilation and individual values as well as row count.
    for category, maximum in (
        (sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20_000),
        (sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000),
        (sqlite3.SQLITE_LIMIT_COLUMN, 100),
        (sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100),
        (sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20),
        (sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 1_000),
        (sqlite3.SQLITE_LIMIT_ATTACHED, 0),
    ):
        connection.setlimit(category, maximum)

    # Keep authorization active during fetching: SQLite may reprepare a statement.
    # https://www.sqlite.org/c3ref/set_authorizer.html
    connection.set_authorizer(authorize)
    connection.set_progress_handler(progress, 1_000)
    cursor = None
    try:
        cursor = connection.execute(request.query, request.parameters)
        if cursor.description is None:
            raise QueryError("invalid_query", "Submit one read-only SELECT query.")
        columns = [column[0] for column in cursor.description]
        rows = []
        size = 0
        truncated = False
        for row in cursor:
            if len(rows) == request.max_rows:
                truncated = True
                break
            values = list(row)
            try:
                row_size = len(json.dumps(values, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            except (TypeError, ValueError) as error:
                raise QueryError(
                    "unsupported_result", "Return finite numbers, text, or NULL; use HEX() for binary values."
                ) from error
            if size + row_size > MAX_RESULT_BYTES:
                truncated = True
                break
            rows.append(values)
            size += row_size
        return QueryResponse(columns=columns, rows=rows, row_count=len(rows), truncated=truncated)
    except sqlite3.Error as error:
        if denied:
            raise QueryError(
                "query_not_allowed",
                "Only read-only queries on application tables and approved SQL functions are allowed.",
            ) from error
        if timed_out:
            raise QueryError("query_limit_exceeded", "Query exceeded its execution budget; narrow the query.", 408) from error
        # Invalid SQL and bindings are client errors; never return a Python traceback.
        raise QueryError("invalid_query", str(error)) from error
    finally:
        if cursor is not None:
            cursor.close()
        connection.set_progress_handler(None, 0)
        connection.set_authorizer(None)
