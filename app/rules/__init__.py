"""Deterministic flags for open follow-ups; rules never modify records."""

from abc import ABC, abstractmethod
from datetime import date

from app.constants import DUE_SOON_DAYS, FollowUpFlag
from app.models import FollowUpRow


def due_soon_end(as_of_date: date) -> date:
    return date.fromordinal(min(as_of_date.toordinal() + DUE_SOON_DAYS, date.max.toordinal()))


class FollowUpRule(ABC):
    flag: FollowUpFlag

    def applies(self, followup: FollowUpRow, as_of_date: date) -> bool:
        return followup.status == "open" and self.matches(followup, as_of_date)

    @abstractmethod
    def matches(self, followup: FollowUpRow, as_of_date: date) -> bool:
        """Evaluate a single rule for an open follow-up."""


class OverdueRule(FollowUpRule):
    flag: FollowUpFlag = "overdue"

    def matches(self, followup: FollowUpRow, as_of_date: date) -> bool:
        return followup.due_date < as_of_date


class DueSoonRule(FollowUpRule):
    flag: FollowUpFlag = "due_soon"

    def matches(self, followup: FollowUpRow, as_of_date: date) -> bool:
        return as_of_date <= followup.due_date <= due_soon_end(as_of_date)


class UnassignedRule(FollowUpRule):
    flag: FollowUpFlag = "unassigned"

    def matches(self, followup: FollowUpRow, as_of_date: date) -> bool:
        return followup.assigned_staff_id is None


RULES = (OverdueRule(), DueSoonRule(), UnassignedRule())


def calculate_flags(followup: FollowUpRow, as_of_date: date) -> list[FollowUpFlag]:
    return [rule.flag for rule in RULES if rule.applies(followup, as_of_date)]
