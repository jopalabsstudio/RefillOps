"""Local startup and fictional demo seed with generated private actor keys."""
import argparse
import json
import os
import secrets
import sqlite3
from pathlib import Path
from refillops.auth import hash_key
from refillops.db import db_path, connect, init_db, transaction
from refillops.domain import utc_now, station_month
from refillops.service import uid, create_order, assign_order, dispatch_order, complete_order, post_payment, issue_invoice, emit_exception, audit


def seed(reset=False):
    path = db_path()
    if reset and path.exists():
        path.unlink()
    init_db()
    with connect() as conn:
        n = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if n:
        raise SystemExit('Demo already seeded. Use `python -m refillops.cli seed --reset` to wipe ONLY the configured local demo DB.')
    sid = uid()
    st = {'id': sid, 'name': 'ClearSpring Demo Station (fictional)', 'center_lat': 14.65,
          'center_lon': 121.05, 'radius_km': 1.5, 'timezone': 'Asia/Manila',
          'currency': 'PHP', 'unit_price_minor': 3000}
    roles = [('owner', 'OWNER', 'Demo Owner'), ('staff1', 'STAFF', 'Demo Dispatcher'),
             ('staff2', 'STAFF', 'Demo Cashier'), ('rider1', 'RIDER', 'Demo Rider A'),
             ('rider2', 'RIDER', 'Demo Rider B')]
    access = {}
    actor_by_key = {}
    with transaction() as conn:
        conn.execute('INSERT INTO stations VALUES (?,?,?,?,?,?,?,?)', tuple(st.values()))
        for alias, role, display_name in roles:
            id, key = uid(), secrets.token_urlsafe(36)
            conn.execute('INSERT INTO users (id,station_id,display_name,role,api_key_hash) VALUES (?,?,?,?,?)',
                         (id, sid, display_name, role, hash_key(key)))
            access[alias] = {'role': role, 'display_name': display_name, 'api_key': key}
            actor_by_key[alias] = {'id': id, 'station_id': sid, 'role': role, 'display_name': display_name}
    customers = []
    # Synthetic named customers, coordinate offsets, and arbitrary container opening balances.
    customer_seed = [
        ('Sample Customer A', 2, 0.0010, 0.0002), ('Sample Customer B', 1, -0.0012, 0.0011),
        ('Sample Customer C', 4, 0.0020, -0.0010), ('Sample Customer D', 3, -0.0022, -0.0011),
        ('Sample Customer E', 0, 0.0016, 0.0017), ('Sample Customer F', 2, 0.0028, 0.0009),
        ('Sample Customer G', 1, -0.0034, -0.0006), ('Sample Customer H', 1, 0.0014, -0.0030),
        ('Sample Customer I', 2, -0.0020, 0.0022), ('Sample Customer J', 3, 0.0026, -0.0019)
    ]
    with transaction() as conn:
        for i, (name, opening, dlat, dlon) in enumerate(customer_seed, start=1):
            cid, lid = uid(), uid()
            conn.execute('INSERT INTO customers (id,station_id,display_name,opening_containers,created_at) VALUES (?,?,?,?,?)',
                         (cid, sid, name, opening, utc_now()))
            conn.execute('''INSERT INTO delivery_locations
                 (id,station_id,customer_id,label,lat,lon,numeric_alias,created_at)
                 VALUES (?,?,?,?,?,?,?,?)''',
                 (lid, sid, cid, f'Sample House {chr(64+i)}', 14.65+dlat, 121.05+dlon, f'{i:06d}', utc_now()))
            customers.append((cid, lid))
    staff = actor_by_key['staff1']
    rider1, rider2 = actor_by_key['rider1'], actor_by_key['rider2']
    # Distinct stages plus confirmed deliveries allow reviews without mutating demo history.
    for i in range(7):
        cid, lid = customers[i]
        order = create_order(staff, cid, lid, 3 if i < 3 else 2)
        if i == 0:
            unassigned_order_id = order['id']
        if i >= 1:
            assign_order(staff, order['id'], rider1['id'] if i % 2 == 0 else rider2['id'])
        if i >= 2:
            ride = rider1 if i % 2 == 0 else rider2
            dispatch_order(ride, order['id'])
        if 3 <= i <= 5:
            complete_order(ride, order['id'], 2, 1, 'seed-complete-'+str(i))
        if i == 6:
            with transaction() as conn:
                conn.execute('UPDATE delivery_orders SET status=?,failure_reason=? WHERE id=?', ('DELIVERY_FAILED', 'Fictional customer unavailable', order['id']))
                emit_exception(conn, staff, 'order', order['id'], 'DELIVERY_FAILED')
                audit(conn, staff, 'SEED_FAILED_ORDER', 'order', order['id'])
    issue_invoice(actor_by_key['owner'], customers[3][0], station_month(utc_now(), 'Asia/Manila'))
    post_payment(actor_by_key['staff2'], customers[3][0], 1000, 'Manual demo receipt', 'SEED-001')
    # At least one explicit reproducible exception independent of clock time.
    with transaction() as conn:
        emit_exception(conn, staff, 'order', unassigned_order_id, 'UNASSIGNED_ORDER_REQUIRES_REVIEW', 'LOW')
    customer_access = create_demo_customer_keys()
    access_path = path.parent / 'demo_access.json' 
    access_path.write_text(json.dumps({'station': st['name'], 'actors': access, 'customers': customer_access}, indent=2), encoding='utf-8')
    try:
        os.chmod(access_path, 0o600)
    except OSError:
        pass
    print(f'Seeded fictional station and 10 customers: {path}')
    print(f'Local demo keys stored at: {access_path} (UNTRACKED; do not commit/share)')
    print('Run: python -m refillops.cli serve')


def create_demo_customer_keys():
    """Issue local synthetic read-only customer credentials for a demo database.

    For existing keys, keep their identity and do not rotate them silently;
    the caller should preserve previously written access.json credentials.
    """
    issued = {}
    with transaction() as conn:
        records = conn.execute('SELECT id,display_name,station_id FROM customers').fetchall()
        for c in records:
            existing = conn.execute('SELECT customer_id FROM customer_portal_keys WHERE customer_id=?', (c['id'],)).fetchone()
            if existing:
                continue
            key = secrets.token_urlsafe(36)
            conn.execute('INSERT INTO customer_portal_keys VALUES (?,?,?,?)',
                         (c['id'], c['station_id'], hash_key(key), utc_now()))
            issued[c['id']] = {'display_name': c['display_name'], 'api_key': key}
    return issued


def upgrade_demo():
    """Safe, explicit upgrade for a locally seeded v0.1.3 database; no reset."""
    path = db_path()
    if path.exists():
        backup = path.parent / (path.stem + '.before-v0.1.4.sqlite3')
        if not backup.exists():
            with sqlite3.connect(path) as source, sqlite3.connect(backup) as target:
                source.backup(target)
            print(f'Local backup created: {backup} (gitignored; keep it private)')
    init_db()
    new_keys = create_demo_customer_keys()
    access_path = db_path().parent / 'demo_access.json'
    contents = json.loads(access_path.read_text(encoding='utf-8')) if access_path.exists() else {'actors': {}}
    contents.setdefault('customers', {}).update(new_keys)
    access_path.write_text(json.dumps(contents, indent=2), encoding='utf-8')
    try:
        os.chmod(access_path, 0o600)
    except OSError:
        pass
    print(f'Migration complete. Existing orders and payments preserved. New customer demo keys: {len(new_keys)}')
    print(f'Customer keys saved locally: {access_path} (do not commit)')


def relabel_demo():
    """Opt-in relabel for the original fictional seed only; preserves customer and order IDs."""
    changes = 0
    with transaction() as conn:
        stations = conn.execute("SELECT id FROM stations WHERE name='ClearSpring Demo Station (fictional)'").fetchall()
        for (sid,) in stations:
            owner = conn.execute("SELECT id,display_name FROM users WHERE station_id=? AND role='OWNER'", (sid,)).fetchone()
            if not owner:
                continue
            actor = {'id': owner['id'], 'station_id': sid, 'display_name': owner['display_name'], 'role': 'OWNER'}
            for i in range(1, 11):
                letter = chr(64 + i)
                legacy = f'Sample House {letter}'
                customer = conn.execute("""SELECT c.id, l.id AS location_id FROM customers c
                    JOIN delivery_locations l ON l.customer_id=c.id AND l.station_id=c.station_id
                    WHERE c.station_id=? AND c.display_name=? AND l.label=? AND l.numeric_alias=?""",
                    (sid, legacy, f'Demo Pin {i}', f'{i:06d}')).fetchone()
                if customer is None:
                    continue
                conn.execute('UPDATE customers SET display_name=? WHERE id=? AND station_id=?',
                             (f'Sample Customer {letter}', customer['id'], sid))
                conn.execute('UPDATE delivery_locations SET label=? WHERE id=? AND station_id=?',
                             (legacy, customer['location_id'], sid))
                audit(conn, actor, 'DEMO_HOUSE_CUSTOMER_RELABELED', 'customer', customer['id'],
                      {'location_id': customer['location_id']})
                changes += 1
    print(f'Relabeled {changes} original fictional customer-house pair(s); all IDs, orders, balances, and keys preserved.')


def main():
    p = argparse.ArgumentParser(description='RefillOps fictional local demo')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init', help='Create database schema')
    seed_parser = sub.add_parser('seed', help='Create synthetic actors and data')
    seed_parser.add_argument('--reset', action='store_true', help='Delete local demo database first')
    sub.add_parser('serve', help='Serve only on 127.0.0.1:8000')
    sub.add_parser('upgrade', help='Migrate existing local demo to order numbers and create customer demo keys without reset')
    sub.add_parser('relabel-demo', help='Distinguish Sample Customer and Sample House in existing fictional seed, preserving records')
    args = p.parse_args()
    if args.command == 'init':
        init_db()
        print('Initialized database:', db_path())
    elif args.command == 'seed':
        seed(args.reset)
    elif args.command == 'upgrade':
        upgrade_demo()
    elif args.command == 'relabel-demo':
        relabel_demo()
    elif args.command == 'serve':
        with connect() as conn:
            try:
                columns = {row['name'] for row in conn.execute('PRAGMA table_info(delivery_orders)')}
                alloc = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='order_payment_allocations'").fetchone()
                keys = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_portal_keys'").fetchone()
                if 'order_number' not in columns or not alloc or not keys:
                    raise SystemExit('This local database needs the safe v0.1.4 upgrade. Run: python -m refillops.cli upgrade')
            except sqlite3.DatabaseError:
                raise SystemExit('Initialize fictional data first: python -m refillops.cli seed')
        import uvicorn
        uvicorn.run('refillops.api:app', host='127.0.0.1', port=8000)


if __name__ == '__main__':
    main()
