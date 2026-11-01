"""Deterministic flags for open follow-ups; rules never modify records.

Every rule gets the reference date from its caller and never reads the clock, so the
same input and date always give the same flags. Rules read only `status`, `due_date`
and `assigned_staff_id`, so they work on ingestion records and on database rows alike.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Protocol

from app.constants import DUE_SOON_DAYS, FollowUpFlag
from app.ingestion.settings import Settings


class FollowUpLike(Protocol):
    status: str
    action_type: str  # read only when the due-soon window depends on the action type
    due_date: date
    assigned_staff_id: str | None


def check_date(as_of_date: object) -> date:
    # A datetime is a date subclass but cannot be compared with a plain date.
    if not isinstance(as_of_date, date) or isinstance(as_of_date, datetime):
        raise TypeError(f"as_of_date must be a date, not {type(as_of_date).__name__}")
    return as_of_date


def due_soon_end(as_of_date: date, days: int = DUE_SOON_DAYS) -> date:
    return date.fromordinal(min(as_of_date.toordinal() + days, date.max.toordinal()))


class FollowUpRule(ABC):
    flag: FollowUpFlag

    def applies(self, followup: FollowUpLike, as_of_date: date) -> bool:
        """Only open follow-ups are flagged; closed ones are finished and never flagged."""
        return followup.status == "open" and self.matches(followup, check_date(as_of_date))

    @abstractmethod
    def matches(self, followup: FollowUpLike, as_of_date: date) -> bool:
        """Evaluate this rule for an open follow-up."""


class OverdueRule(FollowUpRule):
    flag: FollowUpFlag = "overdue"

    def matches(self, followup: FollowUpLike, as_of_date: date) -> bool:
        # Due today is still due soon; it becomes overdue the next day.
        return followup.due_date < as_of_date


def check_days(days: object, name: str = "due_soon_days") -> int:
    if isinstance(days, bool) or not isinstance(days, int):
        raise TypeError(f"{name} must be an integer, not {days!r}")
    if days < 0:
        raise ValueError(f"{name} must not be negative, got {days}")
    return days


class DueSoonRule(FollowUpRule):
    """One window for every follow-up, or a mapping of action type to window."""

    flag: FollowUpFlag = "due_soon"

    def __init__(self, due_soon_days: int | Mapping[str, int] = DUE_SOON_DAYS):
        if isinstance(due_soon_days, Mapping):
            if not due_soon_days:
                raise ValueError("due_soon_days must not be empty")
            self.windows: dict[str, int] | None = {
                action_type: check_days(days, f"due_soon_days for {action_type}")
                for action_type, days in due_soon_days.items()
            }
            self.due_soon_days = None
        else:
            self.windows = None
            self.due_soon_days = check_days(due_soon_days)

    def window_for(self, followup: FollowUpLike) -> int:
        if self.windows is None:
            return self.due_soon_days
        try:
            return self.windows[followup.action_type]
        except KeyError:
            raise ValueError(f"no due-soon window for action type {followup.action_type!r}") from None

    def matches(self, followup: FollowUpLike, as_of_date: date) -> bool:
        return as_of_date <= followup.due_date <= due_soon_end(as_of_date, self.window_for(followup))


class UnassignedRule(FollowUpRule):
    flag: FollowUpFlag = "unassigned"

    def matches(self, followup: FollowUpLike, as_of_date: date) -> bool:
        return followup.assigned_staff_id is None


def build_rules(due_soon_days: int | Mapping[str, int] = DUE_SOON_DAYS) -> tuple[FollowUpRule, ...]:
    """Every rule in report order. A new rule is one subclass plus one entry here."""
    return (OverdueRule(), DueSoonRule(due_soon_days), UnassignedRule())


RULES = build_rules()


def calculate_flags(
    followup: FollowUpLike, as_of_date: date, rules: Sequence[FollowUpRule] = RULES
) -> list[FollowUpFlag]:
    return [rule.flag for rule in rules if rule.applies(followup, as_of_date)]


def run_rules(
    followups: Iterable[FollowUpLike], as_of_date: date, settings: Settings | None = None
) -> dict[str, list[FollowUpFlag]]:
    """Flags for every follow-up, keyed by follow-up ID; an empty list means no flags."""
    check_date(as_of_date)
    rules = build_rules(settings.due_soon_days_by_action) if settings else RULES
    flags: dict[str, list[FollowUpFlag]] = {}
    for followup in followups:
        if followup.followup_id in flags:
            raise ValueError(f"Duplicate follow-up ID: {followup.followup_id}")
        flags[followup.followup_id] = calculate_flags(followup, as_of_date, rules)
    return flags
