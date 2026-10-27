"""Shared domain defaults; keep action types aligned with schema.sql."""

from typing import Literal, get_args

ActionType = Literal["lab", "referral", "recheck"]
FollowUpStatus = Literal["open", "done"]
FollowUpFlag = Literal["overdue", "due_soon", "unassigned"]
EpisodeStatus = Literal["open", "closed"]

ALLOWED_ACTION_TYPES = get_args(ActionType)
FOLLOWUP_STATUSES = get_args(FollowUpStatus)
FOLLOWUP_FLAGS = get_args(FollowUpFlag)
EPISODE_STATUSES = get_args(EpisodeStatus)
DUE_SOON_DAYS = 7
