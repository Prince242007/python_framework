BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gujarati_name TEXT NOT NULL CHECK(length(trim(gujarati_name)) > 0),
    search_name TEXT NOT NULL CHECK(length(trim(search_name)) > 0),
    price_paise INTEGER NOT NULL CHECK(typeof(price_paise) = 'integer' AND price_paise > 0)
);

CREATE TABLE IF NOT EXISTS bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_number TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL CHECK(length(trim(customer_name)) > 0),
    bill_date TEXT NOT NULL,
    total_paise INTEGER NOT NULL CHECK(typeof(total_paise) = 'integer' AND total_paise > 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

-- Keep the sold name and rate even if the catalogue is edited later.
CREATE TABLE IF NOT EXISTS bill_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL REFERENCES bills(id) ON DELETE RESTRICT,
    item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
    gujarati_name TEXT NOT NULL,
    search_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK(typeof(quantity) = 'integer' AND quantity > 0),
    price_paise INTEGER NOT NULL CHECK(typeof(price_paise) = 'integer' AND price_paise > 0)
);
CREATE INDEX IF NOT EXISTS idx_bills_date ON bills(bill_date);
CREATE INDEX IF NOT EXISTS idx_bill_items_bill ON bill_items(bill_id);

-- This ledger also supports standalone outstanding balances from the old app.
CREATE TABLE IF NOT EXISTS pending_bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER UNIQUE REFERENCES bills(id) ON DELETE RESTRICT,
    date TEXT NOT NULL,
    customer_name TEXT NOT NULL CHECK(length(trim(customer_name)) > 0),
    amount_paise INTEGER NOT NULL CHECK(typeof(amount_paise) = 'integer' AND amount_paise > 0)
);
CREATE TABLE IF NOT EXISTS pending_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_bill_id INTEGER NOT NULL REFERENCES pending_bills(id) ON DELETE RESTRICT,
    date TEXT NOT NULL,
    amount_paise INTEGER NOT NULL CHECK(typeof(amount_paise) = 'integer' AND amount_paise > 0)
);
CREATE INDEX IF NOT EXISTS idx_payments_pending ON pending_payments(pending_bill_id);

CREATE TABLE IF NOT EXISTS workers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    hourly_rate_paise INTEGER NOT NULL CHECK(typeof(hourly_rate_paise) = 'integer' AND hourly_rate_paise > 0)
);
CREATE TABLE IF NOT EXISTS worker_hours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE RESTRICT,
    date TEXT NOT NULL,
    hours REAL NOT NULL CHECK(typeof(hours) IN ('integer', 'real') AND hours >= 0 AND hours <= 24),
    hourly_rate_paise INTEGER NOT NULL CHECK(typeof(hourly_rate_paise) = 'integer' AND hourly_rate_paise > 0),
    UNIQUE(worker_id, date)
);
CREATE TABLE IF NOT EXISTS worker_advances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    worker_id INTEGER NOT NULL REFERENCES workers(id) ON DELETE RESTRICT,
    date TEXT NOT NULL,
    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
    amount_paise INTEGER NOT NULL CHECK(typeof(amount_paise) = 'integer' AND amount_paise > 0)
);
CREATE INDEX IF NOT EXISTS idx_worker_advances_date ON worker_advances(worker_id, date);

PRAGMA user_version = 1;
COMMIT;
