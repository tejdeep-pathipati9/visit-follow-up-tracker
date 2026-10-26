# Operational scripts

Available:

- `python scripts/table_generate.py`: create the five core tables and four
  query indexes from `app/schema.sql`. Existing records are preserved on reruns.
  Use `--db-path /path/to/followups.db` or export `FOLLOWUP_DB_PATH` to choose a
  database; otherwise it uses the project's `data/followups.db`. This script uses
  only the Python standard library and does not load `.env` automatically.

Planned utilities (not implemented):

- `generate_synthetic_data.py`: write synthetic demo records to `data/generated/`.
- `import_data.py`: validate records and import the accepted batch atomically.
- `backup_db.py`: use SQLite's backup API and check backup integrity.
- `verify_db.py`: check database integrity and known demo records.
- `restore_db.py`: restore a verified backup to a disposable database for testing.

Keep database logic in the application service/repository layers. Never use real
patient data. Store local backups in the ignored `backups/` directory.
