"""Add a clinic manager who can sign in, so a new database has someone to run it.

Only a manager can add staff in the web app, so the first manager comes from here.
Run scripts/table_generate.py first. Signing in needs only the email in this release.
Managers added here get the IDs M001, M002, and so on, so a data file imported later can
use S001 and up without a clash.
"""

import argparse
from contextlib import closing
import os
from pathlib import Path
import re
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def create_manager(name: str, email: str, db_path: str | Path | None = None) -> str:
    """Insert the manager and return their staff ID; an email already in use is an error."""
    name, email = name.strip(), email.strip().lower()
    if not name:
        raise ValueError("name must not be empty")
    if not EMAIL.fullmatch(email):
        raise ValueError(f"{email!r} is not an email address")
    if db_path is None:
        db_path = os.environ.get("FOLLOWUP_DB_PATH") or PROJECT_ROOT / "data" / "followups.db"
    path = Path(db_path).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"{path} does not exist; run scripts/table_generate.py first")
    with closing(sqlite3.connect(path)) as connection, connection:
        if connection.execute("SELECT 1 FROM staff WHERE email = ?", [email]).fetchone():
            raise ValueError(f"a staff member already signs in with {email}")
        highest = connection.execute(
            "SELECT MAX(CAST(substr(staff_id, 2) AS INTEGER)) FROM staff WHERE staff_id GLOB 'M[0-9]*'"
        ).fetchone()[0]
        staff_id = f"M{(highest or 0) + 1:03d}"
        connection.execute(
            "INSERT INTO staff (staff_id, name, role, email) VALUES (?, ?, 'manager', ?)", [staff_id, name, email],
        )
    return staff_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="Manager's name, for example 'Clinic Manager'.")
    parser.add_argument("--email", required=True, help="Email the manager signs in with.")
    parser.add_argument("--db-path", type=Path, help="SQLite file (default: FOLLOWUP_DB_PATH or data/followups.db).")
    args = parser.parse_args(argv)
    try:
        staff_id = create_manager(args.name, args.email, args.db_path)
    except (ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Could not add the manager: {error}\n")
    print(f"Manager {staff_id} added; sign in with {args.email.strip().lower()}")


if __name__ == "__main__":
    main()
