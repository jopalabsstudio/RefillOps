"""Station-scoped commands and queries. Financial and container writes are transactional."""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from refillops import domain
from refillops.db import connect, transaction, one, many


def uid() -> str:
    return str(uuid.uuid4())


class AppError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def must(row, what='Record'):
    if row is None:
        raise AppError(404, f'{what} not found in authorized station')
    return row


def lookup(conn, table, id, station_id):
    if table not in {'customers', 'delivery_locations', 'delivery_orders', 'users', 'exceptions', 'invoices'}:
        raise ValueError('Unsupported lookup table')
    return must(one(conn, f'SELECT * FROM {table} WHERE id=? AND station_id=?', (id, station_id)), table)


def audit(conn, actor, action, entity, entity_id, metadata=None):
    conn.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)',
                 (uid(), actor['station_id'], actor['id'], action, entity, entity_id,
                  json.dumps(metadata or {}, sort_keys=True), domain.utc_now()))


def emit_exception(conn, actor, entity, entity_id, kind, severity='MEDIUM'):
    eid = uid()
    conn.execute('INSERT INTO exceptions (id, station_id, entity_type, entity_id, kind, severity, state, created_at) VALUES (?,?,?,?,?,?,?,?)',
                 (eid, actor['station_id'], entity, entity_id, kind, severity, 'OPEN', domain.utc_now()))
    return eid


def station(actor):
    with connect() as conn:
        return must(one(conn, 'SELECT * FROM stations WHERE id=?', (actor['station_id'],)), 'station')


def list_customers(actor):
    """Customer financial positions and live order counters are separate measures."""
    with connect() as conn:
        return many(conn, '''SELECT c.*, c.opening_containers + COALESCE((SELECT SUM(m.delta) FROM container_movements m
            WHERE m.station_id=c.station_id AND m.customer_id=c.id), 0) AS container_position,
            COALESCE((SELECT SUM(e.amount_minor) FROM account_entries e
            WHERE e.station_id=c.station_id AND e.customer_id=c.id), 0) AS amount_due_minor,
            COALESCE((SELECT COUNT(*) FROM delivery_locations l
                WHERE l.station_id=c.station_id AND l.customer_id=c.id), 0) AS house_count,
            (SELECT GROUP_CONCAT(l.label, ', ') FROM delivery_locations l
                WHERE l.station_id=c.station_id AND l.customer_id=c.id) AS house_labels,
            COALESCE(os.total_orders, 0) AS total_orders,
            COALESCE(os.active_orders, 0) AS active_orders,
            COALESCE(os.completed_orders, 0) AS completed_orders,
            COALESCE(os.failed_orders, 0) AS failed_orders
            FROM customers c
            LEFT JOIN (
                SELECT station_id, customer_id, COUNT(*) AS total_orders,
                SUM(CASE WHEN status IN ('CREATED','ASSIGNED','OUT_FOR_DELIVERY') THEN 1 ELSE 0 END) AS active_orders,
                SUM(CASE WHEN status='COMPLETED' THEN 1 ELSE 0 END) AS completed_orders,
                SUM(CASE WHEN status='DELIVERY_FAILED' THEN 1 ELSE 0 END) AS failed_orders
                FROM delivery_orders WHERE station_id=? GROUP BY station_id, customer_id
            ) os ON os.station_id=c.station_id AND os.customer_id=c.id
            WHERE c.station_id=? ORDER BY c.display_name''', (actor['station_id'], actor['station_id']))


def get_customer(actor, id):
    with connect() as conn:
        c = lookup(conn, 'customers', id, actor['station_id'])
        c['locations'] = many(conn, 'SELECT * FROM delivery_locations WHERE station_id=? AND customer_id=?', (actor['station_id'], id))
        c['container_position'] = c['opening_containers'] + (one(conn, 'SELECT COALESCE(SUM(delta),0) AS total FROM container_movements WHERE station_id=? AND customer_id=?', (actor['station_id'], id)))['total']
        c['account_entries'] = many(conn, '''SELECT e.*, o.order_number
            FROM account_entries e
            LEFT JOIN order_payment_allocations pa ON pa.payment_entry_id=e.id AND pa.station_id=e.station_id
            LEFT JOIN delivery_orders o ON o.id=COALESCE(e.order_id,pa.order_id) AND o.station_id=e.station_id
            WHERE e.station_id=? AND e.customer_id=? ORDER BY e.created_at''',
            (actor['station_id'], id))
        c['amount_due_minor'] = sum(r['amount_minor'] for r in c['account_entries'])
        # Every created order appears immediately, without fabricating a delivery or charge.
        # Station scoping is explicit across all joined records.
        c['orders'] = _linked_order_rows(conn, actor, customer_id=id)
        return c


def create_customer(actor, display_name, opening_containers=0):
    display_name = display_name.strip()
    if not display_name or opening_containers < 0:
        raise AppError(422, 'Invalid customer name or opening container count')
    id, now = uid(), domain.utc_now()
    with transaction() as conn:
        conn.execute('INSERT INTO customers (id, station_id, display_name, opening_containers, created_at) VALUES (?,?,?,?,?)',
                     (id, actor['station_id'], display_name, opening_containers, now))
        audit(conn, actor, 'CUSTOMER_CREATED', 'customer', id)
    return get_customer(actor, id)


def create_location(actor, customer_id, label, lat, lon):
    with transaction() as conn:
        lookup(conn, 'customers', customer_id, actor['station_id'])
        st = must(one(conn, 'SELECT * FROM stations WHERE id=?', (actor['station_id'],)))
        distance = domain.distance_km(st['center_lat'], st['center_lon'], lat, lon)
        if distance > st['radius_km']:
            raise AppError(422, f'Outside straight-line {st["radius_km"]:g} km service radius ({distance:.2f} km)')
        id = uid()
        # Alias is a location reference, not a reusable physical gallon serial number.
        alias = f'{secrets.randbelow(100_000_000):08d}'
        conn.execute('INSERT INTO delivery_locations (id,station_id,customer_id,label,lat,lon,numeric_alias,created_at) VALUES (?,?,?,?,?,?,?,?)',
                     (id, actor['station_id'], customer_id, label.strip() or 'Home', lat, lon, alias, domain.utc_now()))
        audit(conn, actor, 'LOCATION_CREATED', 'location', id, {'radius_distance_km': round(distance, 3)})
        return one(conn, 'SELECT * FROM delivery_locations WHERE id=? AND station_id=?', (id, actor['station_id']))


def create_token(actor, location_id):
    # Return the plaintext opaque token once. Database keeps only a digest.
    plain = secrets.token_urlsafe(24)
    with transaction() as conn:
        loc = lookup(conn, 'delivery_locations', location_id, actor['station_id'])
        if not loc['active']:
            raise AppError(409, 'Location is inactive')
        tok_id = uid()
        conn.execute('INSERT INTO location_tokens VALUES (?,?,?,?,?,NULL)',
                     (tok_id, actor['station_id'], location_id, hashlib.sha256(plain.encode()).hexdigest(), domain.utc_now()))
        audit(conn, actor, 'TOKEN_CREATED', 'location', location_id, {'token_id': tok_id})
    return {'id': tok_id, 'location_id': location_id, 'token': plain,
            'note': 'Keep this locally generated token private; it identifies a destination, not a gallon'}


def revoke_token(actor, token_id):
    with transaction() as conn:
        tok = must(one(conn, 'SELECT * FROM location_tokens WHERE id=? AND station_id=?', (token_id, actor['station_id'])), 'token')
        if tok['revoked_at'] is None:
            conn.execute('UPDATE location_tokens SET revoked_at=? WHERE id=?', (domain.utc_now(), token_id))
            audit(conn, actor, 'TOKEN_REVOKED', 'location', tok['location_id'], {'token_id': token_id})
    return {'revoked': True, 'token_id': token_id}


def resolve_token(actor, token):
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connect() as conn:
        loc = must(one(conn, '''SELECT l.* FROM location_tokens t JOIN delivery_locations l
            ON l.id=t.location_id AND l.station_id=t.station_id
            WHERE t.token_hash=? AND t.station_id=? AND t.revoked_at IS NULL AND l.active=1''',
            (digest, actor['station_id'])), 'valid destination token')
        if actor['role'] == 'RIDER':
            available = one(conn, '''SELECT id FROM delivery_orders WHERE station_id=? AND location_id=?
                AND rider_id=? AND status IN ('ASSIGNED','OUT_FOR_DELIVERY')''',
                (actor['station_id'], loc['id'], actor['id']))
            if not available:
                raise AppError(403, 'Rider may resolve destinations only for assigned active orders')
        return loc


def resolve_alias(actor, alias):
    """Numeric alias is a lookup hint, not a login credential or gallon identifier."""
    if not alias.isdigit() or len(alias) > 12:
        raise AppError(422, 'Enter a numeric destination alias')
    with connect() as conn:
        loc = must(one(conn, '''SELECT * FROM delivery_locations WHERE station_id=?
               AND numeric_alias=? AND active=1''',
               (actor['station_id'], alias)), 'destination alias')
        if actor['role'] == 'RIDER':
            assigned = one(conn, '''SELECT id FROM delivery_orders WHERE station_id=? AND location_id=?
                AND rider_id=? AND status IN ('ASSIGNED','OUT_FOR_DELIVERY')''',
                (actor['station_id'], loc['id'], actor['id']))
            if not assigned:
                raise AppError(403, 'Rider may resolve destinations only for assigned active orders')
        loc['customer_name'] = must(one(conn, 'SELECT display_name FROM customers WHERE id=? AND station_id=?',
            (loc['customer_id'], actor['station_id'])), 'customer')['display_name']
        return loc


def create_order(actor, customer_id, location_id, requested_qty):
    if requested_qty <= 0:
        raise AppError(422, 'Requested quantity must be positive')
    now, oid = domain.utc_now(), uid()
    with transaction() as conn:
        customer = lookup(conn, 'customers', customer_id, actor['station_id'])
        location = lookup(conn, 'delivery_locations', location_id, actor['station_id'])
        if location['customer_id'] != customer['id'] or not customer['active'] or not location['active']:
            raise AppError(422, 'Customer and active destination do not match')
        st = must(one(conn, 'SELECT * FROM stations WHERE id=?', (actor['station_id'],)))
        # The station-scoped human reference never changes; UUID remains the internal FK.
        previous = one(conn, """SELECT COALESCE(MAX(CAST(SUBSTR(order_number, 4) AS INTEGER)),0) AS n
                            FROM delivery_orders WHERE station_id=?""", (actor['station_id'],))
        order_number = f"RO-{previous['n'] + 1:06d}"
        conn.execute('''INSERT INTO delivery_orders
            (id,station_id,order_number,customer_id,location_id,requested_qty,unit_price_minor,status,created_by,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            (oid, actor['station_id'], order_number, customer_id, location_id, requested_qty,
             st['unit_price_minor'], 'CREATED', actor['id'], now, now))
        audit(conn, actor, 'ORDER_CREATED', 'order', oid, {'order_number': order_number, 'requested_qty': requested_qty, 'price_minor': st['unit_price_minor']})
        return one(conn, 'SELECT * FROM delivery_orders WHERE id=?', (oid,))


def issue_customer_access(actor, customer_id):
    """Local-only read-only customer key, explicitly issued once for demo accounts.

    Rotating invalidates the previous key. Never commit or publish the returned key.
    """
    with transaction() as conn:
        c = lookup(conn, 'customers', customer_id, actor['station_id'])
        plain = secrets.token_urlsafe(36)
        conn.execute('''INSERT INTO customer_portal_keys(customer_id,station_id,key_hash,created_at)
           VALUES (?,?,?,?) ON CONFLICT(customer_id) DO UPDATE SET
           key_hash=excluded.key_hash, created_at=excluded.created_at''',
            (customer_id, actor['station_id'], hashlib.sha256(plain.encode()).hexdigest(), domain.utc_now()))
        audit(conn, actor, 'CUSTOMER_ACCESS_ISSUED', 'customer', customer_id)
        return {'customer_id': customer_id, 'customer_name': c['display_name'],
                'api_key': plain, 'note': 'Local demo only. This rotates earlier customer access and grants read-only access to this customer.'}


def _public_status(raw):
    return {'CREATED': 'ORDERED', 'ASSIGNED': 'ORDERED',
            'OUT_FOR_DELIVERY': 'OUT_FOR_DELIVERY', 'COMPLETED': 'DELIVERED',
            'DELIVERY_FAILED': 'DELIVERY_FAILED', 'CANCELLED': 'CANCELLED'}[raw]


def _linked_order_rows(conn, actor, customer_id=None, order_id=None):
    """One order view shared by owner, assigned rider and customer.

    Payment state is derived from posted charges and specific order allocations,
    never inferred from the aggregate customer balance.
    """
    sql = '''SELECT o.*, c.display_name AS customer_name, l.label AS location_label,
           u.display_name AS rider_name, dc.delivered_qty, dc.returned_empties_qty,
           COALESCE(ch.amount_minor,0) AS charge_minor,
           COALESCE(pa.amount_minor,0) AS paid_minor
           FROM delivery_orders o
           JOIN customers c ON c.id=o.customer_id AND c.station_id=o.station_id
           JOIN delivery_locations l ON l.id=o.location_id AND l.station_id=o.station_id
           LEFT JOIN users u ON u.id=o.rider_id AND u.station_id=o.station_id
           LEFT JOIN delivery_confirmations dc ON dc.order_id=o.id AND dc.station_id=o.station_id
           LEFT JOIN account_entries ch ON ch.order_id=o.id AND ch.station_id=o.station_id AND ch.kind='CHARGE'
           LEFT JOIN (SELECT a.order_id, a.station_id, SUM(a.allocated_minor) AS amount_minor
                      FROM order_payment_allocations a GROUP BY a.station_id,a.order_id) pa
                      ON pa.order_id=o.id AND pa.station_id=o.station_id
           WHERE o.station_id=?'''
    args = [actor['station_id']]
    if actor['role'] == 'RIDER':
        sql += ' AND o.rider_id=?'
        args.append(actor['id'])
    elif actor['role'] == 'CUSTOMER':
        sql += ' AND o.customer_id=?'
        args.append(actor['customer_id'])
    if customer_id:
        sql += ' AND o.customer_id=?'
        args.append(customer_id)
    if order_id:
        sql += ' AND o.id=?'
        args.append(order_id)
    sql += ' ORDER BY o.created_at DESC, o.rowid DESC'
    result = many(conn, sql, args)
    for row in result:
        row['delivery_status'] = _public_status(row['status'])
        row['payment_status'] = ('NOT_DUE' if row['status'] != 'COMPLETED' else
                                 'PAID' if row['charge_minor'] > 0 and row['paid_minor'] >= row['charge_minor'] else
                                 'PARTIALLY_PAID' if row['paid_minor'] > 0 else 'UNPAID')
        row['order_due_minor'] = max(0, row['charge_minor'] - row['paid_minor'])
        if actor['role'] == 'CUSTOMER':
            # Customer portal gets only customer-facing fields.
            fields = ('id','order_number','customer_name','location_label','requested_qty',
                      'unit_price_minor','created_at','updated_at','delivery_status',
                      'payment_status','charge_minor','paid_minor','order_due_minor',
                      'delivered_qty','returned_empties_qty','rider_name')
            for key in list(row):
                if key not in fields:
                    del row[key]
    return result


def orders(actor):
    with connect() as conn:
        return _linked_order_rows(conn, actor)


def get_order(actor, id):
    with connect() as conn:
        result = _linked_order_rows(conn, actor, order_id=id)
        order = must(result[0] if result else None, 'Order')
        if actor['role'] != 'CUSTOMER':
            order['confirmation'] = one(conn, 'SELECT * FROM delivery_confirmations WHERE station_id=? AND order_id=?', (actor['station_id'],id))
        return order


def _transition(conn, actor, order_id, target):
    o = lookup(conn, 'delivery_orders', order_id, actor['station_id'])
    if not domain.can_transition(o['status'], target):
        raise AppError(409, f'Invalid transition: {o["status"]} -> {target}')
    conn.execute('UPDATE delivery_orders SET status=?,updated_at=? WHERE id=? AND station_id=?',
                 (target, domain.utc_now(), order_id, actor['station_id']))
    return o


def assign_order(actor, order_id, rider_id):
    with transaction() as conn:
        rider = lookup(conn, 'users', rider_id, actor['station_id'])
        if rider['role'] != 'RIDER' or not rider['active']:
            raise AppError(422, 'Assignee must be an active rider')
        _transition(conn, actor, order_id, 'ASSIGNED')
        conn.execute('UPDATE delivery_orders SET rider_id=? WHERE id=? AND station_id=?', (rider_id, order_id, actor['station_id']))
        audit(conn, actor, 'ORDER_ASSIGNED', 'order', order_id, {'rider_id': rider_id})
    return get_order(actor, order_id)


def dispatch_order(actor, order_id):
    with transaction() as conn:
        o = lookup(conn, 'delivery_orders', order_id, actor['station_id'])
        if o['rider_id'] != actor['id']:
            raise AppError(403, 'Only assigned rider may dispatch')
        _transition(conn, actor, order_id, 'OUT_FOR_DELIVERY')
        audit(conn, actor, 'ORDER_DISPATCHED', 'order', order_id)
    return get_order(actor, order_id)


def cancel_order(actor, order_id):
    with transaction() as conn:
        _transition(conn, actor, order_id, 'CANCELLED')
        audit(conn, actor, 'ORDER_CANCELLED', 'order', order_id)
    return get_order(actor, order_id)


def fail_order(actor, order_id, reason):
    if not reason.strip():
        raise AppError(422, 'Failure reason is required')
    with transaction() as conn:
        o = lookup(conn, 'delivery_orders', order_id, actor['station_id'])
        if o['rider_id'] != actor['id']:
            raise AppError(403, 'Only assigned rider may fail a delivery')
        _transition(conn, actor, order_id, 'DELIVERY_FAILED')
        conn.execute('UPDATE delivery_orders SET failure_reason=? WHERE id=? AND station_id=?', (reason.strip(), order_id, actor['station_id']))
        emit_exception(conn, actor, 'order', order_id, 'DELIVERY_FAILED')
        audit(conn, actor, 'ORDER_FAILED', 'order', order_id, {'reason': reason.strip()})
    return get_order(actor, order_id)


def complete_order(actor, order_id, delivered_qty, returned_empties_qty, key):
    if delivered_qty <= 0 or returned_empties_qty < 0 or not key or len(key) > 128:
        raise AppError(422, 'Invalid completion quantities or idempotency key')
    payload = {'order_id': order_id, 'delivered_qty': delivered_qty, 'returned_empties_qty': returned_empties_qty}
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with transaction() as conn:
        prior = one(conn, '''SELECT * FROM idempotency_records WHERE station_id=? AND command='COMPLETE_ORDER' AND request_key=?''',
                    (actor['station_id'], key))
        if prior:
            if prior['fingerprint'] != fingerprint:
                raise AppError(409, 'Same idempotency key used with different payload')
            # Replaying does not grant new access when an order is reassigned.
            prev_order = lookup(conn, 'delivery_orders', order_id, actor['station_id'])
            if prev_order['rider_id'] != actor['id']:
                raise AppError(403, 'Only assigned rider may retry completion')
            return json.loads(prior['result_json'])
        o = lookup(conn, 'delivery_orders', order_id, actor['station_id'])
        if o['rider_id'] != actor['id']:
            raise AppError(403, 'Only assigned rider may confirm')
        if delivered_qty > o['requested_qty']:
            raise AppError(422, 'Delivered quantity cannot exceed requested quantity')
        _transition(conn, actor, order_id, 'COMPLETED')
        now = domain.utc_now()
        conf_id = uid()
        conn.execute('INSERT INTO delivery_confirmations VALUES (?,?,?,?,?,?,?,?)',
                     (conf_id, order_id, actor['station_id'], delivered_qty, returned_empties_qty, actor['id'], now, key))
        for kind, delta in [('FULL_DELIVERED', delivered_qty), ('EMPTY_RETURNED', -returned_empties_qty)]:
            if delta != 0:
                conn.execute('INSERT INTO container_movements VALUES (?,?,?,?,?,?,?)',
                             (uid(), actor['station_id'], o['customer_id'], order_id, kind, delta, now))
        amount = domain.charge_minor(delivered_qty, o['unit_price_minor'])
        if amount > 0:
            conn.execute('''INSERT INTO account_entries
                (id,station_id,customer_id,order_id,kind,amount_minor,created_at)
                VALUES (?,?,?,?,?,?,?)''',
                (uid(), actor['station_id'], o['customer_id'], order_id, 'CHARGE', amount, now))
        cust = lookup(conn, 'customers', o['customer_id'], actor['station_id'])
        movements = many(conn, 'SELECT delta FROM container_movements WHERE station_id=? AND customer_id=?',
                         (actor['station_id'], o['customer_id']))
        position = domain.container_position(cust['opening_containers'], [m['delta'] for m in movements])
        if position < 0:
            emit_exception(conn, actor, 'order', order_id, 'NEGATIVE_CONTAINER_POSITION', 'HIGH')
        audit(conn, actor, 'ORDER_COMPLETED', 'order', order_id,
              {'delivered_qty': delivered_qty, 'returned_empties_qty': returned_empties_qty, 'charge_minor': amount})
        outcome = {'order_id': order_id, 'order_number': o['order_number'], 'status': 'COMPLETED', 'delivered_qty': delivered_qty,
                   'returned_empties_qty': returned_empties_qty, 'charge_minor': amount,
                   'container_position': position, 'confirmed_at': now}
        conn.execute('INSERT INTO idempotency_records VALUES (?,?,?,?,?,?)',
                     (actor['station_id'], 'COMPLETE_ORDER', key, fingerprint, json.dumps(outcome, sort_keys=True), now))
        return outcome


def post_payment(actor, customer_id, amount_minor, method, reference, order_id=None):
    """Post customer receipt, optionally allocating to a completed order.

    Legacy unallocated receipts are not guessed into particular orders.
    Multiple partial receipts can pay one order. Each receipt can settle only one
    order in this demo; cross-order allocations are left for later validation.
    """
    if amount_minor <= 0 or not method.strip():
        raise AppError(422, 'Payment amount and method required')
    with transaction() as conn:
        lookup(conn, 'customers', customer_id, actor['station_id'])
        if order_id:
            row = must(one(conn, '''SELECT o.customer_id, o.status, ch.amount_minor AS charge_minor,
                  COALESCE((SELECT SUM(a.allocated_minor) FROM order_payment_allocations a
                            WHERE a.station_id=o.station_id AND a.order_id=o.id),0) AS paid_minor
                  FROM delivery_orders o
                  LEFT JOIN account_entries ch ON ch.order_id=o.id AND ch.station_id=o.station_id AND ch.kind='CHARGE'
                  WHERE o.station_id=? AND o.id=?''', (actor['station_id'], order_id)), 'Order')
            if row['customer_id'] != customer_id:
                raise AppError(422, 'Order does not belong to the selected customer')
            if row['status'] != 'COMPLETED' or not row['charge_minor']:
                raise AppError(409, 'Only delivered orders with a charge can be paid')
            if amount_minor > row['charge_minor'] - row['paid_minor']:
                raise AppError(409, 'Payment exceeds outstanding amount for this order')
        id = uid()
        conn.execute('''INSERT INTO account_entries
            (id,station_id,customer_id,kind,amount_minor,reason,reference,created_at)
            VALUES (?,?,?,?,?,?,?,?)''',
            (id, actor['station_id'], customer_id, 'PAYMENT', -amount_minor, method.strip(), reference, domain.utc_now()))
        if order_id:
            conn.execute('''INSERT INTO order_payment_allocations
                (payment_entry_id,station_id,order_id,allocated_minor) VALUES (?,?,?,?)''',
                (id, actor['station_id'], order_id, amount_minor))
        audit(conn, actor, 'PAYMENT_RECORDED', 'order' if order_id else 'account_entry', order_id or id,
              {'payment_entry_id': id, 'amount_minor': amount_minor, 'method': method.strip(),
               'allocation': 'ORDER' if order_id else 'UNALLOCATED'})
        ref = lookup(conn, 'delivery_orders', order_id, actor['station_id'])['order_number'] if order_id else None
        return {'id': id, 'customer_id': customer_id, 'order_id': order_id, 'order_number': ref, 'amount_minor': -amount_minor}


def _month_ok(month):
    try:
        if len(month) != 7:
            raise ValueError()
        datetime.strptime(month, '%Y-%m')
    except ValueError:
        raise AppError(422, 'Month must be YYYY-MM')


def _eligible(conn, actor, customer_id, month):
    timezone_name = station(actor)['timezone']
    charges = many(conn, '''SELECT e.* FROM account_entries e LEFT JOIN invoice_lines il ON il.account_entry_id=e.id
      WHERE e.station_id=? AND e.customer_id=? AND e.kind='CHARGE' AND il.id IS NULL ORDER BY e.created_at''',
      (actor['station_id'], customer_id))
    return [e for e in charges if domain.station_month(e['created_at'], timezone_name) == month]


def billing_preview(actor, month):
    _month_ok(month)
    with connect() as conn:
        customers = many(conn, 'SELECT id, display_name FROM customers WHERE station_id=? ORDER BY display_name', (actor['station_id'],))
        for c in customers:
            candidates = _eligible(conn, actor, c['id'], month)
            c['eligible_charges'] = len(candidates)
            c['uninvoiced_total_minor'] = sum(e['amount_minor'] for e in candidates)
            c['amount_due_minor'] = one(conn, 'SELECT COALESCE(SUM(amount_minor),0) AS s FROM account_entries WHERE station_id=? AND customer_id=?', (actor['station_id'], c['id']))['s']
        invoices = many(conn, 'SELECT * FROM invoices WHERE station_id=? AND month=? ORDER BY issued_at DESC', (actor['station_id'], month))
        return {'month': month, 'customers': customers, 'invoices': invoices,
                'note': 'Eligible charges use station-local month; amount due includes recorded payments across all time'}


def issue_invoice(actor, customer_id, month):
    _month_ok(month)
    with transaction() as conn:
        lookup(conn, 'customers', customer_id, actor['station_id'])
        lines = _eligible(conn, actor, customer_id, month)
        if not lines:
            raise AppError(409, 'No eligible uninvoiced charges for this customer and month')
        invoice_id, now = uid(), domain.utc_now()
        total = sum(line['amount_minor'] for line in lines)
        conn.execute('''INSERT INTO invoices (id,station_id,customer_id,month,status,total_minor,issued_at)
            VALUES (?,?,?,?,?,?,?)''', (invoice_id, actor['station_id'], customer_id, month, 'ISSUED', total, now))
        for line in lines:
            conn.execute('INSERT INTO invoice_lines VALUES (?,?,?,?,?)',
                         (uid(), actor['station_id'], invoice_id, line['id'], line['amount_minor']))
        audit(conn, actor, 'INVOICE_ISSUED', 'invoice', invoice_id, {'charge_count': len(lines), 'total_minor': total})
        return {'id': invoice_id, 'month': month, 'customer_id': customer_id,
                'total_minor': total, 'line_count': len(lines), 'issued_at': now}


def post_owner_adjustment(actor, customer_id, reason, container_delta=0, amount_delta_minor=0):
    """Append-only owner correction, never rewriting past deliveries, charges, or receipts."""
    if not reason.strip() or (container_delta == 0 and amount_delta_minor == 0):
        raise AppError(422, 'Nonempty reason and at least one nonzero delta are required')
    if abs(container_delta) > 100000 or abs(amount_delta_minor) > 100_000_000:
        raise AppError(422, 'Correction exceeds local demo safety limits')
    now, correction_id = domain.utc_now(), uid()
    with transaction() as conn:
        customer = lookup(conn, 'customers', customer_id, actor['station_id'])
        if container_delta:
            conn.execute('''INSERT INTO container_movements
                (id,station_id,customer_id,kind,delta,created_at) VALUES (?,?,?,?,?,?)''',
                (uid(), actor['station_id'], customer_id, 'ADJUSTMENT', container_delta, now))
        if amount_delta_minor:
            conn.execute('''INSERT INTO account_entries
                (id,station_id,customer_id,kind,amount_minor,reason,reference,created_at)
                VALUES (?,?,?,?,?,?,?,?)''',
                (uid(), actor['station_id'], customer_id, 'ADJUSTMENT', amount_delta_minor,
                 reason.strip(), correction_id, now))
        position = customer['opening_containers'] + one(conn, '''SELECT COALESCE(SUM(delta),0) AS total
                 FROM container_movements WHERE station_id=? AND customer_id=?''',
                 (actor['station_id'], customer_id))['total']
        if position < 0:
            emit_exception(conn, actor, 'customer', customer_id, 'NEGATIVE_CONTAINER_POSITION', 'HIGH')
        audit(conn, actor, 'OWNER_ADJUSTMENT', 'customer', customer_id,
              {'correction_id': correction_id, 'reason': reason.strip(),
               'container_delta': container_delta, 'amount_delta_minor': amount_delta_minor})
    return {'correction_id': correction_id, 'customer_id': customer_id,
            'container_delta': container_delta, 'amount_delta_minor': amount_delta_minor,
            'container_position': position}


def invoice_detail(actor, invoice_id):
    with connect() as conn:
        inv = lookup(conn, 'invoices', invoice_id, actor['station_id'])
        inv['customer_name'] = lookup(conn, 'customers', inv['customer_id'], actor['station_id'])['display_name']
        inv['lines'] = many(conn, '''SELECT il.amount_minor, ae.id AS entry_id, ae.order_id,
             o.order_number, o.requested_qty, dc.delivered_qty, o.unit_price_minor
             FROM invoice_lines il
             JOIN account_entries ae ON ae.id=il.account_entry_id AND ae.station_id=il.station_id
             LEFT JOIN delivery_orders o ON o.id=ae.order_id AND o.station_id=ae.station_id
             LEFT JOIN delivery_confirmations dc ON dc.order_id=o.id AND dc.station_id=o.station_id
             WHERE il.station_id=? AND il.invoice_id=? ORDER BY ae.created_at''',
             (actor['station_id'], invoice_id))
        return inv


def dashboard(actor):
    with connect() as conn:
        states = many(conn, 'SELECT status, COUNT(*) AS count FROM delivery_orders WHERE station_id=? GROUP BY status', (actor['station_id'],))
        st = station(actor)
        all_confirmations = many(conn, 'SELECT confirmed_at FROM delivery_confirmations WHERE station_id=?', (actor['station_id'],))
        current_day = datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo(st['timezone'])).date().isoformat()
        completed_today = sum(1 for r in all_confirmations if datetime.fromisoformat(r['confirmed_at']).astimezone(__import__('zoneinfo').ZoneInfo(st['timezone'])).date().isoformat() == current_day)
        amounts = one(conn, 'SELECT COALESCE(SUM(amount_minor),0) AS total FROM account_entries WHERE station_id=?', (actor['station_id'],))
        open_ex = many(conn, '''SELECT e.*, o.order_number FROM exceptions e
            LEFT JOIN delivery_orders o ON e.entity_type='order' AND e.entity_id=o.id AND e.station_id=o.station_id
            WHERE e.station_id=? AND e.state=? ORDER BY e.created_at DESC''', (actor['station_id'], 'OPEN'))
        return {'orders_by_status': {r['status']: r['count'] for r in states},
                'completed_today': completed_today, 'receivables_minor': amounts['total'],
                'open_exceptions': open_ex,
                'note': 'Owner overview; counters are derived from committed local demo records'}


def list_exceptions(actor):
    with connect() as conn:
        return many(conn, '''SELECT e.*, o.order_number FROM exceptions e
            LEFT JOIN delivery_orders o ON e.entity_type='order' AND e.entity_id=o.id AND e.station_id=o.station_id
            WHERE e.station_id=? ORDER BY e.created_at DESC''', (actor['station_id'],))


def review_exception(actor, id, note):
    if not note.strip():
        raise AppError(422, 'Review note is required')
    with transaction() as conn:
        e = lookup(conn, 'exceptions', id, actor['station_id'])
        if e['state'] != 'OPEN':
            raise AppError(409, 'Exception already reviewed')
        conn.execute('UPDATE exceptions SET state=?, note=?, reviewed_at=?, reviewed_by=? WHERE id=? AND station_id=?',
                     ('REVIEWED', note.strip(), domain.utc_now(), actor['id'], id, actor['station_id']))
        audit(conn, actor, 'EXCEPTION_REVIEWED', 'exception', id, {'note': note.strip()})
    return {'id': id, 'state': 'REVIEWED'}


def audit_history(actor):
    with connect() as conn:
        return many(conn, '''SELECT a.*, u.display_name AS actor_name, o.order_number FROM audit_events a
            JOIN users u ON a.actor_id=u.id AND a.station_id=u.station_id
            LEFT JOIN delivery_orders o ON a.target_type='order' AND a.target_id=o.id AND a.station_id=o.station_id
            WHERE a.station_id=? ORDER BY a.created_at DESC LIMIT 200''', (actor['station_id'],))


def riders(actor):
    with connect() as conn:
        return many(conn, 'SELECT id, display_name, role FROM users WHERE station_id=? AND role=? AND active=1', (actor['station_id'], 'RIDER'))
