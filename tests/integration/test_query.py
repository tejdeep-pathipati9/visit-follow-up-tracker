"""Real SQLite tests for schema discovery and restricted execution of server-built SQL.

Arbitrary SQL is no longer accepted over HTTP; these tests call the repository
that UI searches and natural-language questions use internally.
"""

from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from app import repository
from app.db import read_database
from app.main import app
from app.models import QueryRequest
from app.repository import QueryError


def run(sql, parameters=None, hidden_columns=frozenset(), **options):
    request = QueryRequest(query=sql, parameters=parameters if parameters is not None else [], **options)
    with read_database() as connection:
        return repository.execute_query(connection, request, hidden_columns).model_dump()


def rejected(sql, parameters=None):
    with pytest.raises(QueryError) as error:
        run(sql, parameters)
    return error.value


@pytest.mark.parametrize(("table", "count"), [
    ("patients", 2), ("staff", 4), ("episodes", 2), ("visits", 2), ("followups", 7),
])
def test_all_application_tables_can_be_queried(database, table, count):
    result = run(f"SELECT * FROM {table}")
    assert result["row_count"] == count
    assert len(result["rows"]) == count
    assert result["truncated"] is False
    assert all(len(row) == len(result["columns"]) for row in result["rows"])


def test_bound_parameters_and_non_ascii_text(database):
    result = run("SELECT patient_id, name, phone FROM patients WHERE name = ?", ["Zoë Tëst"])
    assert result == {
        "columns": ["patient_id", "name", "phone"],
        "rows": [["P002", "Zoë Tëst", None]], "row_count": 1, "truncated": False,
    }
    assert run("SELECT patient_id FROM patients WHERE name = :name", {"name": "Alice Example"})["rows"] == [["P001"]]
    assert run("SELECT patient_id FROM patients WHERE name = ?", ["' OR 1=1 --"])["rows"] == []
    assert run("SELECT ? AS literal", ["  preserve spaces  "])["rows"] == [["  preserve spaces  "]]


def test_join_filters_and_sorting_are_defined_by_the_sql(database):
    result = run("""
        SELECT f.followup_id, p.name AS patient_name, s.name AS assigned_staff_name
        FROM followups f JOIN visits v ON v.visit_id = f.visit_id
        JOIN patients p ON p.patient_id = v.patient_id
        LEFT JOIN staff s ON s.staff_id = f.assigned_staff_id
        WHERE f.status = ? AND f.due_date < ?
        ORDER BY f.due_date, f.followup_id
    """, ["open", "2026-10-26"])
    assert result["columns"] == ["followup_id", "patient_name", "assigned_staff_name"]
    assert result["rows"] == [
        ["F006", "Zoë Tëst", "Dr. Example"],
        ["F001", "Alice Example", None],
        ["F007", "Zoë Tëst", "Dr. Example"],
    ]


def test_cte_aggregates_and_window_functions(database):
    result = run("""
        WITH pending AS (SELECT * FROM followups WHERE status = 'open')
        SELECT action_type, COUNT(*) AS count FROM pending
        GROUP BY action_type ORDER BY action_type
    """)
    assert result["rows"] == [["lab", 3], ["recheck", 1], ["referral", 2]]
    assert run("SELECT row_number() OVER (ORDER BY patient_id) AS n FROM patients")["rows"] == [[1], [2]]


def test_duplicate_column_names_preserve_both_values(database):
    result = run("""
        SELECT p.name, s.name FROM patients p CROSS JOIN staff s
        ORDER BY p.patient_id, s.staff_id LIMIT 1
    """)
    assert result["columns"] == ["name", "name"]
    assert result["rows"] == [["Alice Example", "Dr. Example"]]


def test_sql_pagination_and_response_cap(database):
    result = run("SELECT followup_id FROM followups ORDER BY followup_id LIMIT ? OFFSET ?", [2, 2])
    assert result["rows"] == [["F003"], ["F004"]]
    assert result["truncated"] is False
    capped = run("SELECT followup_id FROM followups ORDER BY followup_id", max_rows=2)
    assert capped["rows"] == [["F001"], ["F002"]]
    assert capped["truncated"] is True
    assert capped["row_count"] == 2
    assert run("SELECT patient_id FROM patients ORDER BY patient_id", max_rows=2)["truncated"] is False


def test_empty_result_retains_columns(database):
    result = run("SELECT patient_id, name FROM patients WHERE patient_id = 'missing'")
    assert result == {"columns": ["patient_id", "name"], "rows": [], "row_count": 0, "truncated": False}


def test_hidden_columns_read_as_null_and_cannot_be_filtered(database):
    hidden = repository.SENSITIVE_COLUMNS
    assert run("SELECT name, phone, email FROM patients WHERE patient_id = 'P001'", hidden_columns=hidden)["rows"] == [
        ["Alice Example", None, None],
    ]
    assert run("SELECT * FROM patients ORDER BY patient_id", hidden_columns=hidden)["rows"][0] == [
        "P001", "Alice Example", None, None,
    ]
    assert run("SELECT patient_id FROM patients WHERE phone = '555-0101'", hidden_columns=hidden)["rows"] == []
    assert run("SELECT phone FROM patients WHERE patient_id = 'P001'")["rows"] == [["555-0101"]]


def test_schema_is_live_text_with_relationships_and_no_record_data(client, database):
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("ALTER TABLE patients ADD COLUMN nickname TEXT")
        connection.execute("CREATE TABLE private_settings (secret TEXT)")
        connection.commit()
    response = client.get("/api/schema")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    for table in ("patients", "staff", "episodes", "visits", "followups"):
        assert f"CREATE TABLE {table}" in response.text
    assert "nickname TEXT" in response.text
    assert "FOREIGN KEY (episode_id, patient_id)" in response.text
    assert "idx_followups_status_due" in response.text
    assert "Alice Example" not in response.text
    assert "private_settings" not in response.text
    assert rejected("SELECT * FROM private_settings").code == "query_not_allowed"


@pytest.mark.parametrize("sql", [
    "DELETE FROM patients",
    "UPDATE patients SET name = 'changed' RETURNING name",
    "INSERT INTO patients (patient_id, name) VALUES ('P999', 'changed')",
    "REPLACE INTO patients (patient_id, name) VALUES ('P001', 'changed')",
    "WITH selected AS (SELECT 1) DELETE FROM followups",
    "DROP TABLE followups",
    "ALTER TABLE patients ADD COLUMN unsafe TEXT",
    "CREATE TABLE unsafe (id TEXT)",
    "CREATE TEMP TABLE unsafe (id TEXT)",
    "CREATE VIEW unsafe AS SELECT * FROM patients",
    "PRAGMA table_info(patients)",
    "PRAGMA query_only = OFF",
    "ATTACH DATABASE ':memory:' AS other",
    "VACUUM",
    "BEGIN", "COMMIT",
    "SELECT * FROM sqlite_master",
    "SELECT * FROM pragma_table_info('patients')",
    "SELECT load_extension('anything')",
    "SELECT * FROM patients; DELETE FROM patients;",
    "EXPLAIN DELETE FROM followups",
])
def test_disallowed_sql_cannot_change_database(database, sql):
    with closing(sqlite3.connect(database)) as connection:
        before = list(connection.iterdump())
    assert rejected(sql).status_code == 422
    with closing(sqlite3.connect(database)) as connection:
        assert list(connection.iterdump()) == before
    assert run("SELECT COUNT(*) FROM patients")["rows"] == [[2]]


@pytest.mark.parametrize("body", [
    {}, {"query": "   "}, {"query": "x" * 20_001},
    {"query": "SELECT 1", "max_rows": 0}, {"query": "SELECT 1", "max_rows": 1_001},
    {"query": "SELECT 1", "filters": {}},
    {"query": "SELECT ?", "parameters": [["nested"]]},
    {"query": "SELECT 1", "parameters": [0] * 1_001},
    {"query": "SELECT 1", "max_rows": "10"},
])
def test_invalid_requests_are_rejected(body):
    with pytest.raises(ValidationError):
        QueryRequest(**body)


@pytest.mark.parametrize(("sql", "parameters"), [
    ("not SQL", []), ("SELECT missing_column FROM patients", []),
    ("SELECT ?", []), ("SELECT 1", ["extra"]),
    ("SELECT :name", {"other": "missing"}),
    ("SELECT * FROM missing_table", []),
])
def test_invalid_sql_and_bindings_return_clear_errors(database, sql, parameters):
    assert rejected(sql, parameters).code == "invalid_query"


def test_recursive_query_has_execution_budget(database):
    error = rejected("""
        WITH RECURSIVE numbers(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM numbers)
        SELECT SUM(n) FROM numbers
    """)
    assert (error.code, error.status_code) == ("query_limit_exceeded", 408)
    assert run("SELECT COUNT(*) FROM patients")["rows"] == [[2]]


def test_result_size_is_bounded(database, monkeypatch):
    monkeypatch.setattr("app.repository.MAX_RESULT_BYTES", 20)
    result = run("SELECT name FROM patients ORDER BY patient_id")
    assert result["rows"] == [["Alice Example"]]
    assert result["truncated"] is True


@pytest.mark.parametrize("sql", ["SELECT X'FF'", "SELECT 1e999"])
def test_non_json_values_are_rejected(database, sql):
    assert rejected(sql).code == "unsupported_result"


def test_binary_can_be_requested_as_hex(database):
    assert run("SELECT HEX(X'FF') AS value")["rows"] == [["FF"]]


def test_read_connection_cannot_write(database):
    with read_database() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM followups")


def test_missing_database_returns_503_without_creating_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(missing))
    with TestClient(app) as client:
        for response in (client.get("/api/schema"), client.get("/api/followups")):
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "database_unavailable"
    assert not missing.exists()


def test_comment_prefixed_sql_is_supported(database):
    assert run("-- Read a patient\n SELECT patient_id FROM patients ORDER BY patient_id LIMIT 1;")["rows"] == [["P001"]]


def test_raw_sql_is_not_accepted_over_http(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/query" not in paths
    assert client.post("/api/query", json={"query": "SELECT * FROM patients"}).status_code == 404
    names = {
        parameter["name"] for methods in paths.values() for operation in methods.values()
        for parameter in operation.get("parameters", [])
    }
    assert not names & {"query", "sql"}
    assert "QueryRequest" not in client.get("/openapi.json").json()["components"]["schemas"]
