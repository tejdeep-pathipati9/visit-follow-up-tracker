"""Real SQLite tests for schema discovery and read-only caller-supplied SQL."""

from contextlib import closing
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.db import read_database
from app.main import app
from scripts.table_generate import table_generate

@pytest.fixture
def database(tmp_path, monkeypatch):
    path = table_generate(tmp_path / "search.db")
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(path))
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executemany(
            "INSERT INTO patients (patient_id, name) VALUES (?, ?)",
            [("P001", "Alice Example"), ("P002", "김테스트")],
        )
        connection.executemany(
            "INSERT INTO staff VALUES (?, ?, ?)",
            [("S001", "Dr. Example", "doctor"), ("S002", "Nurse Sample", "nurse"),
             ("S003", "Dr. Duplicate", "doctor"), ("S004", "Dr. Duplicate", "doctor")],
        )
        connection.executemany(
            "INSERT INTO episodes VALUES (?, ?, ?, ?, ?)",
            [("E001", "P001", "Synthetic injury", "2026-10-15", None),
             ("E002", "P002", "Synthetic recheck", "2026-10-20", None)],
        )
        connection.executemany(
            "INSERT INTO visits VALUES (?, ?, ?, ?, ?, ?)",
            [("V001", "P001", "E001", "S002", "2026-10-15", "Synthetic 100%_ note"),
             ("V002", "P002", "E002", "S001", "2026-10-20", "Synthetic visit")],
        )
        connection.executemany(
            "INSERT INTO followups VALUES (?, ?, ?, ?, ?, ?, ?)",
            [("F001", "V001", "lab", "2026-10-25", None, "open", None),
             ("F002", "V001", "lab", "2026-10-26", "S001", "open", None),
             ("F003", "V002", "recheck", "2026-11-02", "S002", "open", None),
             ("F004", "V002", "referral", "2026-11-03", None, "open", None),
             ("F005", "V001", "lab", "2026-10-20", None, "done", "2026-10-21T12:00:00Z"),
             ("F006", "V002", "referral", "2026-10-24", "S001", "open", None),
             ("F007", "V002", "lab", "2026-10-25", "S001", "open", None)],
        )
        connection.commit()
    return path


@pytest.fixture
def client(database):
    with TestClient(app) as client:
        yield client


def query(client, sql, parameters=None, **options):
    response = client.post("/api/query", json={
        "query": sql, "parameters": parameters if parameters is not None else [], **options,
    })
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(("table", "count"), [
    ("patients", 2), ("staff", 4), ("episodes", 2), ("visits", 2), ("followups", 7),
])
def test_all_application_tables_can_be_queried(client, table, count):
    result = query(client, f"SELECT * FROM {table}")
    assert result["row_count"] == count
    assert len(result["rows"]) == count
    assert result["truncated"] is False
    assert all(len(row) == len(result["columns"]) for row in result["rows"])


def test_bound_parameters_and_korean_text(client):
    result = query(client, "SELECT patient_id, name, phone FROM patients WHERE name = ?", ["김테스트"])
    assert result == {
        "columns": ["patient_id", "name", "phone"],
        "rows": [["P002", "김테스트", None]], "row_count": 1, "truncated": False,
    }
    result = query(client, "SELECT patient_id FROM patients WHERE name = :name", {"name": "Alice Example"})
    assert result["rows"] == [["P001"]]
    result = query(client, "SELECT patient_id FROM patients WHERE name = ?", ["' OR 1=1 --"])
    assert result["rows"] == []
    assert query(client, "SELECT ? AS literal", ["  preserve spaces  "])["rows"] == [["  preserve spaces  "]]


def test_join_filters_and_sorting_are_defined_by_the_sql(client):
    result = query(client, """
        SELECT f.followup_id, p.name AS patient_name, s.name AS assigned_staff_name
        FROM followups f JOIN visits v ON v.visit_id = f.visit_id
        JOIN patients p ON p.patient_id = v.patient_id
        LEFT JOIN staff s ON s.staff_id = f.assigned_staff_id
        WHERE f.status = ? AND f.due_date < ?
        ORDER BY f.due_date, f.followup_id
    """, ["open", "2026-10-26"])
    assert result["columns"] == ["followup_id", "patient_name", "assigned_staff_name"]
    assert result["rows"] == [
        ["F006", "김테스트", "Dr. Example"],
        ["F001", "Alice Example", None],
        ["F007", "김테스트", "Dr. Example"],
    ]


def test_cte_aggregates_and_window_functions(client):
    result = query(client, """
        WITH pending AS (SELECT * FROM followups WHERE status = 'open')
        SELECT action_type, COUNT(*) AS count FROM pending
        GROUP BY action_type ORDER BY action_type
    """)
    assert result["rows"] == [["lab", 3], ["recheck", 1], ["referral", 2]]
    assert query(client, "SELECT row_number() OVER (ORDER BY patient_id) AS n FROM patients")["rows"] == [[1], [2]]


def test_duplicate_column_names_preserve_both_values(client):
    result = query(client, """
        SELECT p.name, s.name FROM patients p CROSS JOIN staff s
        ORDER BY p.patient_id, s.staff_id LIMIT 1
    """)
    assert result["columns"] == ["name", "name"]
    assert result["rows"] == [["Alice Example", "Dr. Example"]]


def test_sql_pagination_and_response_cap(client):
    result = query(client, "SELECT followup_id FROM followups ORDER BY followup_id LIMIT ? OFFSET ?", [2, 2])
    assert result["rows"] == [["F003"], ["F004"]]
    assert result["truncated"] is False
    capped = query(client, "SELECT followup_id FROM followups ORDER BY followup_id", max_rows=2)
    assert capped["rows"] == [["F001"], ["F002"]]
    assert capped["truncated"] is True
    assert capped["row_count"] == 2
    exact = query(client, "SELECT patient_id FROM patients ORDER BY patient_id", max_rows=2)
    assert exact["truncated"] is False


def test_empty_result_retains_columns(client):
    result = query(client, "SELECT patient_id, name FROM patients WHERE patient_id = 'missing'")
    assert result == {"columns": ["patient_id", "name"], "rows": [], "row_count": 0, "truncated": False}


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
    assert client.post("/api/query", json={"query": "SELECT * FROM private_settings"}).status_code == 422


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
def test_disallowed_sql_cannot_change_database(client, database, sql):
    with closing(sqlite3.connect(database)) as connection:
        before = list(connection.iterdump())
    response = client.post("/api/query", json={"query": sql})
    assert response.status_code == 422, response.text
    with closing(sqlite3.connect(database)) as connection:
        assert list(connection.iterdump()) == before
    assert query(client, "SELECT COUNT(*) FROM patients")["rows"] == [[2]]


@pytest.mark.parametrize("body", [
    {}, {"query": "   "}, {"query": "x" * 20_001},
    {"query": "SELECT 1", "max_rows": 0}, {"query": "SELECT 1", "max_rows": 1_001},
    {"query": "SELECT 1", "filters": {}},
    {"query": "SELECT ?", "parameters": [["nested"]]},
    {"query": "SELECT 1", "parameters": [0] * 1_001},
    {"query": "SELECT 1", "max_rows": "10"},
])
def test_invalid_requests_return_422(client, body):
    assert client.post("/api/query", json=body).status_code == 422


@pytest.mark.parametrize(("sql", "parameters"), [
    ("not SQL", []), ("SELECT missing_column FROM patients", []),
    ("SELECT ?", []), ("SELECT 1", ["extra"]),
    ("SELECT :name", {"other": "missing"}),
    ("SELECT * FROM missing_table", []),
])
def test_invalid_sql_and_bindings_return_clear_errors(client, sql, parameters):
    response = client.post("/api/query", json={"query": sql, "parameters": parameters})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_query"


def test_recursive_query_has_execution_budget(client):
    response = client.post("/api/query", json={"query": """
        WITH RECURSIVE numbers(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM numbers)
        SELECT SUM(n) FROM numbers
    """})
    assert response.status_code == 408
    assert response.json()["detail"]["code"] == "query_limit_exceeded"
    assert query(client, "SELECT COUNT(*) FROM patients")["rows"] == [[2]]


def test_result_size_is_bounded(client, monkeypatch):
    monkeypatch.setattr("app.repository.MAX_RESULT_BYTES", 20)
    result = query(client, "SELECT name FROM patients ORDER BY patient_id")
    assert result["rows"] == [["Alice Example"]]
    assert result["truncated"] is True


@pytest.mark.parametrize("sql", ["SELECT X'FF'", "SELECT 1e999"])
def test_non_json_values_return_422(client, sql):
    response = client.post("/api/query", json={"query": sql})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_result"


def test_binary_can_be_requested_as_hex(client):
    assert query(client, "SELECT HEX(X'FF') AS value")["rows"] == [["FF"]]


def test_read_connection_cannot_write(database):
    with read_database() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("DELETE FROM followups")


def test_missing_database_returns_503_without_creating_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing.db"
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(missing))
    with TestClient(app) as client:
        for response in (
            client.get("/api/schema"),
            client.post("/api/query", json={"query": "SELECT * FROM patients"}),
        ):
            assert response.status_code == 503
            assert response.json()["detail"]["code"] == "database_unavailable"
    assert not missing.exists()


def test_comment_prefixed_sql_is_supported(client):
    assert query(client, "-- Read a patient\n SELECT patient_id FROM patients ORDER BY patient_id LIMIT 1;")["rows"] == [["P001"]]


def test_openapi_exposes_generic_endpoints_only(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/schema" in paths
    assert "requestBody" in paths["/api/query"]["post"]
    assert not any(path.startswith("/api/followups") for path in paths)
