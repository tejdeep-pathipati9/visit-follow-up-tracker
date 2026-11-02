"""Sign-in by staff email and the access rules that follow from it.

Release 1.x signs staff in with their email alone; passwords come in a later release.
The clinic asked that staff see only the follow-ups assigned to them, so every search
is scoped to the signed-in staff member unless their role is "manager".

Sessions live in this process's memory: restarting the server signs everyone out.
"""

from contextlib import closing
from dataclasses import dataclass
import secrets
from typing import Annotated

from fastapi import Depends, Request

from app.db import connect
from app.repository import QueryError

SESSION_COOKIE = "followup_session"
MANAGER_ROLE = "manager"

# Session token -> staff ID.
SESSIONS: dict[str, str] = {}


@dataclass(frozen=True)
class Viewer:
    staff_id: str
    name: str
    role: str
    email: str

    @property
    def is_manager(self) -> bool:
        return self.role == MANAGER_ROLE

    @property
    def scope(self) -> str | None:
        """The staff ID every search is limited to, or None for a manager who sees everything."""
        return None if self.is_manager else self.staff_id


def find_staff(column: str, value: str) -> Viewer | None:
    """Look up one staff member on a short read-only connection of its own, so the lookup
    never holds a lock while the request's own transaction writes."""
    assert column in ("staff_id", "email")
    with closing(connect("ro")) as connection:
        row = connection.execute(
            f"SELECT staff_id, name, role, email FROM staff WHERE {column} = ? COLLATE NOCASE", [value],
        ).fetchone()
    return None if row is None or row["email"] is None else Viewer(**dict(row))


def sign_in(email: str) -> tuple[str, Viewer]:
    viewer = find_staff("email", email.strip())
    if viewer is None:
        raise QueryError("unknown_email", "No staff member signs in with that email.", 401)
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = viewer.staff_id
    return token, viewer


def sign_out(token: str | None) -> None:
    SESSIONS.pop(token or "", None)


def optional_viewer(request: Request) -> Viewer | None:
    staff_id = SESSIONS.get(request.cookies.get(SESSION_COOKIE, ""))
    return None if staff_id is None else find_staff("staff_id", staff_id)


def current_viewer(viewer: Annotated[Viewer | None, Depends(optional_viewer)]) -> Viewer:
    if viewer is None:
        raise QueryError("not_signed_in", "Sign in with your staff email first.", 401)
    return viewer


def manager_only(viewer: Annotated[Viewer, Depends(current_viewer)]) -> Viewer:
    if not viewer.is_manager:
        raise QueryError("managers_only", "Only a clinic manager can do this.", 403)
    return viewer


CurrentViewer = Annotated[Viewer, Depends(current_viewer)]
Manager = Annotated[Viewer, Depends(manager_only)]
