# Changelog

## Unreleased

### Fixed

- Added uv project metadata and development dependencies so `uv sync` and
  `uv run` work from the repository root; added the dependency lockfile.

### Changed

- Removed the public `POST /api/query` endpoint; callers can no longer send SQL.
  The restricted executor is now used only inside the server.

### Added

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
