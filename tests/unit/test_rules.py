"""Follow-up rules: boundaries, multiple flags, closed follow-ups, and no-flag cases.

Every test passes the reference date in; nothing here depends on the real clock.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.ingestion.models import FollowUpRecord, validate_record
from app.ingestion.settings import Settings, load_settings
from app.rules import (
    DueSoonRule, FollowUpRule, OverdueRule, UnassignedRule, build_rules, calculate_flags,
    due_soon_end, run_rules,
)

AS_OF = date(2026, 10, 26)


def day(offset: int) -> date:
    return AS_OF + timedelta(days=offset)


def followup(
    due_offset: int | None = 30, *, status: str = "open", followup_id: str = "F001",
    action_type: str = "lab",
):
    """A follow-up scheduled `due_offset` days from AS_OF; negative is in the past, None is not scheduled."""
    return SimpleNamespace(
        followup_id=followup_id, status=status, due_date=None if due_offset is None else day(due_offset),
        assigned_staff_id="S001", action_type=action_type,
    )


def record(due_offset: int | None = 30, *, status: str = "open", followup_id: str = "F001"):
    """The same follow-up built through the Step 1 validator, as the loader will produce it."""
    raw = {
        "followup_id": followup_id, "visit_id": "V001", "action_type": "lab",
        "assigned_staff_id": "S001", "status": status,
    }
    if due_offset is not None:
        raw["due_date"] = day(due_offset).isoformat()
    if status in ("done", "closed"):
        raw["completed_at"] = "2026-10-20T12:00:00Z"
    if status == "closed":
        raw["notes"] = "Patient unreachable"
    result = validate_record("followup", raw)
    assert isinstance(result, FollowUpRecord)
    return result


# --- structure ----------------------------------------------------------------


def test_base_rule_cannot_be_used_directly():
    with pytest.raises(TypeError):
        FollowUpRule()


def test_each_rule_is_a_follow_up_rule_with_its_own_flag():
    rules = {OverdueRule(): "overdue", DueSoonRule(): "due_soon", UnassignedRule(): "unassigned"}

    for rule, flag in rules.items():
        assert isinstance(rule, FollowUpRule)
        assert rule.flag == flag


def test_default_rules_are_overdue_due_soon_unassigned_in_that_order():
    assert [rule.flag for rule in build_rules()] == ["overdue", "due_soon", "unassigned"]


# --- overdue ------------------------------------------------------------------


@pytest.mark.parametrize(("due_offset", "expected"), [(-30, True), (-1, True), (0, False), (1, False), (30, False)])
def test_overdue_boundary(due_offset, expected):
    assert OverdueRule().applies(followup(due_offset), AS_OF) is expected


def test_due_today_is_due_soon_and_not_overdue():
    assert calculate_flags(followup(0), AS_OF) == ["due_soon"]


def test_due_yesterday_becomes_overdue_and_is_no_longer_due_soon():
    assert calculate_flags(followup(-1), AS_OF) == ["overdue"]


# --- due soon -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("due_offset", "expected"), [(-1, False), (0, True), (1, True), (7, True), (8, False), (30, False)]
)
def test_due_soon_default_window_boundaries(due_offset, expected):
    assert DueSoonRule().applies(followup(due_offset), AS_OF) is expected


@pytest.mark.parametrize(
    ("days", "due_offset", "expected"),
    [(0, 0, True), (0, 1, False), (3, 3, True), (3, 4, False), (14, 14, True), (14, 15, False), (365, 365, True)],
)
def test_due_soon_window_is_configurable(days, due_offset, expected):
    assert DueSoonRule(days).applies(followup(due_offset), AS_OF) is expected


def test_negative_due_soon_window_is_rejected():
    with pytest.raises(ValueError, match="due_soon_days"):
        DueSoonRule(-1)


@pytest.mark.parametrize("days", [1.5, "7", None, True])
def test_non_integer_due_soon_window_is_rejected(days):
    with pytest.raises(TypeError, match="due_soon_days"):
        DueSoonRule(days)


def test_due_soon_window_stops_at_the_last_supported_date():
    assert due_soon_end(date.max) == date.max
    assert due_soon_end(AS_OF) == day(7)
    assert due_soon_end(AS_OF, 14) == day(14)
    assert calculate_flags(SimpleNamespace(status="open", due_date=date.max, assigned_staff_id="S001"), date.max) == [
        "due_soon"
    ]


# --- a different window for each action type ---------------------------------

WINDOWS = {"lab": 7, "referral": 14, "recheck": 14}


@pytest.mark.parametrize(
    ("action_type", "due_offset", "expected"),
    [
        ("lab", 7, True), ("lab", 8, False), ("lab", 14, False),
        ("referral", 7, True), ("referral", 14, True), ("referral", 15, False),
        ("recheck", 8, True), ("recheck", 14, True), ("recheck", 15, False),
        ("lab", 0, True), ("referral", 0, True), ("recheck", -1, False),
    ],
)
def test_due_soon_window_depends_on_the_action_type(action_type, due_offset, expected):
    item = followup(due_offset, action_type=action_type)

    assert DueSoonRule(WINDOWS).applies(item, AS_OF) is expected


def test_overdue_and_unassigned_ignore_the_action_type_windows():
    rules = build_rules(WINDOWS)

    assert calculate_flags(followup(-1, action_type="referral"), AS_OF, rules) == ["overdue"]
    assert calculate_flags(followup(None, action_type="referral"), AS_OF, rules) == ["unassigned"]
    assert calculate_flags(followup(10, action_type="lab"), AS_OF, rules) == []
    assert calculate_flags(followup(10, action_type="recheck"), AS_OF, rules) == ["due_soon"]


def test_closed_follow_ups_get_no_flags_with_per_action_windows():
    assert calculate_flags(followup(3, status="closed", action_type="referral"), AS_OF, build_rules(WINDOWS)) == []


def test_action_type_without_a_window_is_a_clear_error():
    with pytest.raises(ValueError, match="no due-soon window for action type 'surgery'"):
        DueSoonRule(WINDOWS).applies(followup(3, action_type="surgery"), AS_OF)


@pytest.mark.parametrize("windows", [{"lab": -1}, {"lab": 1.5}, {"lab": "7"}, {"lab": True}, {"lab": None}])
def test_invalid_per_action_windows_are_rejected(windows):
    with pytest.raises((TypeError, ValueError), match="due_soon_days"):
        DueSoonRule(windows)


def test_empty_per_action_windows_are_rejected():
    with pytest.raises(ValueError, match="due_soon_days"):
        DueSoonRule({})


def test_per_action_windows_do_not_change_when_the_input_mapping_does():
    windows = {"lab": 7}
    rule = DueSoonRule(windows)
    windows["lab"] = 0

    assert rule.applies(followup(5, action_type="lab"), AS_OF) is True


def test_run_rules_takes_each_action_window_from_settings():
    settings = Settings(allowed_action_types=["lab", "referral"], due_soon_days_by_action={"lab": 2, "referral": 20})
    items = [
        followup(10, followup_id="F001", action_type="lab"),
        followup(10, followup_id="F002", action_type="referral"),
    ]

    assert run_rules(items, AS_OF, settings) == {"F001": [], "F002": ["due_soon"]}


# --- unassigned ---------------------------------------------------------------


def test_unassigned_means_no_scheduled_date():
    assert UnassignedRule().applies(followup(None), AS_OF) is True
    assert UnassignedRule().applies(followup(30), AS_OF) is False


def test_follow_up_without_a_date_is_never_overdue_or_due_soon():
    assert OverdueRule().applies(followup(None), AS_OF) is False
    assert DueSoonRule().applies(followup(None), AS_OF) is False
    assert DueSoonRule({"lab": 3}).applies(followup(None), AS_OF) is False


# --- multiple flags and no flags ---------------------------------------------


def test_built_in_flags_never_combine():
    for offset in [None, *range(-40, 41)]:
        assert len(calculate_flags(followup(offset), AS_OF)) <= 1, offset
    assert calculate_flags(followup(-5), AS_OF) == ["overdue"]
    assert calculate_flags(followup(2), AS_OF) == ["due_soon"]


def test_overdue_and_due_soon_never_apply_together():
    for offset in range(-40, 41):
        flags = calculate_flags(followup(offset), AS_OF)
        assert not {"overdue", "due_soon"} <= set(flags), offset


def test_day_with_no_flags_returns_an_empty_list():
    assert calculate_flags(followup(30), AS_OF) == []


class AlwaysRule(FollowUpRule):
    flag = "always"
    needs_date = False

    def matches(self, followup, as_of_date):
        return True


def test_flags_follow_rule_order():
    assert calculate_flags(followup(0), AS_OF, (*build_rules(), AlwaysRule())) == ["due_soon", "always"]
    assert calculate_flags(followup(0), AS_OF, (AlwaysRule(), *build_rules())) == ["always", "due_soon"]


# --- closed and legacy statuses ----------------------------------------------


@pytest.mark.parametrize("due_offset", [-30, 0, 3, 60, None])
def test_closed_follow_up_never_gets_flags(due_offset):
    assert calculate_flags(followup(due_offset, status="closed"), AS_OF) == []


def test_legacy_done_status_gets_no_flags_either():
    assert calculate_flags(followup(-30, status="done"), AS_OF) == []


# --- the reference date is injected ------------------------------------------


def test_same_follow_up_gets_different_flags_on_different_reference_dates():
    item = followup(0)

    assert calculate_flags(item, day(-3)) == ["due_soon"]
    assert calculate_flags(item, day(-8)) == []
    assert calculate_flags(item, day(0)) == ["due_soon"]
    assert calculate_flags(item, day(1)) == ["overdue"]


def test_datetime_reference_date_is_rejected():
    with pytest.raises(TypeError, match="as_of_date"):
        calculate_flags(followup(), datetime(2026, 10, 26, 12, 0))


@pytest.mark.parametrize("value", [None, "2026-10-26", 20261026])
def test_non_date_reference_date_is_rejected(value):
    with pytest.raises(TypeError, match="as_of_date"):
        calculate_flags(followup(), value)


def test_rules_work_on_validated_ingestion_records():
    assert calculate_flags(record(-2), AS_OF) == ["overdue"]
    assert calculate_flags(record(None), AS_OF) == ["unassigned"]
    assert calculate_flags(record(0), AS_OF) == ["due_soon"]
    assert calculate_flags(record(0, status="closed"), AS_OF) == []


# --- adding a rule ------------------------------------------------------------


def test_new_rule_is_one_subclass_and_does_not_change_existing_rules():
    class FarFutureRule(FollowUpRule):
        flag = "far_future"

        def matches(self, followup, as_of_date):
            return followup.due_date > as_of_date + timedelta(days=90)

    rules = (*build_rules(), FarFutureRule())

    assert calculate_flags(followup(120), AS_OF, rules) == ["far_future"]
    assert calculate_flags(followup(120), AS_OF) == []
    assert calculate_flags(followup(-5), AS_OF, rules) == ["overdue"]
    # A new date rule never sees a follow-up without a scheduled date.
    assert calculate_flags(followup(None), AS_OF, rules) == ["unassigned"]


# --- running every rule over many follow-ups ----------------------------------


def test_run_rules_collects_flags_for_every_follow_up():
    items = [
        followup(-3, followup_id="F001"),
        followup(2, followup_id="F002"),
        followup(40, followup_id="F003"),
        followup(-9, status="closed", followup_id="F004"),
        followup(None, followup_id="F005"),
    ]

    assert run_rules(items, AS_OF) == {
        "F001": ["overdue"],
        "F002": ["due_soon"],
        "F003": [],
        "F004": [],
        "F005": ["unassigned"],
    }


def test_run_rules_with_no_follow_ups_returns_nothing():
    assert run_rules([], AS_OF) == {}
    assert run_rules(iter(()), AS_OF) == {}


def test_run_rules_accepts_any_iterable():
    assert run_rules((item for item in [followup(0, followup_id="F009")]), AS_OF) == {"F009": ["due_soon"]}


def test_run_rules_takes_the_due_soon_window_from_settings():
    items = [followup(10, followup_id="F001")]
    wide = Settings(allowed_action_types=["lab"], due_soon_days_by_action={"lab": 14})
    narrow = Settings(allowed_action_types=["lab"], due_soon_days_by_action={"lab": 3})

    assert run_rules(items, AS_OF, wide) == {"F001": ["due_soon"]}
    assert run_rules(items, AS_OF, narrow) == {"F001": []}
    assert run_rules(items, AS_OF) == {"F001": []}


def test_run_rules_with_the_shipped_settings_file_uses_three_and_fourteen_days():
    settings = load_settings()
    items = [
        followup(3, followup_id="L3", action_type="lab"),
        followup(4, followup_id="L4", action_type="lab"),
        followup(14, followup_id="R14", action_type="referral"),
        followup(15, followup_id="R15", action_type="referral"),
        followup(14, followup_id="C14", action_type="recheck"),
        followup(15, followup_id="C15", action_type="recheck"),
    ]

    assert run_rules(items, AS_OF, settings) == {
        "L3": ["due_soon"], "L4": [], "R14": ["due_soon"], "R15": [], "C14": ["due_soon"], "C15": [],
    }


def test_run_rules_does_not_change_the_follow_ups():
    items = [record(-3, followup_id="F001"), record(2, followup_id="F002")]
    before = [item.model_copy(deep=True) for item in items]

    run_rules(items, AS_OF)

    assert items == before


def test_run_rules_refuses_duplicate_follow_up_ids():
    with pytest.raises(ValueError, match="F001"):
        run_rules([followup(followup_id="F001"), followup(followup_id="F001")], AS_OF)


def test_running_twice_gives_the_same_answer():
    items = [followup(-3, followup_id="F001"), followup(2, followup_id="F002")]

    assert run_rules(items, AS_OF) == run_rules(items, AS_OF)
