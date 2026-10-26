"""Contracts for SQL queries, results, and the domain rule engine."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import ActionType, FollowUpFlag, FollowUpStatus

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
