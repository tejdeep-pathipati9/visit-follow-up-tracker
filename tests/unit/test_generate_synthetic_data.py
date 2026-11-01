"""Synthetic data generator: reproducible, linked, covers every flag, and has deliberate bad rows."""

from collections import Counter
from datetime import date, timedelta
import json

import pytest

from app.ingestion.models import FollowUpRecord, RecordRejection, validate_record
from app.ingestion.settings import load_settings
from app.rules import run_rules
from scripts.generate_synthetic_data import (
    BAD_VISIT_ID, CLEAN_FILE, DEFAULT_SEED, DEFAULT_VISITS, EXPECTED_FLAGS, MIN_VISITS, WITH_BAD_ROWS_FILE,
    generate, main,
)

AS_OF = date(2026, 10, 30)
KINDS = {"patients": "patient", "staff": "staff", "episodes": "episode"}


def flatten(data):
    """Split the nested file shape into flat records, the way the importer will."""
    visits, followups = [], []
    for visit in data["visits"]:
        visits.append({key: value for key, value in visit.items() if key != "followups"})
        followups += [{**followup, "visit_id": visit["visit_id"]} for followup in visit.get("followups", [])]
    return visits, followups


def validated(kind, records):
    results = [validate_record(kind, record, load_settings()) for record in records]
    assert not [result for result in results if isinstance(result, RecordRejection)], kind
    return results


@pytest.fixture(scope="module")
def generated():
    return generate(seed=42, as_of=AS_OF)


@pytest.fixture(scope="module")
def clean(generated):
    return generated.clean


# --- reproducibility ----------------------------------------------------------


def test_same_seed_and_date_give_identical_data():
    first = generate(seed=7, as_of=AS_OF)
    second = generate(seed=7, as_of=AS_OF)

    assert first == second


def test_different_seed_gives_different_data():
    assert generate(seed=1, as_of=AS_OF).clean != generate(seed=2, as_of=AS_OF).clean


def test_different_reference_date_moves_the_dates():
    later = generate(seed=42, as_of=AS_OF + timedelta(days=10))

    assert later.clean != generate(seed=42, as_of=AS_OF).clean


def test_files_are_byte_identical_across_runs(tmp_path):
    arguments = ["--seed", "42", "--as-of", "2026-10-30"]
    main([*arguments, "--output", str(tmp_path / "a")])
    main([*arguments, "--output", str(tmp_path / "b")])

    for name in (CLEAN_FILE, WITH_BAD_ROWS_FILE):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_changing_the_seed_changes_the_files(tmp_path):
    main(["--seed", "1", "--as-of", "2026-10-30", "--output", str(tmp_path / "a")])
    main(["--seed", "2", "--as-of", "2026-10-30", "--output", str(tmp_path / "b")])

    assert (tmp_path / "a" / CLEAN_FILE).read_bytes() != (tmp_path / "b" / CLEAN_FILE).read_bytes()


# --- linked records -----------------------------------------------------------


def test_every_record_is_linked_to_existing_parents(clean):
    patients = {patient["patient_id"] for patient in clean["patients"]}
    staff = {member["staff_id"] for member in clean["staff"]}
    episodes = {episode["episode_id"]: episode["patient_id"] for episode in clean["episodes"]}

    assert {episode["patient_id"] for episode in clean["episodes"]} <= patients
    for visit in clean["visits"]:
        assert visit["episode_id"] in episodes
        assert episodes[visit["episode_id"]] == visit["patient_id"]
        assert visit["staff_id"] is None or visit["staff_id"] in staff


def test_identifiers_are_unique_within_each_record_type(clean):
    visits, followups = flatten(clean)
    for name, records, key in (
        ("patients", clean["patients"], "patient_id"), ("staff", clean["staff"], "staff_id"),
        ("episodes", clean["episodes"], "episode_id"), ("visits", visits, "visit_id"),
        ("followups", followups, "followup_id"),
    ):
        ids = [record[key] for record in records]
        assert len(ids) == len(set(ids)), name


def test_an_episode_has_several_visits(clean):
    visits_per_episode = Counter(visit["episode_id"] for visit in clean["visits"])

    assert max(visits_per_episode.values()) >= 3


def test_a_patient_has_unrelated_episodes(clean):
    episodes_per_patient = Counter(episode["patient_id"] for episode in clean["episodes"])
    patient = next(patient for patient, count in episodes_per_patient.items() if count >= 2)
    own_episodes = [episode["episode_id"] for episode in clean["episodes"] if episode["patient_id"] == patient]
    visits_per_episode = Counter(visit["episode_id"] for visit in clean["visits"])

    assert all(visits_per_episode[episode] >= 1 for episode in own_episodes)
    assert len({episode["description"] for episode in clean["episodes"] if episode["patient_id"] == patient}) >= 2


def test_follow_ups_are_never_due_before_their_visit_and_visits_are_not_in_the_future(clean):
    visits, followups = flatten(clean)
    visit_dates = {visit["visit_id"]: visit["visit_date"] for visit in visits}

    assert all(visit["visit_date"] <= AS_OF.isoformat() for visit in visits)
    assert all(followup["due_date"] >= visit_dates[followup["visit_id"]] for followup in followups)


def test_episode_dates_are_consistent_with_their_visits(clean):
    visits, _ = flatten(clean)
    for episode in clean["episodes"]:
        dates = [visit["visit_date"] for visit in visits if visit["episode_id"] == episode["episode_id"]]
        assert episode["opened_at"] <= min(dates)
        assert episode["closed_at"] is None or episode["closed_at"] >= max(dates)


# --- the clean file passes the validator and covers every flag ----------------


def test_every_clean_record_passes_validation(clean):
    visits, followups = flatten(clean)

    for kind, records in (
        ("patient", clean["patients"]), ("staff", clean["staff"]), ("episode", clean["episodes"]),
        ("visit", visits), ("followup", followups),
    ):
        results = validated(kind, records)
        assert len(results) == len(records)


def test_scenario_follow_ups_get_exactly_the_expected_flags(clean):
    _, followups = flatten(clean)
    records = validated("followup", followups)

    flags = run_rules(records, AS_OF, load_settings())

    for followup_id, expected in EXPECTED_FLAGS.items():
        assert flags[followup_id] == expected, followup_id


def test_clean_data_covers_every_flag_and_combination(clean):
    _, followups = flatten(clean)
    flags = run_rules(validated("followup", followups), AS_OF, load_settings())
    seen = {tuple(value) for value in flags.values()}

    assert ("overdue",) in seen
    assert ("due_soon",) in seen
    assert ("unassigned",) in seen
    assert ("overdue", "unassigned") in seen
    assert ("due_soon", "unassigned") in seen
    assert () in seen


def test_scenarios_cover_the_window_boundaries_for_every_action_type(clean):
    _, followups = flatten(clean)
    by_id = {followup["followup_id"]: followup for followup in followups}
    boundaries = Counter()
    for followup_id, expected in EXPECTED_FLAGS.items():
        followup = by_id[followup_id]
        if followup["status"] == "open" and followup["assigned_staff_id"] is not None and "overdue" not in expected:
            days = (date.fromisoformat(followup["due_date"]) - AS_OF).days
            boundaries[(followup["action_type"], days, bool(expected))] += 1

    assert boundaries[("lab", 7, True)] and boundaries[("lab", 8, False)]
    assert boundaries[("referral", 14, True)] and boundaries[("referral", 15, False)]
    assert boundaries[("recheck", 14, True)] and boundaries[("recheck", 15, False)]


def test_due_today_is_present_and_due_soon(clean):
    _, followups = flatten(clean)
    flags = run_rules(validated("followup", followups), AS_OF, load_settings())
    today = [f["followup_id"] for f in followups if f["due_date"] == AS_OF.isoformat() and f["status"] == "open"]

    assert today
    assert all("due_soon" in flags[followup_id] and "overdue" not in flags[followup_id] for followup_id in today)


def test_closed_follow_ups_cover_every_reason_and_no_reason(clean):
    _, followups = flatten(clean)
    closed = [followup for followup in followups if followup["status"] == "closed"]

    assert {followup.get("closure_reason") for followup in closed} == {
        None, "completed", "patient_declined", "unable_to_reach", "appointment_cancelled",
    }
    assert all(followup["completed_at"] for followup in closed)
    assert all("closure_reason" not in f and "completed_at" not in f for f in followups if f["status"] == "open")


def test_the_hand_built_scenarios_alone_cover_every_closure_reason_and_flag_combination():
    # No random filler at the minimum size, so nothing here is covered by luck.
    data = generate(seed=1, as_of=AS_OF, visits=MIN_VISITS).clean
    _, followups = flatten(data)
    flags = run_rules(validated("followup", followups), AS_OF, load_settings())

    assert {f.get("closure_reason") for f in followups if f["status"] == "closed"} == {
        None, "completed", "patient_declined", "unable_to_reach", "appointment_cancelled",
    }
    assert {tuple(value) for value in flags.values()} == {
        (), ("overdue",), ("due_soon",), ("unassigned",), ("overdue", "unassigned"), ("due_soon", "unassigned"),
    }


def test_closed_follow_ups_include_one_that_is_past_due(clean):
    _, followups = flatten(clean)
    flags = run_rules(validated("followup", followups), AS_OF, load_settings())

    assert any(
        followup["status"] == "closed" and followup["due_date"] < AS_OF.isoformat() and not flags[followup["followup_id"]]
        for followup in followups
    )


def test_some_follow_ups_have_notes_and_some_have_none(clean):
    _, followups = flatten(clean)

    assert any(followup.get("notes") for followup in followups)
    assert any("notes" not in followup for followup in followups)


# --- bad rows -----------------------------------------------------------------


def test_clean_file_contains_none_of_the_bad_records(generated):
    text = json.dumps(generated.clean)

    assert "BAD" not in text and "MISSING" not in text


def test_bad_file_is_the_clean_data_plus_the_bad_records(generated):
    clean, with_bad = generated.clean, generated.with_bad_rows

    for name in ("patients", "staff", "episodes"):
        assert with_bad[name][: len(clean[name])] == clean[name]
    assert with_bad["visits"][: len(clean["visits"])] == clean["visits"]
    assert len(with_bad["visits"]) > len(clean["visits"])


def test_every_bad_case_is_in_the_bad_file_and_explained(generated):
    in_file = {
        "patient": generated.with_bad_rows["patients"], "staff": generated.with_bad_rows["staff"],
        "episode": generated.with_bad_rows["episodes"], "visit": generated.with_bad_rows["visits"],
        "followup": [f for v in generated.with_bad_rows["visits"] for f in v.get("followups", [])],
    }

    assert generated.bad_cases
    for case in generated.bad_cases:
        assert case.record in in_file[case.kind]
        assert case.why.strip()


def test_every_bad_case_is_rejected_for_its_intended_reason(generated):
    for case in generated.bad_cases:
        record = {**case.record, "visit_id": BAD_VISIT_ID} if case.kind == "followup" else case.record
        result = validate_record(case.kind, record, load_settings())

        if case.reason_contains is None:
            assert not isinstance(result, RecordRejection), case.record_id
        else:
            assert isinstance(result, RecordRejection), case.record_id
            assert result.record_id == case.record_id
            assert case.reason_contains in result.reason


def test_bad_cases_cover_the_required_kinds_of_bad_rows(generated):
    reasons = " ".join(case.reason_contains or "" for case in generated.bad_cases)

    for needed in ("patient_id", "action_type", "due_date", "followup_id", "completed_at", "closure_reason"):
        assert needed in reasons
    assert any(case.reason_contains is None for case in generated.bad_cases)


def test_references_to_missing_records_pass_validation_but_point_nowhere(generated):
    patients = {patient["patient_id"] for patient in generated.with_bad_rows["patients"]}
    episodes = {episode["episode_id"] for episode in generated.with_bad_rows["episodes"]}
    missing = [case for case in generated.bad_cases if case.reason_contains is None]

    assert missing
    for case in missing:
        if case.kind == "episode":
            assert case.record["patient_id"] not in patients
        else:
            assert case.record["episode_id"] not in episodes


def test_the_visit_that_carries_the_bad_follow_ups_is_itself_valid(generated):
    carrier = next(v for v in generated.with_bad_rows["visits"] if v["visit_id"] == BAD_VISIT_ID)
    record = {key: value for key, value in carrier.items() if key != "followups"}

    assert not isinstance(validate_record("visit", record, load_settings()), RecordRejection)
    assert len(carrier["followups"]) >= 5


# --- size ---------------------------------------------------------------------


def test_visit_count_is_respected():
    data = generate(seed=3, as_of=AS_OF, visits=75).clean

    assert len(data["visits"]) == 75


def test_default_size_is_small_and_at_least_the_minimum():
    assert MIN_VISITS <= DEFAULT_VISITS <= 100
    assert len(generate(seed=DEFAULT_SEED, as_of=AS_OF).clean["visits"]) == DEFAULT_VISITS


def test_the_smallest_allowed_size_still_has_every_scenario():
    data = generate(seed=3, as_of=AS_OF, visits=MIN_VISITS).clean
    _, followups = flatten(data)

    assert len(data["visits"]) == MIN_VISITS
    assert set(EXPECTED_FLAGS) <= {followup["followup_id"] for followup in followups}


def test_a_thousand_visits_are_generated_and_all_valid():
    data = generate(seed=5, as_of=AS_OF, visits=1000).clean
    visits, followups = flatten(data)

    assert len(visits) == 1000
    assert len(followups) >= 1000
    for kind, records in (("visit", visits), ("followup", followups), ("patient", data["patients"]),
                          ("episode", data["episodes"])):
        validated(kind, records)
    assert len({followup["followup_id"] for followup in followups}) == len(followups)


@pytest.mark.parametrize("visits", [MIN_VISITS - 1, 0, -5])
def test_too_few_visits_is_an_error(visits):
    with pytest.raises(ValueError, match="visits"):
        generate(seed=1, as_of=AS_OF, visits=visits)


@pytest.mark.parametrize("visits", [1.5, "40", None, True])
def test_non_integer_visit_count_is_an_error(visits):
    with pytest.raises(ValueError, match="visits"):
        generate(seed=1, as_of=AS_OF, visits=visits)


# --- no real patient information ----------------------------------------------


def test_contact_details_are_obviously_fake(clean):
    for patient in clean["patients"]:
        assert patient.get("email") is None or patient["email"].endswith("@example.test")
        assert patient.get("phone") is None or patient["phone"].startswith("555-01")
    assert any(patient.get("email") for patient in clean["patients"])
    assert any("email" not in patient for patient in clean["patients"])


def test_names_and_notes_say_they_are_synthetic(clean):
    assert all("Synthetic" in episode["description"] for episode in clean["episodes"])
    assert all("Synthetic" in (visit.get("notes") or "Synthetic") for visit in clean["visits"])


# --- command line -------------------------------------------------------------


def test_command_line_writes_both_files_as_json(tmp_path, capsys):
    main(["--seed", "42", "--as-of", "2026-10-30", "--output", str(tmp_path / "out")])

    output = capsys.readouterr().out
    for name in (CLEAN_FILE, WITH_BAD_ROWS_FILE):
        path = tmp_path / "out" / name
        assert str(path) in output
        text = path.read_text(encoding="utf-8")
        assert text.endswith("\n")
        assert set(json.loads(text)) == {"patients", "staff", "episodes", "visits"}


def test_command_line_accepts_a_visit_count(tmp_path):
    main(["--as-of", "2026-10-30", "--visits", "60", "--output", str(tmp_path)])

    assert len(json.loads((tmp_path / CLEAN_FILE).read_text(encoding="utf-8"))["visits"]) == 60


def test_command_line_does_not_touch_existing_files_it_does_not_own(tmp_path):
    other = tmp_path / "keep.json"
    other.write_text("{}", encoding="utf-8")

    main(["--as-of", "2026-10-30", "--output", str(tmp_path)])

    assert other.read_text(encoding="utf-8") == "{}"


@pytest.mark.parametrize(
    "arguments",
    [
        [],  # --as-of is required, so a file never depends on today's date
        ["--as-of", "2026-13-45"],
        ["--as-of", "20261030"],
        ["--as-of", "yesterday"],
        ["--as-of", "2026-10-30", "--seed", "abc"],
        ["--as-of", "2026-10-30", "--visits", "3"],
        ["--as-of", "2026-10-30", "--visits", "many"],
    ],
)
def test_command_line_rejects_bad_arguments_and_writes_nothing(tmp_path, arguments, capsys):
    with pytest.raises(SystemExit) as error:
        main([*arguments, "--output", str(tmp_path / "out")])

    assert error.value.code != 0
    assert not (tmp_path / "out").exists()
    assert capsys.readouterr().err


def test_command_line_reports_an_unwritable_output_folder(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        main(["--as-of", "2026-10-30", "--output", str(blocker / "out")])

    assert error.value.code != 0
