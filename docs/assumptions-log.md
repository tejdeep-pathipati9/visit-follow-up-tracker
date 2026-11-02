# Assumptions log

Decisions the brief leaves open. Add a row when something is decided; if a decision
changes, add a new row and mark the old one *Replaced by …*.

Status: **Clinic** (the instructor answered as the clinic), **Agreed** (team agreed),
**Confirm** (built this way, team still needs to agree), **Open** (see
[remaining work](remaining-work.md#open-questions)).

## Clinic answers

"Who decided" is the member who asked, per our question split; fix it if someone else asked.

| ID | Decision | What we assumed | Source | Who decided | Status |
|---|---|---|---|---|---|
| C1 | When is a follow-up overdue? | From the day after its scheduled date; on the day itself it is "due soon". A patient who cannot attend gets a new date, or the follow-up is closed with a reason. | Q1 | Sanket | Clinic |
| C2 | Due-soon window | Lab 3 days, referral 14, recheck 14 | Q2 | Sanket | Clinic |
| C3 | Statuses | `open`, `done`, `closed` (unreachable, did not return, no results); closed needs the reason in notes | Q3 | Sanket | Clinic |
| C4 | A file with a bad row | Reject the whole file, report every reason, save nothing | Q4 | Sanket | Clinic |
| C5 | Where staff use the tool | Their own computers at the clinic | Q5 | Jihyung | Clinic |
| C6 | Reports | Printable reports are required | Q6 | Jihyung | Clinic |
| C7 | Data volume | About 1,000 visits **per month** | Q7 and follow-up answer | Jihyung | Clinic |
| C8 | History | Keep previous visits, appointments, and patient history | Q8 | Jihyung | Clinic |
| C9 | Who sees what | Staff see only follow-ups assigned to them | Q9 | Tejdeep | Clinic |
| C10 | Retention | Keep 10 years, then delete. This is the clinic's own wish, not a regulation. | Q10 and follow-up answer | Tejdeep | Clinic |
| C11 | Web app or command line | The web app may replace the command line tool the brief asks for | Instructor | Jihyung | Clinic |

## Team decisions

| ID | Decision | What we assumed | Reason | Who decided | Status |
|---|---|---|---|---|---|
| A1 | Meaning of "unassigned" | No scheduled date yet, never "no staff member". So the three flags never apply together. | Team question list | Jihyung | Agreed |
| A2 | Follow-up without staff | Not allowed: every follow-up has an assigned staff member | It always comes from a patient visit | Jihyung | Agreed |
| A3 | Dates per follow-up | One scheduled date, stored as `due_date`, shown as "Scheduled"; may be empty (A1) | Team question list | Jihyung | Agreed |
| A4 | Settings file | `config/settings.json`: allowed action types and a due-soon window per type (C2); read at startup | Brief | Sanket | Agreed |
| A5 | Today's date | Passed in as `as_of_date` (the "As of" box; `--as-of` in scripts), never read inside rules | Repeatable tests | Sanket | Agreed |
| A6 | Database path variable | `FOLLOWUP_DB_PATH`; a named volume in Docker | Brief | Tejdeep | Agreed |
| A7 | Status history | Replaced by A19 | | Jihyung | Replaced by A19 |
| A8 | Sign-in | Staff email only, for internal use; passwords in a later release (A26) | C9 needs to know who is signed in | Jihyung | Agreed |
| A9 | Who sees everything | Role `manager`; other staff see their follow-ups and those patients' records, with counts of their own work only | C9; the manager still needs the whole picture | Jihyung | Agreed |
| A10 | What other staff can change | Status, date, staff member, and notes of their own follow-ups; everything else, including imports, is for managers | Keeps C9 simple | Jihyung | Confirm |
| A11 | Plain-English questions | Replaced by A17 | | Jihyung | Replaced by A17 |
| A12 | Report contents | Open follow-ups that are overdue, due soon, or unassigned, grouped by flag, with patient ID, action, date, and staff | Brief; C6 | Jihyung | Agreed |
| A13 | Episodes | Visits are grouped by medical issue (patient → episode → visit → follow-up) | Shows one case's visits together; beyond the brief | Team | Agreed |
| A14 | Web app or command line | The web app is the interface; scripts cover operations (import, backup, retention) | C11 | Team | Agreed |
| A15 | Release 1.1.0 rule | Replaced by A18 | | Sanket | Replaced by A18 |
| A16 | Reschedule history | Replaced by A19 | | Jihyung | Replaced by A19 |
| A17 | Plain-English questions | Everyone may ask; staff who are not managers get answers from their own rows only. Enforced by the database, not by the model: their questions run on a private in-memory copy that holds only their rows. | C9 | Jihyung | Agreed |
| A18 | Release 1.1.0 | Replaced by A26 | | Jihyung | Replaced by A26 |
| A19 | Change history | One `followup_history` row for each change of status, scheduled date, or staff member, with who made it and the note sent with it, in the same transaction as the change | Brief; C1, C8 | Jihyung | Agreed |
| A20 | What a visit is | Every encounter in an episode: a consultation, a test, or a treatment. Every visit has a staff member. | Clarified by Jihyung | Jihyung | Agreed |
| A21 | How retention works | `delete_old_records.py` deletes visits older than 10 years with their follow-ups and history, then episodes and patients left with no visits; staff stay. One transaction; `--dry-run` first. | C10 | Jihyung | Agreed |
| A22 | Repeat imports | IDs or staff emails already saved are rejections, so importing the same file twice saves nothing the second time | Brief: no silent duplicates; C4 | Jihyung | Agreed |
| A23 | First start | Import a file that includes a manager, or run `create_manager.py` on an empty database. Managers it adds are `M001`, `M002`, … so a file imported later with `S001`-style staff still imports. | Only a manager can add staff (A10) | Jihyung | Agreed |
| A24 | Presentation | One HTML slide page: three or four overview slides, then each feature as a screenshot with red circles on the parts to look at. Who shares the screen does not matter. | Team | Jihyung | Agreed |
| A25 | What the model is told | The question, the table layout, the date, and the asker's staff ID (no names); for staff, that their tables already hold only their rows, so "my follow-ups" works | Without it, "my" questions returned nothing | Jihyung | Agreed |
| A26 | Release 1.1.0 | The calendar (scheduled follow-ups and important dates) and a dashboard for follow-up and patient management, with one chart at most. 1.0.0 is the tag `v1.0.0` on the main branch of 2026-11-02. Passwords come in a later release. | Team decision, 2026-11-02 | Jihyung | Agreed (see O9) |
| A27 | Calendar events | An event is for one staff member or the whole clinic. Managers see and change every event; other staff see the clinic's events and their own, and add, change, or delete only their own. Events can be deleted; they are not patient records, so plain-English questions and the 10-year clean-up leave them out. | Keeps the access rule of C9 and A10 | Jihyung | Confirm |
| A28 | Upgrades | The app creates missing tables when it starts with an existing database, so a new release that only adds tables needs no manual step, and the previous release can still read the database | Release and rollback on one volume | Jihyung | Agreed |
