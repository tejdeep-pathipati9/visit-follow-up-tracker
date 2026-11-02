"""The whole tool on the synthetic files: generate, import, report, change, history.

Not covered: real clinic systems, a real browser (see the UI checks in the PR), passwords,
the OpenAI models, and Docker; those are checked by hand or in other tests.
"""

from datetime import date
import json

from fastapi.testclient import TestClient
import pytest

from app.main import app
from scripts.create_manager import create_manager
from scripts.generate_synthetic_data import EXPECTED_FLAGS, generate
from scripts.import_data import main as import_script
from scripts.table_generate import table_generate

AS_OF = date(2026, 10, 30)
MANAGER = "elm.overseer@clinic.example.test"
NURSE = "birch.sample@clinic.example.test"  # S002


@pytest.fixture
def files(tmp_path, monkeypatch):
    database = table_generate(tmp_path / "followups.db")
    monkeypatch.setenv("FOLLOWUP_DB_PATH", str(database))
    generated = generate(seed=42, as_of=AS_OF)
    paths = {}
    for name, data in (("clean", generated.clean), ("bad", generated.with_bad_rows)):
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_text(json.dumps(data), encoding="utf-8")
    return paths


def signed_in(email):
    client = TestClient(app)
    assert client.post("/api/session", json={"email": email}).status_code == 200, email
    return client


def test_generate_import_report_change_and_history(files, capsys):
    # A file with bad rows is refused whole; the clean file is then saved whole.
    assert import_script(["--file", str(files["bad"])]) == 1
    assert "nothing was saved" in capsys.readouterr().err
    assert import_script(["--file", str(files["clean"])]) == 0

    manager = signed_in(MANAGER)
    report = manager.get("/api/report", params={"as_of_date": AS_OF.isoformat()}).json()
    flagged = {f["followup_id"]: section["flag"] for section in report["sections"] for f in section["followups"]}
    for followup_id, expected in EXPECTED_FLAGS.items():
        assert flagged.get(followup_id) == (expected[0] if expected else None), followup_id
    page = manager.get("/report", params={"as_of_date": AS_OF.isoformat()})
    assert "Overdue (" in page.text and "F002" in page.text

    # The nurse sees only her follow-ups and closes one; the change is kept with her name.
    nurse = signed_in(NURSE)
    mine = nurse.get("/api/followups", params={"as_of_date": AS_OF.isoformat(), "limit": 1000}).json()["items"]
    assert mine and {f["assigned_staff_id"] for f in mine} == {"S002"}
    closed = nurse.patch("/api/followups/F002", json={"status": "closed", "notes": "Patient unreachable after three calls"},
                         params={"as_of_date": AS_OF.isoformat()})
    assert closed.status_code == 200 and closed.json()["flags"] == []
    history = manager.get("/api/followups/F002").json()["history"]
    assert [(h["field"], h["new_value"], h["changed_by"]) for h in history] == [("status", "closed", "S002")]

    # The patient's history still shows every episode and visit.
    patient = manager.get("/api/patients/P001", params={"as_of_date": AS_OF.isoformat()}).json()
    assert [e["episode_id"] for e in patient["episodes"]] == ["E001", "E002"]
    assert sum(len(e["visits"]) for e in patient["episodes"]) == 4

    # Importing the clean file again would duplicate everything, so it is refused.
    again = manager.post("/api/import", json=json.loads(files["clean"].read_text(encoding="utf-8")))
    assert again.status_code == 422 and again.json()["saved"] is False


def test_first_start_with_a_script_manager_then_imports_from_the_app(files):
    # The README's first start: add a manager, sign in, and import the files in the app.
    assert create_manager("Clinic Manager", "manager@clinic.example.test") == "M001"
    manager = signed_in("manager@clinic.example.test")
    bad = manager.post("/api/import", json=json.loads(files["bad"].read_text(encoding="utf-8")))
    assert bad.status_code == 422 and len(bad.json()["rejections"]) == 12
    clean = manager.post("/api/import", json=json.loads(files["clean"].read_text(encoding="utf-8")))
    assert clean.status_code == 200 and clean.json()["saved"] is True
