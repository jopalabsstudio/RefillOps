PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS stations (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, center_lat REAL NOT NULL,
    center_lon REAL NOT NULL, radius_km REAL NOT NULL CHECK (radius_km > 0),
    timezone TEXT NOT NULL, currency TEXT NOT NULL,
    unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor >= 0)
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    display_name TEXT NOT NULL, role TEXT NOT NULL CHECK (role IN ('OWNER','STAFF','RIDER')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    api_key_hash TEXT UNIQUE NOT NULL,
    UNIQUE (id, station_id)
);
CREATE TABLE IF NOT EXISTS customers (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    display_name TEXT NOT NULL, opening_containers INTEGER NOT NULL DEFAULT 0 CHECK (opening_containers >= 0),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE (id, station_id)
);
CREATE TABLE IF NOT EXISTS delivery_locations (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    customer_id TEXT NOT NULL, label TEXT NOT NULL,
    lat REAL NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon REAL NOT NULL CHECK (lon BETWEEN -180 AND 180),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1)),
    numeric_alias TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id, station_id) REFERENCES customers(id, station_id),
    UNIQUE (id, station_id), UNIQUE (station_id, numeric_alias)
);
CREATE TABLE IF NOT EXISTS location_tokens (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    location_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, revoked_at TEXT,
    FOREIGN KEY (location_id, station_id) REFERENCES delivery_locations(id, station_id)
);
CREATE TABLE IF NOT EXISTS delivery_orders (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    order_number TEXT NOT NULL, customer_id TEXT NOT NULL, location_id TEXT NOT NULL,
    requested_qty INTEGER NOT NULL CHECK (requested_qty > 0),
    unit_price_minor INTEGER NOT NULL CHECK (unit_price_minor >= 0),
    status TEXT NOT NULL CHECK (status IN ('CREATED','ASSIGNED','OUT_FOR_DELIVERY','COMPLETED','DELIVERY_FAILED','CANCELLED')),
    rider_id TEXT, created_by TEXT NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, failure_reason TEXT,
    FOREIGN KEY (customer_id, station_id) REFERENCES customers(id, station_id),
    FOREIGN KEY (location_id, station_id) REFERENCES delivery_locations(id, station_id),
    FOREIGN KEY (rider_id, station_id) REFERENCES users(id, station_id),
    FOREIGN KEY (created_by, station_id) REFERENCES users(id, station_id),
    UNIQUE (id, station_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_station_number ON delivery_orders(station_id, order_number);
CREATE INDEX IF NOT EXISTS idx_orders_station_status ON delivery_orders (station_id, status);
CREATE TABLE IF NOT EXISTS delivery_confirmations (
    id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE,
    station_id TEXT NOT NULL REFERENCES stations(id),
    delivered_qty INTEGER NOT NULL CHECK (delivered_qty > 0),
    returned_empties_qty INTEGER NOT NULL CHECK (returned_empties_qty >= 0),
    confirmed_by TEXT NOT NULL, confirmed_at TEXT NOT NULL, request_key TEXT NOT NULL,
    FOREIGN KEY (order_id, station_id) REFERENCES delivery_orders(id, station_id),
    FOREIGN KEY (confirmed_by, station_id) REFERENCES users(id, station_id)
);
CREATE TABLE IF NOT EXISTS container_movements (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    customer_id TEXT NOT NULL, order_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('FULL_DELIVERED','EMPTY_RETURNED','ADJUSTMENT')),
    delta INTEGER NOT NULL CHECK (delta <> 0), created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id, station_id) REFERENCES customers(id, station_id),
    FOREIGN KEY (order_id, station_id) REFERENCES delivery_orders(id, station_id)
);
CREATE INDEX IF NOT EXISTS idx_containers_customer ON container_movements (station_id, customer_id);
CREATE TABLE IF NOT EXISTS account_entries (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    customer_id TEXT NOT NULL, order_id TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('CHARGE','PAYMENT','CREDIT','ADJUSTMENT')),
    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0), reason TEXT,
    reference TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id, station_id) REFERENCES customers(id, station_id),
    FOREIGN KEY (order_id, station_id) REFERENCES delivery_orders(id, station_id),
    UNIQUE (station_id, order_id, kind)
);
-- Allocation connects a posted payment to exactly one completed order in the demo.
-- Payments recorded before this feature remain unallocated; they are never guessed.
CREATE TABLE IF NOT EXISTS order_payment_allocations (
    payment_entry_id TEXT PRIMARY KEY REFERENCES account_entries(id),
    station_id TEXT NOT NULL REFERENCES stations(id),
    order_id TEXT NOT NULL,
    allocated_minor INTEGER NOT NULL CHECK (allocated_minor > 0),
    FOREIGN KEY (order_id, station_id) REFERENCES delivery_orders(id, station_id)
);
CREATE INDEX IF NOT EXISTS idx_allocations_order ON order_payment_allocations(station_id, order_id);
CREATE INDEX IF NOT EXISTS idx_account_customer ON account_entries (station_id, customer_id);
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    customer_id TEXT NOT NULL,
    month TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('ISSUED')),
    total_minor INTEGER NOT NULL CHECK (total_minor >= 0), issued_at TEXT NOT NULL,
    FOREIGN KEY (customer_id, station_id) REFERENCES customers(id, station_id),
    UNIQUE (id, station_id)
);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    invoice_id TEXT NOT NULL, account_entry_id TEXT NOT NULL UNIQUE,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    FOREIGN KEY (invoice_id, station_id) REFERENCES invoices(id, station_id),
    FOREIGN KEY (account_entry_id) REFERENCES account_entries(id)
);
CREATE TABLE IF NOT EXISTS exceptions (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
    kind TEXT NOT NULL, severity TEXT NOT NULL CHECK (severity IN ('LOW','MEDIUM','HIGH')),
    state TEXT NOT NULL CHECK (state IN ('OPEN','REVIEWED')),
    note TEXT, created_at TEXT NOT NULL, reviewed_at TEXT, reviewed_by TEXT,
    FOREIGN KEY (reviewed_by, station_id) REFERENCES users(id, station_id)
);
CREATE TABLE IF NOT EXISTS audit_events (
    id TEXT PRIMARY KEY, station_id TEXT NOT NULL REFERENCES stations(id),
    actor_id TEXT NOT NULL, action TEXT NOT NULL,
    target_type TEXT NOT NULL, target_id TEXT NOT NULL,
    metadata_json TEXT NOT NULL, created_at TEXT NOT NULL,
    FOREIGN KEY (actor_id, station_id) REFERENCES users(id, station_id)
);
CREATE INDEX IF NOT EXISTS idx_audit_station_time ON audit_events (station_id, created_at);
CREATE TABLE IF NOT EXISTS idempotency_records (
    station_id TEXT NOT NULL REFERENCES stations(id),
    command TEXT NOT NULL, request_key TEXT NOT NULL,
    fingerprint TEXT NOT NULL, result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (station_id, command, request_key)
);

-- Read-only customer demo keys; entirely separate from staff/rider permissions.
CREATE TABLE IF NOT EXISTS customer_portal_keys (
    customer_id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    FOREIGN KEY (customer_id, station_id) REFERENCES customers(id, station_id)
);
