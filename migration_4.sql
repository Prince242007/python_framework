BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS worker_actions (
    token TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE CASCADE,
    advance_id INTEGER REFERENCES worker_advances(id) ON DELETE CASCADE
);
PRAGMA user_version = 4;
COMMIT;
