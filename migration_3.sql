BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS pending_actions (
    token TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    pending_bill_id INTEGER NOT NULL REFERENCES pending_bills(id) ON DELETE CASCADE,
    payment_id INTEGER REFERENCES pending_payments(id) ON DELETE RESTRICT
);
PRAGMA user_version = 3;
COMMIT;
