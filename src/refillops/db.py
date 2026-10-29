"""SQLite storage for a local demo. Not a hosted multi-user production store."""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / '.local' / 'refillops.sqlite3'


def db_path() -> Path:
    return Path(os.environ.get('REFILLOPS_DB', str(DEFAULT_PATH))).resolve()


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    return conn


def init_db() -> None:
    """Create or migrate the demo schema without discarding existing records."""
    with connect() as conn:
        old_orders = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='delivery_orders'").fetchone()
        has_number = bool(old_orders) and any(r['name'] == 'order_number' for r in conn.execute('PRAGMA table_info(delivery_orders)'))
        # The new schema contains a unique order-number index; add the legacy column
        # and populate it BEFORE running schema.sql for existing databases.
        if old_orders and not has_number:
            conn.execute('BEGIN IMMEDIATE')
            try:
                conn.execute('ALTER TABLE delivery_orders ADD COLUMN order_number TEXT')
                for station in conn.execute('SELECT DISTINCT station_id FROM delivery_orders'):
                    rows = conn.execute('SELECT id FROM delivery_orders WHERE station_id=? ORDER BY created_at, rowid',
                                        (station['station_id'],)).fetchall()
                    for index, row in enumerate(rows, start=1):
                        conn.execute('UPDATE delivery_orders SET order_number=? WHERE id=?',
                                     (f'RO-{index:06d}', row['id']))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        sql = (Path(__file__).parent / 'schema.sql').read_text(encoding='utf-8')
        conn.executescript(sql)


@contextmanager
def transaction():
    conn = connect()
    try:
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def one(conn, query: str, args=()):
    row = conn.execute(query, args).fetchone()
    return dict(row) if row is not None else None


def many(conn, query: str, args=()):
    return [dict(r) for r in conn.execute(query, args).fetchall()]
