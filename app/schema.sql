-- Core schema. scripts/table_generate.py creates it; the app also runs it when it starts
-- with an existing database, so a new release adds its tables without touching data.
-- Every change to a follow-up's status, scheduled date, or staff member is kept in
-- followup_history, written in the same transaction as the change.

PRAGMA foreign_keys = ON; -- Execute for EVERY new SQLite connection.

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    phone      TEXT,
    email      TEXT
);

CREATE TABLE IF NOT EXISTS staff (
    staff_id TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    role     TEXT NOT NULL,  -- "manager" sees every follow-up; everyone else sees their own
    email    TEXT UNIQUE COLLATE NOCASE  -- sign-in name; passwords come in a later release
);

CREATE TABLE IF NOT EXISTS episodes (
    episode_id  TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL,
    description TEXT NOT NULL,
    opened_at   TEXT NOT NULL,
    closed_at   TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    UNIQUE (episode_id, patient_id)
);

CREATE TABLE IF NOT EXISTS visits (
    visit_id    TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL,
    episode_id  TEXT NOT NULL,
    staff_id    TEXT NOT NULL,  -- who saw the patient, ran the test, or gave the treatment
    visit_date  TEXT NOT NULL,
    notes       TEXT,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    FOREIGN KEY (episode_id, patient_id)
        REFERENCES episodes(episode_id, patient_id),
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id)
);

CREATE TABLE IF NOT EXISTS followups (
    followup_id       TEXT PRIMARY KEY,
    visit_id          TEXT NOT NULL,
    action_type       TEXT NOT NULL
                      CHECK (action_type IN ('lab', 'referral', 'recheck')),
    due_date          TEXT,  -- scheduled date; NULL means unassigned (not yet scheduled)
    assigned_staff_id TEXT NOT NULL,  -- every follow-up has a responsible staff member
    status            TEXT NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open', 'done', 'closed')),
    completed_at      TEXT,  -- when it became done or closed; NULL while open
    notes             TEXT,  -- a closed follow-up must say why it could not be completed
    FOREIGN KEY (visit_id) REFERENCES visits(visit_id),
    FOREIGN KEY (assigned_staff_id) REFERENCES staff(staff_id),
    CHECK (status <> 'closed' OR (notes IS NOT NULL AND length(trim(notes)) > 0))
);

CREATE TABLE IF NOT EXISTS followup_history (
    change_id   INTEGER PRIMARY KEY,
    followup_id TEXT NOT NULL,
    field       TEXT NOT NULL CHECK (field IN ('status', 'due_date', 'assigned_staff_id')),
    old_value   TEXT,           -- NULL: no scheduled date before the change
    new_value   TEXT,           -- NULL: the scheduled date was cleared
    changed_at  TEXT NOT NULL,  -- UTC timestamp
    changed_by  TEXT,           -- the signed-in staff member; NULL for scripts
    note        TEXT,           -- the note sent with the change, such as a closing reason
    FOREIGN KEY (followup_id) REFERENCES followups(followup_id),
    FOREIGN KEY (changed_by) REFERENCES staff(staff_id),
    CHECK (old_value IS NOT new_value),
    CHECK (field <> 'status' OR (old_value IN ('open', 'done', 'closed') AND new_value IN ('open', 'done', 'closed')))
);

-- Important dates on the calendar (release 1.1.0), such as a team meeting or a day the
-- clinic is closed. They are not patient records; follow-ups keep their own scheduled date.
CREATE TABLE IF NOT EXISTS schedule_events (
    event_id   TEXT PRIMARY KEY,
    title      TEXT NOT NULL CHECK (length(trim(title)) > 0),
    event_date TEXT NOT NULL,
    start_time TEXT,  -- HH:MM; NULL for an all-day event
    staff_id   TEXT,  -- who it is for; NULL for the whole clinic
    notes      TEXT,
    created_by TEXT,  -- who added it; NULL for scripts
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id),
    FOREIGN KEY (created_by) REFERENCES staff(staff_id)
);

CREATE INDEX IF NOT EXISTS idx_visits_episode_date
    ON visits (episode_id, visit_date);
CREATE INDEX IF NOT EXISTS idx_visits_patient_date
    ON visits (patient_id, visit_date);
CREATE INDEX IF NOT EXISTS idx_followups_status_due
    ON followups (status, due_date);
CREATE INDEX IF NOT EXISTS idx_followups_staff_status
    ON followups (assigned_staff_id, status);
CREATE INDEX IF NOT EXISTS idx_followup_history_followup
    ON followup_history (followup_id, changed_at);
CREATE INDEX IF NOT EXISTS idx_schedule_events_date
    ON schedule_events (event_date);
