"""Import a JSON file of patients, staff, episodes, visits, and follow-ups.

Every record is checked first. If any record is rejected, every reason is printed and
nothing is saved; otherwise the whole file is saved in one transaction.
"""

import argparse
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))  # run as "python scripts/import_data.py"

from app import service  # noqa: E402
from app.db import write_database  # noqa: E402
from app.ingestion.loader import ImportFileError, read_file  # noqa: E402
from app.repository import QueryError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True, help="Import file (JSON).")
    parser.add_argument("--db-path", type=Path, help="SQLite file (default: FOLLOWUP_DB_PATH or data/followups.db).")
    args = parser.parse_args(argv)
    if args.db_path:
        os.environ["FOLLOWUP_DB_PATH"] = str(args.db_path)
    try:
        data = read_file(args.file)
        with write_database() as connection:
            result = service.import_records(connection, data)
    except (ImportFileError, QueryError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    if not result.saved:
        print(f"Rejected {args.file}: nothing was saved. {len(result.rejections)} problem(s):", file=sys.stderr)
        for rejection in result.rejections:
            print(f"  {rejection.kind} {rejection.record_id}: {rejection.reason}", file=sys.stderr)
        return 1
    print(f"Imported {args.file}: " + ", ".join(f"{count} {table}" for table, count in result.counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
