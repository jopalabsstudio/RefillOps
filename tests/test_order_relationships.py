"""V0.1.4: one reference across owner, rider, customer and payment."""
import sqlite3
import uuid
from pathlib import Path

from refillops.db import init_db

from test_api import request, new_order


def test_seed_has_customer_read_only_keys_and_station_scoped_unique_order_numbers(demo):
    client, headers, path = demo
    rows = request(client, headers, 'owner', 'GET', '/api/orders').json()
    refs = [row['order_number'] for row in rows]
    assert len(refs) == len(set(refs))
    assert all(ref.startswith('RO-') for ref in refs)
    access = __import__('json').loads((path.parent / 'demo_access.json').read_text())
    customer = next(c for c in request(client, headers, 'staff1', 'GET', '/api/customers').json()
                    if c['display_name'] == 'Sample Customer A')
    customer_key = access['customers'][customer['id']]['api_key']
    customer_headers = {'Authorization': 'Bearer '+customer_key}
    assert client.get('/api/me', headers=customer_headers).json()['role'] == 'CUSTOMER'
    visible = client.get('/api/orders', headers=customer_headers)
    assert visible.status_code == 200
    assert visible.json() and all(o['customer_name'] == 'Sample Customer A' for o in visible.json())
    assert all('created_by' not in o and 'rider_id' not in o for o in visible.json())
    other = next(o for o in rows if o['customer_id'] != customer['id'])
    assert client.get('/api/orders/'+other['id'], headers=customer_headers).status_code == 404
    for path_fragment in ['/api/customers', '/api/billing/preview?month=2026-10', '/api/dashboard', '/api/riders', '/api/audit']:
        assert client.get(path_fragment, headers=customer_headers).status_code == 403


def test_one_order_reference_through_delivery_and_order_payment(demo):
    client, headers, path = demo
    order, customer_id, _ = new_order(client, headers, qty=3)
    ref = order['order_number']
    assert ref.startswith('RO-')
    owner = request(client, headers, 'owner', 'GET', '/api/orders/'+order['id']).json()
    assert owner['order_number'] == ref
    assert owner['delivery_status'] == 'ORDERED' and owner['payment_status'] == 'NOT_DUE'
    rider = next(r for r in request(client, headers, 'staff1', 'GET', '/api/riders').json()
                 if r['display_name']=='Demo Rider A')
    assert request(client, headers, 'staff1', 'POST', f"/api/orders/{order['id']}/assign", {'rider_id':rider['id']}).status_code==200
    rider_order = request(client, headers, 'rider1', 'GET', '/api/orders/'+order['id']).json()
    assert rider_order['order_number']==ref and rider_order['delivery_status']=='ORDERED'
    assert request(client, headers, 'rider1', 'POST', f"/api/orders/{order['id']}/dispatch").status_code==200
    assert request(client, headers, 'owner', 'GET', f"/api/orders/{order['id']}").json()['delivery_status']=='OUT_FOR_DELIVERY'
    done = request(client, headers, 'rider1', 'POST', f"/api/orders/{order['id']}/complete",
        {'delivered_qty': 3, 'returned_empties_qty': 2}, {'Idempotency-Key': str(uuid.uuid4())})
    assert done.status_code==200
    completed = request(client, headers, 'owner', 'GET', '/api/orders/'+order['id']).json()
    assert completed['delivery_status']=='DELIVERED'
    assert completed['payment_status']=='UNPAID'
    assert completed['order_number']==ref
    assert completed['order_due_minor']==9000
    customer = request(client, headers, 'staff1', 'GET', '/api/customers/'+customer_id).json()
    assert next(o for o in customer['orders'] if o['id']==order['id'])['payment_status']=='UNPAID'
    # A separate unallocated customer receipt must NOT silently settle this order.
    unallocated = request(client, headers, 'staff2', 'POST', '/api/billing/payments',
        {'customer_id':customer_id,'amount_minor':500,'method':'Cash','reference':'unallocated'})
    assert unallocated.status_code==201
    assert request(client,headers,'owner','GET','/api/orders/'+order['id']).json()['payment_status']=='UNPAID'
    payment = request(client,headers,'staff2','POST','/api/billing/payments',
        {'customer_id':customer_id,'order_id':order['id'],'amount_minor':4000,'method':'Cash','reference':'part 1'})
    assert payment.status_code==201, payment.text
    mid = request(client,headers,'rider1','GET','/api/orders/'+order['id']).json()
    assert mid['payment_status']=='PARTIALLY_PAID'
    assert mid['order_due_minor']==5000
    full = request(client,headers,'staff2','POST','/api/billing/payments',
        {'customer_id':customer_id,'order_id':order['id'],'amount_minor':5000,'method':'Cash','reference':'part 2'})
    assert full.status_code==201
    owner_after = request(client,headers,'owner','GET','/api/orders/'+order['id']).json()
    rider_after = request(client,headers,'rider1','GET','/api/orders/'+order['id']).json()
    assert owner_after['payment_status']==rider_after['payment_status']=='PAID'
    assert owner_after['order_due_minor']==rider_after['order_due_minor']==0
    assert owner_after['order_number']==rider_after['order_number']==ref
    blocked = request(client,headers,'staff2','POST','/api/billing/payments',
        {'customer_id':customer_id,'order_id':order['id'],'amount_minor':100,'method':'Cash','reference':'overpay'})
    assert blocked.status_code==409
    assert request(client,headers,'rider1','POST','/api/billing/payments',
        {'customer_id':customer_id,'order_id':order['id'],'amount_minor':100,'method':'Cash','reference':'forbidden'}).status_code==403
    access = __import__('json').loads((path.parent/'demo_access.json').read_text())
    customer_headers={'Authorization':'Bearer '+access['customers'][customer_id]['api_key']}
    customer_order=client.get('/api/orders/'+order['id'],headers=customer_headers).json()
    assert customer_order['order_number']==ref
    assert customer_order['delivery_status']=='DELIVERED'
    assert customer_order['payment_status']=='PAID'
    assert customer_order['order_due_minor']==0
    assert request(client, headers, 'owner', 'GET', '/api/audit').status_code==200
    assert any(a['action']=='PAYMENT_RECORDED' and a['target_id']==order['id']
               for a in request(client,headers,'owner','GET','/api/audit').json())


def test_order_payment_cannot_attach_to_wrong_customer_or_unfinished_order(demo):
    client, headers, path = demo
    order, cid, _ = new_order(client,headers)
    cid_other = next(c['id'] for c in request(client,headers,'owner','GET','/api/customers').json() if c['id']!=cid)
    body={'customer_id':cid,'order_id':order['id'],'amount_minor':100,'method':'Cash','reference':'ref'}
    assert request(client,headers,'staff2','POST','/api/billing/payments',body).status_code==409
    body['customer_id']=cid_other
    assert request(client,headers,'staff2','POST','/api/billing/payments',body).status_code==422


def test_existing_order_references_migrated_without_changing_ids(tmp_path,monkeypatch):
    from refillops.db import connect
    old_schema = (Path(__file__).parents[1]/'src/refillops/schema.sql').read_text()
    # Simulate a v0.1.3 local DB with old order rows and no readable order_number.
    old_schema=old_schema.replace('order_number TEXT NOT NULL, ','').replace(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_station_number ON delivery_orders(station_id, order_number);','')
    db = tmp_path/'old.sqlite3'
    monkeypatch.setenv('REFILLOPS_DB',str(db))
    with sqlite3.connect(db) as conn:
        conn.executescript(old_schema)
        conn.execute("INSERT INTO stations VALUES ('S','Test',14.65,121.05,1.5,'Asia/Manila','PHP',3000)")
        conn.execute("INSERT INTO users (id,station_id,display_name,role,api_key_hash) VALUES ('U','S','Test User','STAFF','digest')")
        conn.execute("INSERT INTO customers (id,station_id,display_name,opening_containers,created_at) VALUES ('C','S','Customer',0,'2026-10-28T00:00:00Z')")
        conn.execute("INSERT INTO delivery_locations (id,station_id,customer_id,label,lat,lon,created_at) VALUES ('L','S','C','House',14.65,121.05,'2026-10-28T00:00:00Z')")
        for i in range(3):
            conn.execute('''INSERT INTO delivery_orders (id,station_id,customer_id,location_id,requested_qty,unit_price_minor,status,created_by,created_at,updated_at)
                            VALUES (?,?,?,?,?,?,?,?,?,?)''',
                         (f'old{i}','S','C','L',2,3000,'CREATED','U',f'2026-10-28T00:00:0{i}Z',f'2026-10-28T00:00:0{i}Z'))
    init_db()
    init_db() # idempotent, preserve assigned numbers
    with connect() as conn:
        result=conn.execute('SELECT id,order_number FROM delivery_orders ORDER BY created_at').fetchall()
        assert [(r['id'],r['order_number']) for r in result] == [
            ('old0','RO-000001'),('old1','RO-000002'),('old2','RO-000003')]


def test_customer_key_rotation_and_access_scoping(demo):
    import json
    client,headers,path=demo
    customer = next(c for c in request(client,headers,'owner','GET','/api/customers').json()
                    if c['display_name']=='Sample Customer A')
    original=json.loads((path.parent/'demo_access.json').read_text())['customers'][customer['id']]['api_key']
    assert client.get('/api/orders',headers={'Authorization':'Bearer '+original}).status_code==200
    assert request(client,headers,'rider1','POST',f"/api/customers/{customer['id']}/portal-access").status_code==403
    new=request(client,headers,'owner','POST',f"/api/customers/{customer['id']}/portal-access")
    assert new.status_code==201
    new_key=new.json()['api_key']
    assert new_key!=original
    assert client.get('/api/orders',headers={'Authorization':'Bearer '+original}).status_code==401
    assert client.get('/api/orders',headers={'Authorization':'Bearer '+new_key}).status_code==200


def test_upgrade_preserves_actor_keys_and_existing_payments(demo):
    import json
    from refillops.cli import upgrade_demo
    client,headers,path=demo
    access_file=path.parent/'demo_access.json'
    before=json.loads(access_file.read_text())
    with sqlite3.connect(path) as conn:
        orders_before=conn.execute('SELECT id,order_number FROM delivery_orders ORDER BY id').fetchall()
        count_before=conn.execute('SELECT COUNT(*) FROM account_entries').fetchone()[0]
    upgrade_demo()
    upgrade_demo()
    after=json.loads(access_file.read_text())
    assert before['actors']==after['actors']
    assert before['customers']==after['customers']
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT id,order_number FROM delivery_orders ORDER BY id').fetchall()==orders_before
        assert conn.execute('SELECT COUNT(*) FROM account_entries').fetchone()[0]==count_before
