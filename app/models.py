"""Contracts for SQL queries, UI searches, record changes, natural-language questions, and rules."""

from datetime import date
from typing import Annotated, ClassVar, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.constants import ActionType, EpisodeStatus, FollowUpFlag, FollowUpStatus

SQLValue = (
    str
    | Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]
    | Annotated[float, Field(allow_inf_nan=False)]
    | bool
    | None
)


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1, max_length=20_000)
    parameters: list[SQLValue] | dict[str, SQLValue] = Field(default_factory=list, max_length=1_000)
    max_rows: int = Field(default=100, ge=1, le=1_000)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[SQLValue]]
    row_count: int
    truncated: bool


class FollowUpRow(BaseModel):
    """Domain input for deterministic rules; independent of the SQL query API."""

    followup_id: str
    visit_id: str
    patient_id: str
    patient_name: str
    episode_id: str
    episode_description: str
    visit_date: date
    action_type: ActionType
    due_date: date
    assigned_staff_id: str | None
    assigned_staff_name: str | None
    status: FollowUpStatus
    completed_at: str | None
    flags: list[FollowUpFlag] = Field(default_factory=list)


class FollowUpItem(FollowUpRow):
    """One follow-up row in UI search results, with rule flags already calculated."""

    days_until_due: int
    assigned_staff_role: str | None
    visit_staff_id: str | None
    visit_staff_name: str | None
    visit_staff_role: str | None
    visit_notes: str | None
    episode_closed_at: date | None


# --- UI search filters --------------------------------------------------------
# Every filter is optional and filters combine with AND; list values match any item.
# Request values are always bound parameters; SQL text is fixed in app/search.py.

SearchText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
RecordId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
IdList = Annotated[list[RecordId], Field(max_length=100)]
Days = Annotated[int, Field(ge=0, le=3650)]
Count = Annotated[int, Field(ge=0, le=100_000)]

FollowUpPreset = Literal[
    "overdue", "overdue_30_plus", "due_today", "due_soon", "due_this_week", "due_next_30_days",
    "unassigned", "unassigned_overdue", "open_labs", "open_referrals", "open_rechecks",
    "completed_last_7_days", "completed_last_30_days", "open_episode_followups",
]
FollowUpSort = Literal[
    "due_date", "-due_date", "visit_date", "-visit_date", "patient_name", "-patient_name",
    "assigned_staff_name", "-assigned_staff_name", "action_type", "status",
    "completed_at", "-completed_at", "followup_id",
]
FollowUpGroup = Literal[
    "action_type", "status", "assigned_staff", "assigned_staff_role", "visit_staff",
    "patient", "episode", "due_date", "due_week", "due_month", "visit_month", "completed_month",
]
PatientSort = Literal[
    "name", "-name", "patient_id", "last_visit_date", "-last_visit_date", "next_due_date",
    "-open_followups", "-overdue_followups", "-visit_count",
]
StaffSort = Literal[
    "name", "-name", "role", "-open_followups", "-overdue_followups", "-visit_count", "next_due_date",
]
VisitSort = Literal[
    "visit_date", "-visit_date", "patient_name", "staff_name", "-followup_count", "-open_followups",
]
EpisodeSort = Literal[
    "opened_at", "-opened_at", "last_visit_date", "-last_visit_date", "patient_name",
    "-open_followups", "-visit_count", "-days_open",
]


class AsOf(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Rule flags and relative day filters are evaluated against this date.
    as_of_date: date = Field(default_factory=date.today)


class Paging(BaseModel):
    limit: int = Field(default=50, ge=1, le=1_000)
    offset: int = Field(default=0, ge=0, le=1_000_000)


class FollowUpFilters(AsOf):
    q: SearchText | None = None  # ID, patient, staff, episode, or visit notes
    preset: FollowUpPreset | None = None
    followup_id: IdList = []
    patient_id: IdList = []
    patient_name: SearchText | None = None
    visit_id: IdList = []
    episode_id: IdList = []
    episode_description: SearchText | None = None
    episode_status: EpisodeStatus | None = None
    action_type: list[ActionType] = []
    status: list[FollowUpStatus] = []
    flag: list[FollowUpFlag] = []
    staff_id: IdList = []  # assigned to the follow-up or conducted its visit
    staff_name: SearchText | None = None
    assigned_staff_id: IdList = []
    assigned_staff_name: SearchText | None = None
    assigned_staff_role: list[SearchText] = []
    unassigned: bool | None = None
    visit_staff_id: IdList = []
    visit_staff_name: SearchText | None = None
    visit_staff_role: list[SearchText] = []
    notes: SearchText | None = None
    due_from: date | None = None
    due_to: date | None = None
    due_within_days: Days | None = None  # as_of_date <= due_date <= as_of_date + N
    days_overdue_min: Days | None = None  # open and at least N days past due
    days_overdue_max: Days | None = None
    visit_from: date | None = None
    visit_to: date | None = None
    completed_from: date | None = None
    completed_to: date | None = None
    completed_within_days: Days | None = None


class FollowUpSearch(FollowUpFilters, Paging):
    sort: FollowUpSort = "due_date"


class FollowUpStatsQuery(FollowUpFilters):
    group_by: FollowUpGroup | None = None


class PatientSearch(AsOf, Paging):
    q: SearchText | None = None  # ID, name, phone, or email
    patient_id: IdList = []
    name: SearchText | None = None
    staff_id: IdList = []  # conducted a visit or is assigned a follow-up
    flag: list[FollowUpFlag] = []  # has at least one open follow-up with any flag
    open_action_type: list[ActionType] = []
    has_open_episode: bool | None = None
    open_followups_min: Count | None = None
    open_followups_max: Count | None = None
    overdue_followups_min: Count | None = None
    visit_count_min: Count | None = None
    visit_count_max: Count | None = None
    last_visit_from: date | None = None
    last_visit_to: date | None = None
    next_due_from: date | None = None
    next_due_to: date | None = None
    sort: PatientSort = "name"


class StaffSearch(AsOf, Paging):
    q: SearchText | None = None  # ID or name
    staff_id: IdList = []
    role: list[SearchText] = []
    flag: list[FollowUpFlag] = []  # is assigned an open follow-up with any flag
    open_followups_min: Count | None = None
    open_followups_max: Count | None = None
    overdue_followups_min: Count | None = None
    visit_count_min: Count | None = None
    sort: StaffSort = "name"


class VisitSearch(AsOf, Paging):
    q: SearchText | None = None  # ID, patient, staff, episode, or notes
    visit_id: IdList = []
    patient_id: IdList = []
    patient_name: SearchText | None = None
    episode_id: IdList = []
    episode_status: EpisodeStatus | None = None
    staff_id: IdList = []
    staff_name: SearchText | None = None
    staff_role: list[SearchText] = []
    notes: SearchText | None = None
    visit_from: date | None = None
    visit_to: date | None = None
    visit_within_days: Days | None = None  # as_of_date - N <= visit_date <= as_of_date
    flag: list[FollowUpFlag] = []
    followup_action_type: list[ActionType] = []
    followup_count_min: Count | None = None
    followup_count_max: Count | None = None
    open_followups_min: Count | None = None
    sort: VisitSort = "-visit_date"


class EpisodeSearch(AsOf, Paging):
    q: SearchText | None = None  # ID, description, or patient
    episode_id: IdList = []
    patient_id: IdList = []
    patient_name: SearchText | None = None
    description: SearchText | None = None
    status: EpisodeStatus | None = None
    staff_id: IdList = []
    flag: list[FollowUpFlag] = []
    opened_from: date | None = None
    opened_to: date | None = None
    closed_from: date | None = None
    closed_to: date | None = None
    days_open_min: Days | None = None
    days_open_max: Days | None = None
    visit_count_min: Count | None = None
    visit_count_max: Count | None = None
    open_followups_min: Count | None = None
    sort: EpisodeSort = "-opened_at"


# --- UI search results --------------------------------------------------------

Item = TypeVar("Item")


class Page(BaseModel, Generic[Item]):
    items: list[Item]
    total: int  # all matches, not only this page
    limit: int
    offset: int
    as_of_date: date


class FollowUpCounts(BaseModel):
    followup_count: int = 0
    open_followups: int = 0
    done_followups: int = 0
    overdue_followups: int = 0
    due_today_followups: int = 0
    due_soon_followups: int = 0
    unassigned_followups: int = 0
    next_due_date: date | None = None  # earliest open follow-up


class PatientSummary(FollowUpCounts):
    patient_id: str
    name: str
    phone: str | None
    email: str | None
    episode_count: int
    open_episode_count: int
    visit_count: int
    first_visit_date: date | None
    last_visit_date: date | None


class StaffSummary(FollowUpCounts):
    """Follow-up counts are for follow-ups assigned to this staff member."""

    staff_id: str
    name: str
    role: str
    visit_count: int
    patient_count: int
    last_visit_date: date | None


class VisitSummary(FollowUpCounts):
    visit_id: str
    visit_date: date
    notes: str | None
    patient_id: str
    patient_name: str
    episode_id: str
    episode_description: str
    episode_closed_at: date | None
    staff_id: str | None
    staff_name: str | None
    staff_role: str | None


class EpisodeSummary(FollowUpCounts):
    episode_id: str
    patient_id: str
    patient_name: str
    description: str
    opened_at: date
    closed_at: date | None
    status: EpisodeStatus
    days_open: int
    visit_count: int
    first_visit_date: date | None
    last_visit_date: date | None


class StatsGroup(FollowUpCounts):
    key: str | None
    label: str | None


class FollowUpStats(BaseModel):
    as_of_date: date
    group_by: FollowUpGroup | None
    totals: FollowUpCounts
    groups: list[StatsGroup]


class VisitHistory(VisitSummary):
    followups: list[FollowUpItem]


class EpisodeHistory(EpisodeSummary):
    visits: list[VisitHistory]


class FollowUpDetail(BaseModel):
    followup: FollowUpItem
    patient: PatientSummary
    episode_followups: list[FollowUpItem]  # other follow-ups for the same medical issue


class PatientDetail(BaseModel):
    patient: PatientSummary
    episodes: list[EpisodeHistory]


class StaffDetail(BaseModel):
    staff: StaffSummary
    open_followups: list[FollowUpItem]
    recent_visits: list[VisitSummary]


class EpisodeDetail(BaseModel):
    episode: EpisodeHistory


class VisitDetail(BaseModel):
    visit: VisitHistory


class Dashboard(BaseModel):
    as_of_date: date
    followups: FollowUpCounts
    completed_last_7_days: int
    patients: int
    patients_with_open_followups: int
    patients_with_overdue: int
    open_episodes: int
    visits_last_30_days: int
    staff_with_overdue: int


class StaffOption(BaseModel):
    staff_id: str
    name: str
    role: str


class DateRange(BaseModel):
    min: date | None
    max: date | None


class PresetOption(BaseModel):
    name: FollowUpPreset
    label: str
    filters: dict[str, object]


class SearchOptions(BaseModel):
    """Values for dropdowns, slider bounds, and sort menus."""

    as_of_date: date
    due_soon_days: int
    action_types: list[ActionType]
    followup_statuses: list[FollowUpStatus]
    followup_flags: list[FollowUpFlag]
    episode_statuses: list[EpisodeStatus]
    staff: list[StaffOption]
    staff_roles: list[str]
    date_ranges: dict[str, DateRange]
    presets: list[PresetOption]
    sorts: dict[str, list[str]]
    followup_groups: list[FollowUpGroup]
    max_limit: int


# --- Record changes -----------------------------------------------------------
# Create and update only; records are never deleted. SQL text is fixed in app/writes.py.
# Omit an ID on create to receive the next one (P004, S012, ...).

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Contact = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=5_000)]


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def changes(self) -> dict[str, object]:
        """Only fields the caller sent; an explicit null clears an optional value."""
        return {name: getattr(self, name) for name in self.model_fields_set}


class Update(Change):
    not_null: ClassVar[frozenset[str]] = frozenset()  # NOT NULL columns cannot be cleared

    @model_validator(mode="after")
    def has_changes(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        for name in self.model_fields_set & self.not_null:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class PatientCreate(Change):
    patient_id: RecordId | None = None
    name: Name
    phone: Contact | None = None
    email: Contact | None = None


class PatientUpdate(Update):
    not_null = frozenset({"name"})
    name: Name | None = None
    phone: Contact | None = None
    email: Contact | None = None


class StaffCreate(Change):
    staff_id: RecordId | None = None
    name: Name
    role: Name


class StaffUpdate(Update):
    not_null = frozenset({"name", "role"})
    name: Name | None = None
    role: Name | None = None


class EpisodeCreate(Change):
    episode_id: RecordId | None = None
    patient_id: RecordId
    description: Name
    opened_at: date
    closed_at: date | None = None


class EpisodeUpdate(Update):
    """Set closed_at to close an episode, or null to reopen it."""

    not_null = frozenset({"description", "opened_at"})
    description: Name | None = None
    opened_at: date | None = None
    closed_at: date | None = None


class VisitCreate(Change):
    visit_id: RecordId | None = None
    episode_id: RecordId  # the visit's patient is the episode's patient
    staff_id: RecordId | None = None
    visit_date: date
    notes: Notes | None = None


class VisitUpdate(Update):
    not_null = frozenset({"visit_date"})
    staff_id: RecordId | None = None
    visit_date: date | None = None
    notes: Notes | None = None


class FollowUpCreate(Change):
    followup_id: RecordId | None = None
    visit_id: RecordId
    action_type: ActionType
    due_date: date
    assigned_staff_id: RecordId | None = None


class FollowUpUpdate(Update):
    """status "done" records completed_at now; "open" clears it. Null unassigns staff."""

    not_null = frozenset({"action_type", "due_date", "status"})
    action_type: ActionType | None = None
    due_date: date | None = None
    assigned_staff_id: RecordId | None = None
    status: FollowUpStatus | None = None


# --- Natural-language questions -----------------------------------------------

PromptIntent = Literal["read", "modify", "unrelated"]


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1_000)
    max_rows: int = Field(default=100, ge=1, le=1_000)
    as_of_date: date = Field(default_factory=date.today)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class PromptDecision(BaseModel):
    """Decisions API verdict on the user's prompt text alone."""

    intent: PromptIntent
    confidence: float = Field(ge=0, le=1)
    modify_probability: float = Field(ge=0, le=1)


class GeneratedQuery(BaseModel):
    sql: str
    parameters: list[str | int | float | None]
    explanation: str


class AskResponse(BaseModel):
    question: str
    decision: PromptDecision
    sql: str
    parameters: list[SQLValue]
    explanation: str
    result: QueryResponse
