"""Importing a file through the API and the script: all of it, or none of it."""

from contextlib import closing
from datetime import date
import json
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.main import app
from scripts.generate_synthetic_data import generate
from scripts.import_data import main as import_script
from scripts.table_generate import table_generate
from tests.conftest import AS_OF


def count(database, table):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


NEW_FILE = {
    "patients": [{"patient_id": "P100", "name": "Imported Patient"}],
    "episodes": [{"episode_id": "E100", "patient_id": "P100", "description": "Synthetic case", "opened_at": "2026-10-20"}],
    "visits": [{
        "visit_id": "V100", "patient_id": "P100", "episode_id": "E100", "staff_id": "S002", "visit_date": "2026-10-21",
        "followups": [{"followup_id": "F100", "action_type": "lab", "assigned_staff_id": "S002"}],
    }],
}


def test_clean_file_is_saved_and_its_follow_ups_are_flagged(client, database):
    response = client.post("/api/import", json=NEW_FILE)
    assert response.status_code == 200, response.text
    assert response.json()["counts"] == {"patients": 1, "staff": 0, "episodes": 1, "visits": 1, "followups": 1}
    followup = client.get("/api/followups/F100", params={"as_of_date": AS_OF}).json()["followup"]
    assert (followup["patient_id"], followup["flags"]) == ("P100", ["unassigned"])


def test_a_file_with_any_bad_record_saves_nothing(client, database):
    bad = {**NEW_FILE, "patients": [*NEW_FILE["patients"], {"patient_id": "P101"}]}
    response = client.post("/api/import", json=bad)
    assert response.status_code == 422
    body = response.json()
    assert body["saved"] is False
    assert body["rejections"] == [{"kind": "patient", "record_id": "P101", "reason": "name: Field required"}]
    assert (count(database, "patients"), count(database, "followups")) == (2, 7)


def test_importing_the_same_file_twice_does_not_duplicate(client, database):
    assert client.post("/api/import", json=NEW_FILE).status_code == 200
    again = client.post("/api/import", json=NEW_FILE)
    assert again.status_code == 422
    assert {r["record_id"] for r in again.json()["rejections"]} == {"P100", "E100", "V100", "F100"}
    assert count(database, "patients") == 3


def test_a_failed_save_leaves_nothing_behind(client, database):
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("CREATE TRIGGER refuse_followups BEFORE INSERT ON followups BEGIN SELECT RAISE(ABORT, 'disk full'); END")
        connection.commit()
    response = client.post("/api/import", json=NEW_FILE)
    assert response.status_code == 409
    assert (count(database, "patients"), count(database, "episodes"), count(database, "visits")) == (2, 2, 2)


def test_only_a_manager_imports(database):
    with TestClient(app) as client:
        client.post("/api/session", json={"email": "sample@clinic.test"})
        assert client.post("/api/import", json=NEW_FILE).status_code == 403


@pytest.mark.parametrize(("body", "message"), [([1, 2], "one JSON object"), ({"visits": "V1"}, "visits must be a list")])
def test_badly_shaped_file_is_refused(client, database, body, message):
    response = client.post("/api/import", json=body)
    assert response.status_code == 422
    assert message in response.json()["detail"]["message"]


def test_script_imports_the_generated_files(tmp_path, capsys, monkeypatch):
    database = table_generate(tmp_path / "followups.db")
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(database))  # restored after the test; the script sets it too
    generated = generate(seed=42, as_of=date(2026, 10, 26))
    clean, bad = tmp_path / "clean.json", tmp_path / "bad.json"
    clean.write_text(json.dumps(generated.clean), encoding="utf-8")
    bad.write_text(json.dumps(generated.with_bad_rows), encoding="utf-8")

    assert import_script(["--file", str(bad), "--db-path", str(database)]) == 1
    assert "nothing was saved" in capsys.readouterr().err
    assert count(database, "patients") == 0
    assert import_script(["--file", str(clean), "--db-path", str(database)]) == 0
    assert "40 visits" in capsys.readouterr().out
    assert count(database, "visits") == 40
