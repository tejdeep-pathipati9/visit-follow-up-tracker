"""Delete records older than the clinic's retention period (10 years).

Visits from before the cutoff go, with their follow-ups and change history, and so do the
episodes and patients that are left with no visits. Staff are kept. Everything happens in
one transaction; --dry-run shows the counts and changes nothing.
"""

import argparse
from datetime import date
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))  # run as "python scripts/delete_old_records.py"

from app import writes  # noqa: E402
from app.constants import RETENTION_YEARS  # noqa: E402
from app.db import write_database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), help="Today's date (default: today).")
    parser.add_argument("--dry-run", action="store_true", help="Count what would be deleted; delete nothing.")
    parser.add_argument("--db-path", type=Path, help="SQLite file (default: FOLLOWUP_DB_PATH or data/followups.db).")
    args = parser.parse_args(argv)
    if args.db_path:
        os.environ["FOLLOWUP_DB_PATH"] = str(args.db_path)
    cutoff = writes.retention_cutoff(args.as_of, RETENTION_YEARS)
    with write_database() as connection:
        counts = writes.delete_older_than(connection, cutoff)
        if not args.dry_run:
            connection.commit()  # otherwise write_database rolls everything back
    summary = ", ".join(f"{count} {table}" for table, count in counts.items())
    print(f"{'Would delete' if args.dry_run else 'Deleted'} records from before {cutoff}: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
