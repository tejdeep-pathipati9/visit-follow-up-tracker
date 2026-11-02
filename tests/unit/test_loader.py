"""Import file loading: every record is checked, and every problem is reported."""

import json

import pytest

from app.ingestion.loader import ExistingRecords, ImportFileError, load, read_file


def clean_file():
    return {
        "patients": [{"patient_id": "P001", "name": "Synthetic Patient"}],
        "staff": [{"staff_id": "S001", "name": "Dr. Example", "role": "doctor", "email": "dr@clinic.test"}],
        "episodes": [{"episode_id": "E001", "patient_id": "P001", "description": "Synthetic case", "opened_at": "2026-10-01"}],
        "visits": [{
            "visit_id": "V001", "patient_id": "P001", "episode_id": "E001", "staff_id": "S001",
            "visit_date": "2026-10-02", "followups": [
                {"followup_id": "F001", "action_type": "lab", "due_date": "2026-10-05", "assigned_staff_id": "S001"},
                {"followup_id": "F002", "action_type": "referral", "assigned_staff_id": "S001"},
            ],
        }],
    }


def rejections(data, existing=ExistingRecords()):
    return [(r.kind, r.record_id, r.reason) for r in load(data, existing).rejections]


def test_clean_file_has_no_rejections_and_follow_ups_get_their_visit():
    batch = load(clean_file(), ExistingRecords())
    assert batch.rejections == []
    assert [(f.followup_id, f.visit_id) for f in batch.followups] == [("F001", "V001"), ("F002", "V001")]
    assert batch.followups[1].due_date is None  # unassigned is valid


def test_every_problem_is_reported_not_just_the_first():
    data = clean_file()
    data["patients"].append({"patient_id": "P002"})  # no name
    data["visits"][0]["followups"].append({"followup_id": "F003", "action_type": "surgery", "assigned_staff_id": "S001"})
    data["episodes"].append({"episode_id": "E002", "patient_id": "P404", "description": "x", "opened_at": "2026-10-01"})
    found = rejections(data)
    assert [(kind, record_id) for kind, record_id, _ in found] == [("patient", "P002"), ("followup", "F003"), ("episode", "E002")]
    assert "P404 does not exist" in found[2][2]


@pytest.mark.parametrize(("change", "expected"), [
    (lambda d: d["visits"][0].update(staff_id="S404"), ("visit", "V001", "staff member S404 does not exist")),
    (lambda d: d["visits"][0].update(episode_id="E404"), ("visit", "V001", "episode E404 does not exist")),
    (lambda d: d["visits"][0]["followups"][0].update(assigned_staff_id="S404"), ("followup", "F001", "staff member S404 does not exist")),
    (lambda d: d["visits"][0]["followups"][0].update(visit_id="V999"), ("followup", "F001", "visit_id does not match visit V001, which it is listed under")),
    (lambda d: d["patients"].append({"patient_id": "P001", "name": "Again"}), ("patient", "P001", "the ID appears more than once in the file")),
    (lambda d: d["staff"].append({"staff_id": "S002", "name": "Dr. Copy", "role": "doctor", "email": "DR@clinic.test"}),
     ("staff", "S002", "email dr@clinic.test is already used by another staff member")),
])
def test_references_and_duplicates_are_checked_across_the_file(change, expected):
    data = clean_file()
    change(data)
    assert expected in rejections(data)


def test_visit_and_episode_must_belong_to_the_same_patient():
    data = clean_file()
    data["patients"].append({"patient_id": "P002", "name": "Other Patient"})
    data["visits"][0]["patient_id"] = "P002"
    assert ("visit", "V001", "episode E001 belongs to another patient") in rejections(data)


def test_records_already_saved_are_rejected_and_saved_parents_count():
    existing = ExistingRecords(patients=frozenset({"P001"}), staff=frozenset({"S009"}))
    data = clean_file()
    data["visits"][0]["staff_id"] = "S009"  # a staff member who is already saved is a valid reference
    assert rejections(data, existing) == [("patient", "P001", "a record with this ID is already saved")]


@pytest.mark.parametrize(("data", "message"), [
    ([], "one JSON object"),
    ({"patients": {}}, "patients must be a list"),
    ({"doctors": []}, "Unknown sections: doctors"),
])
def test_badly_shaped_files_are_refused(data, message):
    with pytest.raises(ImportFileError, match=message):
        load(data, ExistingRecords())


def test_read_file_names_the_problem(tmp_path):
    with pytest.raises(ImportFileError, match="not found"):
        read_file(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(ImportFileError, match="Not valid JSON"):
        read_file(broken)
    good = tmp_path / "good.json"
    good.write_text(json.dumps(clean_file()), encoding="utf-8")
    assert read_file(good) == clean_file()
