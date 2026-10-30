"""Typed input records and validation that turns bad records into readable rejections."""

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Annotated, Any

from pydantic import (
    BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, ValidationError,
    ValidationInfo, field_validator, model_validator,
)

from app.constants import ALLOWED_ACTION_TYPES, ActionType, FollowUpStatus
from app.ingestion.settings import Settings

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_iso_date(value: Any) -> Any:
    """Accept date objects and YYYY-MM-DD strings only; numbers and other formats are rejected."""
    if isinstance(value, datetime):
        raise ValueError("must be a date in YYYY-MM-DD format")
    if isinstance(value, date):
        return value
    if isinstance(value, str) and ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("must be a valid date in YYYY-MM-DD format")


IsoDate = Annotated[date, BeforeValidator(parse_iso_date)]
RecordId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50, strict=True)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500, strict=True)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatientRecord(Record):
    patient_id: RecordId
    name: Text
    phone: Text | None = None
    email: Text | None = None


class StaffRecord(Record):
    staff_id: RecordId
    name: Text
    role: Text


class EpisodeRecord(Record):
    episode_id: RecordId
    patient_id: RecordId
    description: Text
    opened_at: IsoDate
    closed_at: IsoDate | None = None

    @model_validator(mode="after")
    def closed_after_opened(self) -> "EpisodeRecord":
        if self.closed_at is not None and self.closed_at < self.opened_at:
            raise ValueError("closed_at must not be before opened_at")
        return self


class VisitRecord(Record):
    visit_id: RecordId
    patient_id: RecordId
    episode_id: RecordId
    staff_id: RecordId | None = None
    visit_date: IsoDate
    notes: str | None = None


class FollowUpRecord(Record):
    followup_id: RecordId
    visit_id: RecordId
    action_type: ActionType
    due_date: IsoDate
    assigned_staff_id: RecordId | None = None
    status: FollowUpStatus = "open"
    completed_at: Text | None = None

    @field_validator("action_type", mode="before")
    @classmethod
    def allowed_action_type(cls, value: Any, info: ValidationInfo) -> Any:
        # The settings file may narrow the supported action types; it is passed as context.
        allowed = (info.context or {}).get("allowed_action_types", ALLOWED_ACTION_TYPES)
        if value not in allowed:
            raise ValueError(f"unsupported action type {value!r}; allowed types: {', '.join(allowed)}")
        return value

    @field_validator("completed_at")
    @classmethod
    def completed_at_is_timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("must be an ISO date or timestamp") from None
        return value

    @model_validator(mode="after")
    def open_follow_up_not_completed(self) -> "FollowUpRecord":
        if self.status == "open" and self.completed_at is not None:
            raise ValueError("completed_at must be empty while status is open")
        return self


# kind: (record model, name of the identifier field)
RECORD_KINDS: dict[str, tuple[type[Record], str]] = {
    "patient": (PatientRecord, "patient_id"),
    "staff": (StaffRecord, "staff_id"),
    "episode": (EpisodeRecord, "episode_id"),
    "visit": (VisitRecord, "visit_id"),
    "followup": (FollowUpRecord, "followup_id"),
}


@dataclass(frozen=True)
class RecordRejection:
    kind: str
    record_id: str
    reason: str


def describe(error: ValidationError) -> str:
    problems = []
    for problem in error.errors():
        field = ".".join(str(part) for part in problem["loc"])
        message = problem["msg"].removeprefix("Value error, ")
        problems.append(f"{field}: {message}" if field else message)
    return "; ".join(problems)


def validate_record(kind: str, raw: Any, settings: Settings | None = None) -> Record | RecordRejection:
    """Return the typed record, or a RecordRejection saying why it was refused."""
    if kind not in RECORD_KINDS:
        raise ValueError(f"Unknown record kind: {kind!r}")
    model, id_field = RECORD_KINDS[kind]
    if not isinstance(raw, dict):
        return RecordRejection(kind, "unknown", "record must be a JSON object")

    record_id = raw.get(id_field)
    if not isinstance(record_id, str) or not record_id.strip():
        record_id = "unknown"
    context = {"allowed_action_types": settings.allowed_action_types} if settings else None
    try:
        return model.model_validate(raw, context=context)
    except ValidationError as error:
        return RecordRejection(kind, record_id.strip(), describe(error))
