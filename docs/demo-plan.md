# Demo plan

About eight minutes, right after the slides (`presentation/index.html`), on the Docker
setup. Synthetic data only. Who shares the screen does not matter (A24).

## Before the session

Do this the day before, rehearse once, reset, and do it again 30 minutes before.

- [ ] Docker Desktop is running, and `.env` has `OPENAI_API_KEY` and `OPENAI_MODELS` (only
  step 8 needs them).
- [ ] A fresh database with one manager:

  ```bash
  docker compose down --volumes        # deletes the demo database
  docker compose build
  docker compose run --rm app python scripts/table_generate.py
  docker compose run --rm app python scripts/create_manager.py --name "Clinic Manager" --email manager@clinic.example.test
  docker compose up -d
  ```

- [ ] The two files, dated the day of the demo:

  ```bash
  uv run python scripts/generate_synthetic_data.py --as-of YYYY-MM-DD
  ```

  This writes `data/generated/visits_with_bad_rows.json` and
  `data/generated/clean_visits.json`.
- [ ] A browser at `http://localhost:8000`, signed out, with notifications off.
- [ ] A terminal in the repository with a large font, for steps 9 and 10.
- [ ] The slides open in another window, for the fallbacks.

## Steps

| # | Do | Say | Expect |
|---|---|---|---|
| 1 | Sign in as `manager@clinic.example.test` | Staff sign in with their clinic email; 1.1.0 adds passwords. | An empty tracker; every count is 0 |
| 2 | **Import file**, choose `visits_with_bad_rows.json` | The clinic asked for all or nothing. | "was rejected: nothing was saved", 12 problems with reasons; counts still 0 |
| 3 | **Import file**, choose `clean_visits.json` | The same file without the bad records. | 15 patients, 5 staff, 23 episodes, 40 visits, 79 follow-ups; the counts fill in |
| 4 | **Follow-ups** tab; move **As of** a week ahead, then back | Flags follow the clinic's windows: lab 3 days, referral and recheck 14. | More follow-ups turn overdue a week ahead |
| 5 | **Printable report**, then **Print** | What the manager prints. | Follow-ups grouped by flag; the print preview has no buttons |
| 6 | Sign out; sign in as `birch.sample@clinic.example.test` | A nurse sees only her own follow-ups. | Smaller counts; every row is assigned to her |
| 7 | On an overdue row, set **Status** to **Closed**, pick "Patient unreachable after three calls", and **Close follow-up**; open the row | Closing needs a reason, and every change is kept. | The history shows the change, her name, the time, and the reason |
| 8 | **Ask** tab: "How many of my follow-ups are overdue, by action type?"; then click "Mark F001 as done" | Questions read her rows only; they cannot change anything. | The counts add up to her Overdue tile; the second request is refused |
| 9 | Terminal: `docker compose exec app python scripts/backup_db.py --output /data/backups` | Backups are checked, not just copied. | "integrity_check ok, test restore matched" |
| 10 | Terminal: `docker compose up -d --force-recreate`; refresh; sign in as the manager; open the closed follow-up | The container is replaced; the data volume stays. | The follow-up is still closed, with its history |

Everyone signs in again after step 10, because sessions are kept in memory.

When release 1.1.0 exists, add: upgrade to 1.1.0, sign in with a password, roll back to
1.0.0, and show the history is still there (see [remaining work](remaining-work.md)).
Until then, step 10 shows the same idea.

## If something goes wrong

- **Ask fails** (no network or key): say so, show the Ask slide, and move on.
- **Docker fails**: run it locally with the same steps. Use `uv run python scripts/...`
  with `--db-path data/demo.db`, and start the app with
  `FOLLOWUP_DB_PATH=data/demo.db uv run uvicorn app.main:app --env-file .env`. In step
  10, restart the server instead.
- **More than 12 problems in step 2**: the database was not empty. Reset and start again.
- **Port 8000 is busy**: stop the other app, or change the port in `compose.yaml`.

## Reset after a rehearsal

```bash
docker compose down --volumes
```

Then repeat the setup.
