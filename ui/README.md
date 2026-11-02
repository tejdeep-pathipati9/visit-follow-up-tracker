# Visit Follow-Up Tracker UI

React + TypeScript, Vite, Tailwind CSS, and shadcn/ui Radix components in a separate
`ui/` folder. The shell and dashboard grid adapt Efferd Dashboard 5 and App Shell 5
for clinic operations. Attribution is in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Run with Docker

From the repository root, with Docker running:

```bash
docker compose build
# First start on a new database:
docker compose run --rm app python scripts/table_generate.py
docker compose run --rm app python scripts/create_manager.py --name "Clinic Manager" --email manager@clinic.example
docker compose up -d
```

Open http://localhost:8000 and sign in with `manager@clinic.example`. Managers can
add records or use **Import data** to upload synthetic JSON files. The main README
explains generating and importing the supplied synthetic dataset, whose manager
email is `elm.overseer@clinic.example.test`.

SQLite stays on the existing `followup_data` named volume at `/data/followups.db`.
Docker builds the frontend; teammates do not need local Node or Python. For an
update, use `docker compose up -d --build`. Keep the existing volume.

**View sample dashboard** at sign-in or http://localhost:8000/?demo=1 provides an
in-memory preview with no database writes or external AI calls. Sample work is
clearly labeled and resets on reload. Only synthetic data may be used.

## Develop locally

Install Node.js 24 and follow the main README's Python/database setup. From the
repository root:

```bash
npm ci --prefix ui
npm run dev --prefix ui
```

Vite serves http://localhost:5173 and proxies `/api`, `/health`, and API documentation
to FastAPI at http://127.0.0.1:8000. Run FastAPI in another terminal:

```bash
uv run uvicorn app.main:app --reload --env-file .env
```

For FastAPI to serve the production frontend at port 8000:

```bash
npm run build --prefix ui
```

## Checks

```bash
npm test --prefix ui
npm run build --prefix ui
uv run pytest -q
```

Build runs strict TypeScript checking. CI's stable `test` check runs frontend
interaction tests and builds the UI before the Python integration suite.

## Main workflows

- Dashboard cards, urgency charts, and a follow-up worklist use backend counts.
  The dashboard timeline reads up to 1,000 records and discloses truncation.
- Follow-ups support search, type/status/staff/attention filters, sorting, paging,
  completion, reopening, notes, and closing with a reason.
- **Unassigned means no scheduled date.** Every visit and follow-up has staff.
  Due soon is Lab 3 days, Referral 14 days, and Recheck 14 days. Due today is not overdue.
- Details display previous visits and the backend's field-level follow-up history.
- Reports link to the authenticated `/report` print view. Connected CSV exports
  use backend endpoints and include all matching rows.
- **Import data** is for managers; backend validation rejects the whole file on
  any error and the UI shows every rejection reason.
- AI Search and the bottom-right Agent use `/api/ask`. Minimize preserves the
  draft; expand makes room for results; new chat cancels pending work. Each
  question is independent. The conversation resets on identity, workspace, or
  assessment-date changes and is not stored locally. AI needs a configured model key.

## Backend integration

Use the merged backend's `/api/session` contract: GET checks the session, POST
signs in with `{ "email": "..." }`, and DELETE signs out. Identification is
email-only for the internal synthetic demo; restarting the server signs users out.
Managers see all records. Other staff see assigned follow-ups and related patient
context. All record access, reports, exports, imports, and AI queries are enforced
by the backend. UI permissions reflect that policy.

## Structure

- `src/components/ui/`: source-managed shadcn components.
- `src/components/app-*`: shared application shell.
- `src/pages/`: dashboard, worklist, records, reports, import, AI search, settings.
- `src/lib/api.ts`: API errors, requests, and full CSV downloads.
- `src/lib/session.tsx`: email sign-in and session lifecycle.
- `src/lib/workspace.tsx`: data source, assessment date, queries, and mutations.
- `src/lib/sample-data.ts`: explicitly selected synthetic preview.
- `src/test/`: workflow, API-boundary, and interaction tests.

Hash routes let FastAPI serve one application entry point. The generated `dist/`
and `node_modules/` are ignored. Printable report assets remain served by FastAPI.

For additional shadcn components, from `ui/`:

```bash
npx shadcn@latest add <component>
```
