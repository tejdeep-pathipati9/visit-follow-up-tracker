# Operational scripts

Run from the repository root. Database scripts use `--db-path` or `FOLLOWUP_DB_PATH`
(default `data/followups.db`); none of them load `.env`.

- `table_generate.py`: create the tables and indexes from `app/schema.sql`, keeping
  existing records. It does not migrate an older database; re-create it after a schema change.
- `generate_synthetic_data.py --as-of YYYY-MM-DD`: write `clean_visits.json` and
  `visits_with_bad_rows.json` to `data/generated/` (ignored by Git). The same `--seed`
  (default 42) and `--as-of` give identical files. `--visits` sets the number of visits
  (default 40, minimum 9). Every record is invented; staff have `@clinic.example.test`
  emails and one is a manager.
- `import_data.py --file FILE`: import a whole file. If any record is rejected, every
  problem is printed and nothing is saved (exit code 1).
- `create_manager.py --name NAME --email EMAIL`: add a manager to a database that has none,
  so someone can sign in. Managers added here get `M001`, `M002`, and so on, so they never
  clash with the `S001`-style staff IDs of a file imported later.
- `backup_db.py [--output DIR]`: copy the live database with SQLite's backup API to
  `backups/` (ignored by Git), run `PRAGMA integrity_check`, and test-restore the copy.
- `delete_old_records.py [--as-of DATE] [--dry-run]`: delete visits older than 10 years with
  their follow-ups and history, then patients and episodes left with no visits.

Never use real patient data.
