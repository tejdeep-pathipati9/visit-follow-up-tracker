# Changelog

## Unreleased

### Fixed

- Added uv project metadata and development dependencies so `uv sync` and
  `uv run` work from the repository root; added the dependency lockfile.

### Added

- A shared read-only SQL query endpoint for all application tables and a live
  plain-text schema endpoint, with bound parameters and ordered result columns/rows.
- SQLite authorization, execution/result limits, and integration tests for SQL
  queries, joins, aggregates, schema discovery, and rejected writes.
- Independent deterministic overdue/due-soon/unassigned rule classes.
- Explicit SQLite table initialization with atomic schema creation, repeat-run
  data preservation, database path overrides, and unit tests.
- Python/FastAPI project structure with a placeholder home page and health route.
- Synthetic sample data, domain constants in application code, and the proposed core SQL schema.
- Local development configuration, Docker with a named data volume, and CI smoke checks.

Ingestion, reports, history, updates, natural-language interpretation, and
releases 1.0.0 / 1.1.0 remain planned; no release is tagged.
