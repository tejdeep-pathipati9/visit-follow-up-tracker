"""Read an import file and check every record before anything is saved.

The clinic asked that a file with any bad record be refused as a whole, so this module
collects every problem: invalid records, references to records that do not exist,
duplicate IDs, and IDs or staff emails already in the database. The caller saves the
batch only when there are no rejections.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from app.ingestion.models import (
    EpisodeRecord, FollowUpRecord, PatientRecord, RecordRejection, StaffRecord, VisitRecord, validate_record,
)
from app.ingestion.settings import Settings

# File section -> record kind, parents before children.
SECTIONS = {"patients": "patient", "staff": "staff", "episodes": "episode", "visits": "visit"}
# Record kind -> ImportBatch list.
BATCH_LISTS = {"patient": "patients", "staff": "staff", "episode": "episodes", "visit": "visits", "followup": "followups"}


class ImportFileError(ValueError):
    """The file is missing, unreadable, not JSON, or not shaped like an import file."""


@dataclass(frozen=True)
class ExistingRecords:
    """What the database already holds, for references and duplicate checks."""

    patients: frozenset[str] = frozenset()
    staff: frozenset[str] = frozenset()
    staff_emails: frozenset[str] = frozenset()
    episodes: dict[str, str] = field(default_factory=dict)  # episode -> patient
    visits: frozenset[str] = frozenset()
    followups: frozenset[str] = frozenset()


@dataclass
class ImportBatch:
    patients: list[PatientRecord] = field(default_factory=list)
    staff: list[StaffRecord] = field(default_factory=list)
    episodes: list[EpisodeRecord] = field(default_factory=list)
    visits: list[VisitRecord] = field(default_factory=list)
    followups: list[FollowUpRecord] = field(default_factory=list)
    rejections: list[RecordRejection] = field(default_factory=list)

    def reject(self, kind: str, record_id: str, reason: str) -> None:
        self.rejections.append(RecordRejection(kind, record_id, reason))


def read_file(path: str | Path) -> Any:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ImportFileError(f"File not found: {path}") from None
    except (OSError, UnicodeDecodeError) as error:
        raise ImportFileError(f"File could not be read: {path} ({error})") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ImportFileError(f"Not valid JSON: {path} ({error.msg} at line {error.lineno}, column {error.colno})") from error


def load(data: Any, existing: ExistingRecords, settings: Settings | None = None) -> ImportBatch:
    """Validate every record in the file; the batch lists every rejection with its reason."""
    if not isinstance(data, dict):
        raise ImportFileError("An import file must contain one JSON object.")
    unknown = sorted(set(data) - set(SECTIONS))
    if unknown:
        raise ImportFileError(f"Unknown sections: {', '.join(unknown)}; expected {', '.join(SECTIONS)}.")
    for section, records in data.items():
        if not isinstance(records, list):
            raise ImportFileError(f"{section} must be a list.")

    batch = ImportBatch()
    for section, kind in SECTIONS.items():
        for raw in data.get(section, []):
            nested = []
            if kind == "visit" and isinstance(raw, dict):
                raw = dict(raw)
                nested = raw.pop("followups", [])
            add(batch, kind, validate_record(kind, raw, settings))
            if not isinstance(nested, list):
                batch.reject("visit", str(raw.get("visit_id", "unknown")), "followups must be a list")
                continue
            for followup in nested:
                # A follow-up belongs to the visit it is listed under.
                if isinstance(followup, dict) and followup.get("visit_id", raw.get("visit_id")) != raw.get("visit_id"):
                    batch.reject("followup", str(followup.get("followup_id", "unknown")),
                                 f"visit_id does not match visit {raw.get('visit_id')}, which it is listed under")
                    continue
                if isinstance(followup, dict):
                    followup = {**followup, "visit_id": raw.get("visit_id")}
                add(batch, "followup", validate_record("followup", followup, settings))
    check_references(batch, existing)
    return batch


def add(batch: ImportBatch, kind: str, result) -> None:
    if isinstance(result, RecordRejection):
        batch.rejections.append(result)
    else:
        getattr(batch, BATCH_LISTS[kind]).append(result)


def check_references(batch: ImportBatch, existing: ExistingRecords) -> None:
    """Rejections that need the whole file and the database: duplicates and references."""
    patients = unique(batch, "patient", [p.patient_id for p in batch.patients], existing.patients)
    staff = unique(batch, "staff", [s.staff_id for s in batch.staff], existing.staff)
    unique(batch, "episode", [e.episode_id for e in batch.episodes], frozenset(existing.episodes))
    episode_patients = {**existing.episodes, **{e.episode_id: e.patient_id for e in batch.episodes}}
    unique(batch, "visit", [v.visit_id for v in batch.visits], existing.visits)
    unique(batch, "followup", [f.followup_id for f in batch.followups], existing.followups)

    emails = set(existing.staff_emails)
    for member in batch.staff:
        if member.email is None or member.staff_id in existing.staff:
            continue  # a saved staff member's ID is already rejected
        if member.email in emails:
            batch.reject("staff", member.staff_id, f"email {member.email} is already used by another staff member")
        emails.add(member.email)

    known_patients = patients | existing.patients
    known_staff = staff | existing.staff
    for episode in batch.episodes:
        if episode.patient_id not in known_patients:
            batch.reject("episode", episode.episode_id, f"patient {episode.patient_id} does not exist")
    for visit in batch.visits:
        if visit.patient_id not in known_patients:
            batch.reject("visit", visit.visit_id, f"patient {visit.patient_id} does not exist")
        if visit.episode_id not in episode_patients:
            batch.reject("visit", visit.visit_id, f"episode {visit.episode_id} does not exist")
        elif episode_patients[visit.episode_id] != visit.patient_id:
            batch.reject("visit", visit.visit_id, f"episode {visit.episode_id} belongs to another patient")
        if visit.staff_id not in known_staff:
            batch.reject("visit", visit.visit_id, f"staff member {visit.staff_id} does not exist")
    for followup in batch.followups:
        if followup.assigned_staff_id not in known_staff:
            batch.reject("followup", followup.followup_id, f"staff member {followup.assigned_staff_id} does not exist")


def unique(batch: ImportBatch, kind: str, ids: list[str], existing: frozenset[str]) -> set[str]:
    """IDs that appear once in the file and are not in the database; the rest are rejected."""
    seen: set[str] = set()
    for record_id in ids:
        if record_id in seen:
            batch.reject(kind, record_id, "the ID appears more than once in the file")
        elif record_id in existing:
            batch.reject(kind, record_id, "a record with this ID is already saved")
        seen.add(record_id)
    return seen
