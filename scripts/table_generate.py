"""Create the initial SQLite tables from app/schema.sql without deleting data."""

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "app" / "schema.sql"


def table_generate(db_path: str | Path | None = None) -> Path:
    """Initialize tables atomically and return the database's absolute path.

    Path priority: explicit argument, FOLLOWUP_DB_PATH, project data directory.
    This creates missing tables; it does not migrate existing table definitions.
    """
    if db_path is None:
        db_path = os.environ.get("FOLLOWUP_DB_PATH") or (
            PROJECT_ROOT / "data" / "followups.db"
        )
    database_path = Path(db_path).expanduser().resolve()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(database_path)) as connection:
        # Foreign keys must be enabled before starting the schema transaction.
        connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.executescript("BEGIN;\n" + schema + "\nCOMMIT;")

    return database_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        help="SQLite file (default: FOLLOWUP_DB_PATH or data/followups.db).",
    )
    args = parser.parse_args()
    try:
        database_path = table_generate(args.db_path)
    except (OSError, sqlite3.Error) as error:
        parser.exit(1, f"Database initialization failed: {error}\n")
    print(f"Database tables ready: {database_path}")


if __name__ == "__main__":
    main()
