# Changelog

## Unreleased

### Fixed

- A staff member's question could read other staff members' records when the generated
  SQL defined a CTE named after a table, such as
  `WITH followups AS (SELECT * FROM main.followups)`. Their questions now run on a copy
  that holds only their rows.
- Lists, counts, and the report no longer fail with `query_limit_exceeded` on ten years of
  records (120,000 visits): the app's own searches have only a 30-second time limit. The
  step and 2-second limits still apply to model-written SQL.
- `create_manager.py` gives managers the IDs `M001`, `M002`, and so on; it used `S001`,
  which made a later import of a generated file fail with "already saved".
- Compose passes the optional OpenAI settings to the container, so plain-English questions
  work in Docker.
- The Sort menu now lists every sort option; it previously showed only Default.
- Added uv project metadata and development dependencies so `uv sync` and
  `uv run` work from the repository root; added the dependency lockfile.

### Changed

- `status_changes` is replaced by `followup_history`: one row for each change of status,
  scheduled date, or staff member, with who made it.
- Everyone can ask plain-English questions; staff who are not managers get answers from
  their own follow-ups only. Their questions run on a private in-memory copy that holds only
  their rows.
- Every visit (consultation, test, or treatment) needs a staff member.
- "Unassigned" now means a follow-up has no scheduled date yet. `followups.due_date` is the
  scheduled date and may be NULL; overdue and due soon apply only when it is set, so the
  three flags never combine, and follow-ups without a date sort last.
- Every follow-up must have an assigned staff member (`assigned_staff_id` is `NOT NULL`,
  required on create, and cannot be cleared). The `unassigned` staff filter and the
  `unassigned_overdue` preset are removed.
- Existing databases keep the old column constraints until they are re-created with
  `scripts/table_generate.py`.
- Due soon now uses a window per action type from `config/settings.json` (lab 3 days,
  referral and recheck 14 days) everywhere: flags, the `due_soon` filter and preset,
  dashboard and summary counts, and `/api/ask`. `GET /api/options` returns
  `due_soon_days_by_action` instead of `due_soon_days`.
- Choosing Closed in a follow-up row opens a dialog that asks for the reason, with the
  clinic's usual reasons to pick from; it replaces the browser's prompt.
- The Ask tab shows the answer and its rows, not the SQL; `/api/ask` still returns the SQL
  and its parameters.
- Removed the public `POST /api/query` endpoint; callers can no longer send SQL.
  The restricted executor is now used only inside the server.

### Added

- Import a whole data file from the web app (managers), `POST /api/import`, or
  `scripts/import_data.py`. Every record is validated and cross-checked (missing parents
  or staff, duplicate or already-saved IDs); any rejection rejects the whole file and
  nothing is saved.
- `scripts/backup_db.py`: verified backups (`Connection.backup`, `PRAGMA integrity_check`,
  test restore). `scripts/delete_old_records.py`: the clinic's 10-year retention.
- A test of the whole tool on the synthetic files.
- Team documents in `docs/`: the assumptions log (clinic answers and team decisions with
  sources and deciders) and remaining work by owner. The README now describes only the
  program and how to use it.
- Sign-in by staff email (no password in this release; passwords come later). A manager
  sees and edits everything; other staff see only the follow-ups assigned to them, the
  patients those belong to, and counts of their own work, and can change only their own
  follow-ups. Natural-language questions are limited to managers. Staff have a unique
  `email`.
- A printable report at `/report` (and `GET /api/report`): open follow-ups that are
  overdue, due soon, or unassigned, grouped by flag, with patient ID, action, scheduled
  date, and assigned staff.
- `scripts/create_manager.py` adds the first manager who can sign in.
- Reproducible synthetic data generator (`scripts/generate_synthetic_data.py`, from
  Sanket's PR #9), updated for required staff, unassigned as no scheduled date,
  open/done/closed with reasons, and staff emails with one manager.
- A `closed` follow-up status for actions that could not be completed (patient unreachable,
  did not return, no results), which requires a reason in the new `followups.notes`.
- Status-change history: every status change adds a `status_changes` row in the same
  transaction, shown as `history` on the follow-up detail and in the UI drawer.
- CSV downloads for every record type (`GET /api/{type}/export`) with the same filters
  and sort as the list, every matching row, and formula-safe cells.
- Spreadsheet-style list view: gridlines, frozen header and ID column, row tints by
  state with a legend, header-click sorting, 25/100/500 rows per page, an inline
  follow-up status menu, and a Download CSV button.
- A web UI (one Jinja2 page with plain JavaScript): summary cards, filterable and
  sortable lists for every record type, a detail panel with edit, create, and
  follow-up Mark done/Reopen, and an Ask tab for read-only questions.
- Create (`POST`) and partial update (`PATCH`) endpoints for patients, staff,
  episodes, visits, and follow-ups using fixed, parameterized SQL in one
  transaction per request. IDs are generated when omitted; follow-up completion
  times are set by the server; records are never deleted.
- Search endpoints for patients, staff, episodes, visits, and follow-ups with
  combinable filters, presets, sorting, paging, grouped counts, detail views, a
  dashboard, and an options endpoint for dropdowns and sliders. All search SQL is
  fixed and parameterized.
- `POST /api/ask`: the OpenAI Decisions API rejects prompts that ask to change
  data before a second model writes read-only SQL, which runs through the
  restricted executor. Patient phone and email read as NULL in generated queries.
- A restricted read-only SQL executor and a live plain-text schema endpoint, with
  bound parameters and ordered result columns/rows.
- SQLite authorization, execution/result limits, and integration tests for SQL
  queries, joins, aggregates, schema discovery, and rejected writes.
- Independent deterministic overdue/due-soon/unassigned rule classes.
- Explicit SQLite table initialization with atomic schema creation, repeat-run
  data preservation, database path overrides, and unit tests.
- Python/FastAPI project structure with a placeholder home page and health route.
- Synthetic sample data, domain constants in application code, and the proposed core SQL schema.
- Local development configuration, Docker with a named data volume, and CI smoke checks.

Bulk import, reports, status-change history, authentication, and
releases 1.0.0 / 1.1.0 remain planned; no release is tagged.
