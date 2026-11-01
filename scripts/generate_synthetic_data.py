"""Write reproducible synthetic clinic data: one clean file and one with deliberate bad rows.

Every patient, staff member, visit, and follow-up is invented here; nothing comes from real
people. Dates are relative to --as-of, so the same seed and date always give identical files.
The importer refuses a whole file that contains a bad row, so the two files show both outcomes.
"""

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
import json
from pathlib import Path
import random
import re
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "generated"
CLEAN_FILE = "clean_visits.json"
WITH_BAD_ROWS_FILE = "visits_with_bad_rows.json"
DEFAULT_SEED = 42
DEFAULT_VISITS = 40
BAD_VISIT_ID = "VBAD00"  # a valid visit that carries the bad follow-ups

ACTION_TYPES = ("lab", "referral", "recheck")
CLOSURE_REASONS = ("completed", "patient_declined", "unable_to_reach", "appointment_cancelled")

FIRST_NAMES = ("Avery", "Blake", "Casey", "Devon", "Emery", "Finley", "Harper", "Jordan", "Kendall", "Logan")
LAST_NAMES = ("Testwell", "Samplewood", "Exampleton", "Mockley", "Demoson", "Fakeman", "Placeholder", "Dummerfield")
CONDITIONS = (
    "ankle sprain", "asthma review", "blood pressure check", "skin rash", "back pain", "migraine follow-up",
    "diabetes review", "wrist injury", "allergy review", "sleep problems",
)
NOTES = (
    "Patient prefers morning calls", "Result needed before next visit", "Family member will help with travel",
    "Check if the patient has transport", "Remind about fasting before the test",
)

# Scenario data, built from fixed offsets (in days) from --as-of. Each follow-up is listed with the
# flags it must get under the shipped settings (lab 7, referral 14, recheck 14 days), so the
# boundaries are written down once and tested against the real rules.
STAFF = (
    ("S001", "Dr. Alder Example", "doctor"),
    ("S002", "Nurse Birch Sample", "nurse"),
    ("S003", "Dr. Cedar Testcase", "doctor"),
    ("S004", "Coordinator Dune Mock", "coordinator"),
)
PATIENTS = (
    ("P001", "Avery Testwell", "555-0101", "avery.testwell@example.test"),
    ("P002", "Blake Samplewood", None, None),
    ("P003", "Casey Exampleton", "555-0103", None),
    ("P004", "Devon Mockley", None, "devon.mockley@example.test"),
    ("P005", "Emery Demoson", "555-0105", "emery.demoson@example.test"),
)
# (episode, patient, description, [(visit, staff, visit offset)])
EPISODES = (
    ("E001", "P001", "Synthetic knee injury", [("V001", "S001", -60), ("V002", "S002", -45), ("V003", "S001", -20)]),
    ("E002", "P001", "Synthetic annual checkup", [("V004", "S002", -12)]),
    ("E003", "P002", "Synthetic diabetes review", [("V005", "S003", -30), ("V006", "S001", -3)]),
    ("E004", "P003", "Synthetic wrist sprain", [("V007", "S002", -8)]),
    ("E005", "P004", "Synthetic asthma review", [("V008", "S003", -6)]),
    ("E006", "P005", "Synthetic blood pressure check", [("V009", "S001", -2)]),
)
CLOSED_EPISODES = {"E002"}
# (follow-up, visit, action, due offset, staff, expected flags, closure, note)
# closure is None for an open follow-up, else (completed offset, reason or None).
SCENARIOS = (
    ("F001", "V001", "lab", -50, "S001", [], (-48, "completed"), None),  # closed and long past due: no flag
    ("F002", "V001", "referral", -30, None, ["overdue", "unassigned"], None, "Patient prefers morning calls"),
    ("F003", "V002", "recheck", -10, "S002", ["overdue"], None, None),
    ("F004", "V002", "lab", -1, "S001", ["overdue"], None, None),  # due yesterday: overdue
    ("F005", "V003", "lab", 0, "S001", ["due_soon"], None, None),  # due today: still due soon
    ("F006", "V003", "referral", 0, None, ["due_soon", "unassigned"], None, "Referral letter not yet sent"),
    ("F007", "V004", "lab", 7, "S002", ["due_soon"], None, None),  # last day of the lab window
    ("F008", "V004", "lab", 8, "S002", [], None, None),  # one day outside the lab window
    ("F009", "V005", "referral", 14, "S003", ["due_soon"], None, None),  # last day of the referral window
    ("F010", "V005", "referral", 15, "S003", [], None, None),
    ("F011", "V006", "recheck", 14, "S001", ["due_soon"], None, None),  # last day of the recheck window
    ("F012", "V006", "recheck", 15, "S001", [], None, None),
    ("F013", "V007", "lab", 3, None, ["due_soon", "unassigned"], None, None),
    ("F014", "V007", "recheck", 60, "S002", [], None, None),  # assigned and far away: no flags
    ("F015", "V008", "referral", 30, None, ["unassigned"], None, None),
    ("F016", "V005", "lab", -20, "S003", [], (-22, "patient_declined"), "Patient said they will arrange it"),
    ("F017", "V009", "recheck", 5, None, [], (-1, "unable_to_reach"), "Three call attempts, no answer"),
    ("F018", "V009", "referral", -2, "S001", [], (-2, "appointment_cancelled"), "Clinic closed that day"),
    ("F019", "V009", "lab", 10, "S002", [], (-1, "completed"), None),
    ("F020", "V008", "lab", -5, "S004", [], (-5, None), None),  # closed without a reason
)
EXPECTED_FLAGS = {scenario[0]: scenario[5] for scenario in SCENARIOS}
MIN_VISITS = sum(len(visits) for *_, visits in EPISODES)


@dataclass(frozen=True)
class BadCase:
    """One deliberate bad record, and why it is in the file."""

    kind: str
    record: dict
    record_id: str  # "unknown" when the record has no usable identifier
    reason_contains: str | None  # None: well-formed, but it points at a record that does not exist
    why: str


@dataclass(frozen=True)
class Generated:
    clean: dict
    with_bad_rows: dict
    bad_cases: tuple[BadCase, ...]


def timestamp(day: date) -> str:
    return f"{day.isoformat()}T09:30:00Z"


def contact(rng: random.Random, number: int) -> dict:
    """Optional phone and email, in ranges that cannot belong to real people."""
    details = {}
    if rng.random() < 0.5:
        details["phone"] = f"555-01{rng.randint(0, 99):02d}"
    if rng.random() < 0.6:
        details["email"] = f"patient{number:03d}@example.test"
    return details


def build_clean(rng: random.Random, as_of: date, visits: int) -> dict:
    def at(offset: int) -> date:
        return as_of + timedelta(days=offset)

    patients = [
        {"patient_id": pid, "name": name, **({"phone": phone} if phone else {}), **({"email": email} if email else {})}
        for pid, name, phone, email in PATIENTS
    ]
    staff = [{"staff_id": sid, "name": name, "role": role} for sid, name, role in STAFF]
    episodes, visit_records, visit_by_id = [], [], {}
    for episode_id, patient_id, description, episode_visits in EPISODES:
        first = min(offset for *_, offset in episode_visits)
        last = max(offset for *_, offset in episode_visits)
        episodes.append({
            "episode_id": episode_id, "patient_id": patient_id, "description": description,
            "opened_at": at(first).isoformat(),
            "closed_at": at(last).isoformat() if episode_id in CLOSED_EPISODES else None,
        })
        for visit_id, staff_id, offset in episode_visits:
            record = {
                "visit_id": visit_id, "patient_id": patient_id, "episode_id": episode_id, "staff_id": staff_id,
                "visit_date": at(offset).isoformat(), "notes": "Synthetic visit", "followups": [],
            }
            visit_records.append(record)
            visit_by_id[visit_id] = record
    for followup_id, visit_id, action, due, staff_id, _, closure, note in SCENARIOS:
        followup = {
            "followup_id": followup_id, "action_type": action, "due_date": at(due).isoformat(),
            "assigned_staff_id": staff_id, "status": "open" if closure is None else "closed",
        }
        if closure is not None:
            followup["completed_at"] = timestamp(at(closure[0]))
            if closure[1] is not None:
                followup["closure_reason"] = closure[1]
        if note:
            followup["notes"] = note
        visit_by_id[visit_id]["followups"].append(followup)

    # Filler: random but reproducible, only to reach the requested number of visits.
    filler = []  # (patient id, episode record) for every filler episode
    patient_count, episode_count, followup_count = len(PATIENTS), len(EPISODES), len(SCENARIOS)
    filler_patients = []
    for number in range(len(visit_records) + 1, visits + 1):
        if filler and rng.random() < 0.35:
            patient_id, episode = rng.choice(filler)
        else:
            if filler_patients and rng.random() < 0.3:
                patient_id = rng.choice(filler_patients)
            else:
                patient_count += 1
                patient_id = f"P{patient_count:03d}"
                filler_patients.append(patient_id)
                patients.append({
                    "patient_id": patient_id,
                    "name": f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}",
                    **contact(rng, patient_count),
                })
            episode_count += 1
            episode = {
                "episode_id": f"E{episode_count:03d}", "patient_id": patient_id,
                "description": f"Synthetic {rng.choice(CONDITIONS)}", "opened_at": None,
                "closed_at": None, "_closed": rng.random() < 0.25,
            }
            episodes.append(episode)
            filler.append((patient_id, episode))
        offset = -rng.randint(0, 120)
        staff_id = None if rng.random() < 0.15 else rng.choice(STAFF)[0]
        followups = []
        for _ in range(rng.randint(1, 3)):
            followup_count += 1
            due = offset + rng.randint(0, 60)  # never before the visit
            followup = {
                "followup_id": f"F{followup_count:03d}", "action_type": rng.choice(ACTION_TYPES),
                "due_date": at(due).isoformat(),
                "assigned_staff_id": None if rng.random() < 0.25 else rng.choice(STAFF)[0],
                "status": "open",
            }
            if rng.random() < 0.2:
                followup["status"] = "closed"
                followup["completed_at"] = timestamp(at(rng.randint(offset, 0)))
                if rng.random() < 0.75:
                    followup["closure_reason"] = rng.choice(CLOSURE_REASONS)
            if rng.random() < 0.2:
                followup["notes"] = rng.choice(NOTES)
            followups.append(followup)
        visit_records.append({
            "visit_id": f"V{number:03d}", "patient_id": patient_id, "episode_id": episode["episode_id"],
            "staff_id": staff_id, "visit_date": at(offset).isoformat(), "notes": "Synthetic visit",
            "followups": followups,
        })

    # Filler episodes open on their first visit and, if closed, close on their last.
    dates = {}
    for visit in visit_records:
        dates.setdefault(visit["episode_id"], []).append(visit["visit_date"])
    for episode in episodes:
        if episode["opened_at"] is None:
            episode["opened_at"] = min(dates[episode["episode_id"]])
            episode["closed_at"] = max(dates[episode["episode_id"]]) if episode.pop("_closed") else None
    return {"patients": patients, "staff": staff, "episodes": episodes, "visits": visit_records}


def build_bad_rows(clean: dict, as_of: date) -> tuple[dict, tuple[BadCase, ...]]:
    day = lambda offset: (as_of + timedelta(days=offset)).isoformat()  # noqa: E731
    carrier_followups = [
        BadCase("followup", {
            "followup_id": "FBAD01", "action_type": "surgery", "due_date": day(5),
            "assigned_staff_id": "S001", "status": "open",
        }, "FBAD01", "action_type", "Unknown action type: only lab, referral and recheck are allowed."),
        BadCase("followup", {
            "followup_id": "FBAD02", "action_type": "lab", "due_date": "2026-13-45",
            "assigned_staff_id": "S001", "status": "open",
        }, "FBAD02", "due_date", "Invalid date: month 13 does not exist."),
        BadCase("followup", {
            "action_type": "lab", "due_date": day(5), "assigned_staff_id": "S001", "status": "open",
        }, "unknown", "followup_id", "Missing identifier: the rejection cannot name the record."),
        BadCase("followup", {
            "followup_id": "FBAD04", "action_type": "lab", "due_date": day(5),
            "assigned_staff_id": "S001", "status": "closed",
        }, "FBAD04", "completed_at", "Closed without a closure time."),
        BadCase("followup", {
            "followup_id": "FBAD05", "action_type": "lab", "due_date": day(5), "assigned_staff_id": "S001",
            "status": "open", "closure_reason": "completed",
        }, "FBAD05", "closure_reason", "A closure reason on a follow-up that is still open."),
    ]
    cases = (
        BadCase("patient", {"patient_id": "PBAD01"}, "PBAD01", "name", "Patient without a name."),
        BadCase("staff", {"staff_id": "SBAD01", "name": "Dr. Missing Role"}, "SBAD01", "role",
                "Staff member without a role."),
        BadCase("episode", {
            "episode_id": "EBAD01", "patient_id": "P001", "description": "Synthetic episode closed before it opened",
            "opened_at": day(-10), "closed_at": day(-20),
        }, "EBAD01", "closed_at", "Episode that closes before it opens."),
        BadCase("episode", {
            "episode_id": "EBAD02", "patient_id": "PMISSING", "description": "Synthetic episode for a missing patient",
            "opened_at": day(-10),
        }, "EBAD02", None, "Well-formed, but the patient does not exist: only a reference check catches this."),
        BadCase("visit", {
            "visit_id": "VBAD01", "episode_id": "E001", "staff_id": "S001", "visit_date": day(-1),
            "notes": "Synthetic visit without a patient",
        }, "VBAD01", "patient_id", "Visit without a patient ID."),
        BadCase("visit", {
            "visit_id": "VBAD02", "patient_id": "P001", "episode_id": "EMISSING", "staff_id": "S001",
            "visit_date": day(-1), "notes": "Synthetic visit for a missing episode",
        }, "VBAD02", None, "Well-formed, but the episode does not exist: only a reference check catches this."),
        *carrier_followups,
    )
    with_bad_rows = deepcopy(clean)
    for case in cases:
        if case.kind == "followup":
            continue
        collection = {"patient": "patients", "staff": "staff", "episode": "episodes", "visit": "visits"}[case.kind]
        with_bad_rows[collection].append(deepcopy(case.record))
    carrier = {
        "visit_id": BAD_VISIT_ID, "patient_id": "P001", "episode_id": "E001", "staff_id": "S001",
        "visit_date": day(-1), "notes": "Synthetic visit that carries the bad follow-ups",
        "followups": [deepcopy(case.record) for case in cases if case.kind == "followup"],
    }
    with_bad_rows["visits"].insert(len(clean["visits"]), carrier)
    return with_bad_rows, cases


def generate(seed: int, as_of: date, visits: int = DEFAULT_VISITS) -> Generated:
    if isinstance(visits, bool) or not isinstance(visits, int):
        raise ValueError(f"visits must be an integer, not {visits!r}")
    if visits < MIN_VISITS:
        raise ValueError(f"visits must be at least {MIN_VISITS} to include every scenario, got {visits}")
    clean = build_clean(random.Random(seed), as_of, visits)
    with_bad_rows, cases = build_bad_rows(clean, as_of)
    return Generated(clean, with_bad_rows, cases)


def write_files(output: Path, generated: Generated) -> list[Path]:
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, data in ((CLEAN_FILE, generated.clean), (WITH_BAD_ROWS_FILE, generated.with_bad_rows)):
        path = output / name
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def iso_date(text: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise argparse.ArgumentTypeError(f"{text!r} is not a date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a real date") from None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=iso_date, required=True,
                        help="Reference date (YYYY-MM-DD); all dates are relative to it. Required, so files never depend on today.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"Random seed (default {DEFAULT_SEED}).")
    parser.add_argument("--visits", type=int, default=DEFAULT_VISITS,
                        help=f"Number of visits (default {DEFAULT_VISITS}, minimum {MIN_VISITS}).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Folder for the two JSON files (default: data/generated).")
    args = parser.parse_args(argv)
    try:
        generated = generate(args.seed, args.as_of, args.visits)
    except ValueError as error:
        parser.error(str(error))
    try:
        paths = write_files(args.output, generated)
    except OSError as error:
        parser.exit(1, f"Could not write the output files: {error}\n")
    for path in paths:
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
