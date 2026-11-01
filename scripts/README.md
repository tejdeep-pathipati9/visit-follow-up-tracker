# Operational scripts

Available:

- `python scripts/table_generate.py`: create the five core tables and four
  query indexes from `app/schema.sql`. Existing records are preserved on reruns.
  Use `--db-path /path/to/followups.db` or export `FOLLOWUP_DB_PATH` to choose a
  database; otherwise it uses the project's `data/followups.db`. This script uses
  only the Python standard library and does not load `.env` automatically.
- `python scripts/generate_synthetic_data.py --as-of 2026-10-30`: write two reproducible
  synthetic files to `data/generated/` (ignored by Git): `clean_visits.json` (every record
  valid) and `visits_with_bad_rows.json` (the same data plus deliberate bad records). The
  same `--seed` (default 42) and `--as-of` always give identical files; `--as-of` is required
  so a file never depends on today's date. `--visits` sets the number of visits (default 40,
  minimum 9, 1000 works) and `--output` the folder. Standard library only; all patients,
  staff, emails (`@example.test`), and phone numbers (`555-01xx`) are invented.

Planned utilities (not implemented):

- `import_data.py`: validate records and import the accepted batch atomically.
- `backup_db.py`: use SQLite's backup API and check backup integrity.
- `verify_db.py`: check database integrity and known demo records.
- `restore_db.py`: restore a verified backup to a disposable database for testing.

Keep database logic in the application service/repository layers. Never use real
patient data. Store local backups in the ignored `backups/` directory.
