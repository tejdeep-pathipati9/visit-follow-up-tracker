"""Record validation: accepted records and rejection reasons for every record type."""

from datetime import date

import pytest

from app.ingestion.models import (
    EpisodeRecord, FollowUpRecord, PatientRecord, RecordRejection, StaffRecord, VisitRecord,
    validate_record,
)
from app.ingestion.settings import Settings


def patient(**overrides):
    return {"patient_id": "P001", "name": "Sample Patient", **overrides}


def staff(**overrides):
    return {"staff_id": "S001", "name": "Dr. Example", "role": "doctor", **overrides}


def episode(**overrides):
    return {
        "episode_id": "E001", "patient_id": "P001", "description": "Synthetic case",
        "opened_at": "2026-10-15", **overrides,
    }


def visit(**overrides):
    return {
        "visit_id": "V001", "patient_id": "P001", "episode_id": "E001", "staff_id": "S001",
        "visit_date": "2026-10-15", "notes": "Synthetic visit", **overrides,
    }


def followup(**overrides):
    return {
        "followup_id": "F001", "visit_id": "V001", "action_type": "lab",
        "due_date": "2026-10-20", "assigned_staff_id": "S001", "status": "open", **overrides,
    }


def reject(kind, raw, settings=None):
    result = validate_record(kind, raw, settings)
    assert isinstance(result, RecordRejection)
    return result


# --- accepted records ---------------------------------------------------------


def test_valid_follow_up_is_accepted_and_dates_are_parsed():
    result = validate_record("followup", followup())

    assert isinstance(result, FollowUpRecord)
    assert result.due_date == date(2026, 10, 20)
    assert result.status == "open"


def test_follow_up_without_assigned_staff_is_rejected():
    # Every follow-up comes from a patient visit, so a staff member is always responsible.
    for raw in (followup(assigned_staff_id=None), {k: v for k, v in followup().items() if k != "assigned_staff_id"}):
        assert "assigned_staff_id" in reject("followup", raw).reason


def test_follow_up_status_defaults_to_open():
    raw = {k: v for k, v in followup().items() if k != "status"}

    assert validate_record("followup", raw).status == "open"


def test_done_follow_up_with_completion_time_is_accepted():
    result = validate_record("followup", followup(status="done", completed_at="2026-10-21T12:00:00Z"))

    assert isinstance(result, FollowUpRecord)
    assert (result.status, result.completed_at) == ("done", "2026-10-21T12:00:00Z")


@pytest.mark.parametrize("reason", ["Patient unreachable after three calls", "Did not return", "No results sent"])
def test_closed_follow_up_with_a_reason_in_notes_is_accepted(reason):
    result = validate_record("followup", followup(status="closed", completed_at="2026-10-21", notes=reason))

    assert (result.status, result.notes) == ("closed", reason)


def test_notes_are_optional_free_text_unless_closed():
    text = "Patient asked to be called after 5pm.\nSecond line, with punctuation: ok!"
    open_result = validate_record("followup", followup(notes=f"  {text}  "))
    done_result = validate_record("followup", followup(status="done", completed_at="2026-10-21", notes=text))

    assert open_result.notes == text
    assert done_result.notes == text
    assert validate_record("followup", followup()).notes is None
    assert validate_record("followup", followup(notes=None)).notes is None


@pytest.mark.parametrize("blank", ["", "   \n"])
def test_blank_notes_are_treated_as_no_notes(blank):
    assert validate_record("followup", followup(notes=blank)).notes is None


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("2026-10-26T12:00:00Z", "2026-10-26T12:00:00Z"),
        ("20261026T120000Z", "2026-10-26T12:00:00Z"),
        ("2026-10-26 12:00:00+00:00", "2026-10-26T12:00:00Z"),
        ("2026-10-26T14:30:00+02:00", "2026-10-26T12:30:00Z"),
        ("2026-10-26T23:30:00-05:00", "2026-10-27T04:30:00Z"),
        ("2026-10-26T12:00:00.987654Z", "2026-10-26T12:00:00Z"),
        ("2026-10-26", "2026-10-26T00:00:00Z"),
    ],
)
def test_completion_time_is_stored_in_one_utc_format(given, stored):
    # Searches read the first 10 characters of completed_at as the date.
    result = validate_record("followup", followup(status="done", completed_at=given))

    assert result.completed_at == stored


def test_completion_time_without_a_timezone_is_rejected():
    result = reject("followup", followup(status="closed", completed_at="2026-10-26T12:00:00"))

    assert "completed_at" in result.reason
    assert "timezone" in result.reason


def test_identifiers_are_stripped():
    assert validate_record("followup", followup(followup_id="  F001  ")).followup_id == "F001"


def test_valid_patient_staff_episode_and_visit_are_accepted():
    assert isinstance(validate_record("patient", patient(phone="555-0100", email="a@example.test")), PatientRecord)
    assert isinstance(validate_record("staff", staff()), StaffRecord)
    assert isinstance(validate_record("episode", episode()), EpisodeRecord)
    assert isinstance(validate_record("visit", visit()), VisitRecord)


def test_open_episode_and_visit_without_notes_are_accepted():
    assert validate_record("episode", episode(closed_at=None)).closed_at is None
    assert validate_record("visit", visit(notes=None)).notes is None


@pytest.mark.parametrize("raw", [visit(staff_id=None), {k: v for k, v in visit().items() if k != "staff_id"}])
def test_visit_without_staff_is_rejected(raw):
    # A visit is a consultation, test, or treatment, so someone always carries it out.
    assert "staff_id" in reject("visit", raw).reason


def test_episode_closed_on_the_day_it_opened_is_accepted():
    assert isinstance(validate_record("episode", episode(closed_at="2026-10-15")), EpisodeRecord)


# --- follow-up rejections -----------------------------------------------------


@pytest.mark.parametrize("field", ["followup_id", "visit_id", "action_type"])
def test_follow_up_missing_required_field_is_rejected_naming_the_field(field):
    raw = {k: v for k, v in followup().items() if k != field}

    result = reject("followup", raw)

    assert field in result.reason
    assert "required" in result.reason.lower()


@pytest.mark.parametrize("field", ["followup_id", "visit_id"])
@pytest.mark.parametrize("value", ["", "   ", None, 7])
def test_follow_up_blank_or_non_string_identifier_is_rejected(field, value):
    assert field in reject("followup", followup(**{field: value})).reason


def test_follow_up_identifier_longer_than_limit_is_rejected():
    assert "followup_id" in reject("followup", followup(followup_id="F" * 51)).reason


@pytest.mark.parametrize(
    "value", ["2026-13-45", "2026-02-30", "not a date", "20/10/2026", "20261020", "", 20261020, 1.5]
)
def test_follow_up_invalid_due_date_is_rejected(value):
    assert "due_date" in reject("followup", followup(due_date=value)).reason


def test_follow_up_without_a_scheduled_date_is_accepted_as_unassigned():
    missing = {k: v for k, v in followup().items() if k != "due_date"}

    for raw in (missing, followup(due_date=None)):
        result = validate_record("followup", raw)
        assert isinstance(result, FollowUpRecord)
        assert result.due_date is None


def test_follow_up_unsupported_action_type_lists_the_allowed_types():
    result = reject("followup", followup(action_type="surgery"))

    assert "action_type" in result.reason
    for allowed in ("lab", "referral", "recheck"):
        assert allowed in result.reason


@pytest.mark.parametrize("value", ["Lab", "", None, 3])
def test_follow_up_action_type_must_match_exactly(value):
    assert "action_type" in reject("followup", followup(action_type=value)).reason


def test_action_type_outside_the_configured_settings_is_rejected():
    settings = Settings(allowed_action_types=["lab"], due_soon_days_by_action={"lab": 7})

    result = reject("followup", followup(action_type="referral"), settings)

    assert "action_type" in result.reason
    assert "lab" in result.reason
    assert isinstance(validate_record("followup", followup(action_type="lab"), settings), FollowUpRecord)


def test_follow_up_with_unknown_status_is_rejected():
    assert "status" in reject("followup", followup(status="pending")).reason


def test_open_follow_up_with_completion_time_is_rejected():
    assert "completed_at" in reject("followup", followup(completed_at="2026-10-21")).reason


def test_follow_up_with_invalid_completion_time_is_rejected():
    assert "completed_at" in reject("followup", followup(status="closed", completed_at="yesterday")).reason


@pytest.mark.parametrize("status", ["done", "closed"])
def test_finished_follow_up_without_completion_time_is_rejected(status):
    assert "completed_at" in reject("followup", followup(status=status, notes="Reason")).reason
    assert "completed_at" in reject("followup", followup(status=status, completed_at=None, notes="Reason")).reason


@pytest.mark.parametrize("notes", [None, "", "   "])
def test_closed_follow_up_without_a_reason_is_rejected(notes):
    result = reject("followup", followup(status="closed", completed_at="2026-10-21", notes=notes))

    assert "notes" in result.reason
    assert "reason" in result.reason


def test_closure_reason_field_is_not_accepted():
    # The reason goes in notes, as the clinic asked.
    assert "closure_reason" in reject("followup", followup(closure_reason="completed")).reason


@pytest.mark.parametrize("notes", [5, ["a"], "x" * 2001])
def test_notes_must_be_text_within_the_length_limit(notes):
    assert "notes" in reject("followup", followup(notes=notes)).reason


def test_closed_follow_up_missing_time_and_reason_reports_both():
    result = reject("followup", followup(status="closed"))

    assert "completed_at" in result.reason
    assert "notes" in result.reason


def test_follow_up_with_unexpected_field_is_rejected():
    assert "surprise" in reject("followup", followup(surprise=True)).reason


def test_follow_up_with_blank_assigned_staff_is_rejected():
    assert "assigned_staff_id" in reject("followup", followup(assigned_staff_id="  ")).reason


def test_follow_up_with_several_problems_reports_each_one():
    result = reject("followup", followup(followup_id=None, action_type="surgery", due_date="bad"))

    for field in ("followup_id", "action_type", "due_date"):
        assert field in result.reason


# --- other record rejections --------------------------------------------------


def test_visit_missing_patient_id_is_rejected():
    raw = {k: v for k, v in visit().items() if k != "patient_id"}

    result = reject("visit", raw)

    assert "patient_id" in result.reason
    assert result.record_id == "V001"


@pytest.mark.parametrize("field", ["visit_id", "episode_id", "visit_date"])
def test_visit_missing_required_field_is_rejected(field):
    raw = {k: v for k, v in visit().items() if k != field}

    assert field in reject("visit", raw).reason


def test_visit_with_invalid_date_is_rejected():
    assert "visit_date" in reject("visit", visit(visit_date="2026-99-01")).reason


@pytest.mark.parametrize(
    ("kind", "raw", "field"),
    [
        ("patient", {"patient_id": "P001"}, "name"),
        ("patient", patient(name="  "), "name"),
        ("patient", {"name": "No Id"}, "patient_id"),
        ("staff", {"staff_id": "S001", "name": "Dr. Example"}, "role"),
        ("staff", staff(staff_id=""), "staff_id"),
        ("episode", {k: v for k, v in episode().items() if k != "patient_id"}, "patient_id"),
        ("episode", episode(opened_at="2026-02-30"), "opened_at"),
        ("episode", episode(closed_at="soon"), "closed_at"),
    ],
)
def test_other_record_types_reject_missing_or_invalid_fields(kind, raw, field):
    assert field in reject(kind, raw).reason


def test_episode_closed_before_it_opened_is_rejected():
    assert "closed_at" in reject("episode", episode(closed_at="2026-10-14")).reason


# --- rejection details --------------------------------------------------------


def test_rejection_carries_the_record_kind_and_id():
    result = reject("followup", followup(action_type="surgery"))

    assert (result.kind, result.record_id) == ("followup", "F001")


def test_rejection_without_a_usable_id_says_unknown():
    assert reject("followup", followup(followup_id=None)).record_id == "unknown"
    assert reject("followup", {}).record_id == "unknown"


@pytest.mark.parametrize("raw", [None, "text", 7, ["F001"]])
def test_record_that_is_not_an_object_is_rejected(raw):
    result = reject("followup", raw)

    assert "object" in result.reason
    assert result.record_id == "unknown"


def test_unknown_record_kind_is_a_programming_error():
    with pytest.raises(ValueError, match="Unknown record kind"):
        validate_record("invoice", {})


def test_rejection_reason_is_plain_text_without_pydantic_prefixes():
    result = reject("followup", followup(due_date="2026-13-45"))

    assert "Value error" not in result.reason
    assert "pydantic" not in result.reason.lower()
