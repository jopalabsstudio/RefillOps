import json
import sqlite3
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo


def request(client, headers, role, method, path, json_body=None, extra=None):
    return client.request(method, path, json=json_body, headers={**headers(role), **(extra or {})})


def new_order(client, headers, qty=3):
    customers = request(client, headers, 'staff1', 'GET', '/api/customers').json()
    customer_id = customers[-1]['id']
    detail = request(client, headers, 'staff1', 'GET', '/api/customers/'+customer_id).json()
    location_id = detail['locations'][0]['id']
    order = request(client, headers, 'staff1', 'POST', '/api/orders',
                    {'customer_id':customer_id, 'location_id':location_id, 'requested_qty':qty})
    assert order.status_code == 201, order.text
    return order.json(), customer_id, location_id


def prepare_ride(client, headers):
    order, customer_id, location_id = new_order(client, headers)
    riders = request(client, headers, 'staff1', 'GET', '/api/riders').json()
    rider = next(r for r in riders if r['display_name'] == 'Demo Rider A')
    a = request(client, headers, 'staff1', 'POST', f"/api/orders/{order['id']}/assign", {'rider_id':rider['id']})
    assert a.status_code==200, a.text
    d = request(client, headers, 'rider1', 'POST', f"/api/orders/{order['id']}/dispatch")
    assert d.status_code == 200, d.text
    return order, customer_id, location_id


def test_health_and_auth(demo):
    client, headers, _ = demo
    assert client.get('/api/health').json()['status']=='local-demo'
    assert client.get('/api/dashboard').status_code==401
    assert request(client,headers,'rider1','GET','/api/dashboard').status_code==403
    assert request(client,headers,'staff1','POST','/api/billing/invoices',{'customer_id':'x','month':'2026-10'}).status_code==403
    assert request(client,headers,'owner','GET','/api/dashboard').status_code==200


def test_customer_location_token_and_revocation(demo):
    client, headers, _ = demo
    cust = request(client,headers,'staff1','POST','/api/customers',{'display_name':'Synthetic Customer', 'opening_containers':0})
    assert cust.status_code==201
    cid = cust.json()['id']
    far = request(client,headers,'staff1','POST','/api/locations',{'customer_id':cid,'label':'Far','lat':14.80,'lon':121.05})
    assert far.status_code == 422
    loc = request(client,headers,'staff1','POST','/api/locations',{'customer_id':cid,'label':'Fake pin','lat':14.6502,'lon':121.0502})
    assert loc.status_code==201
    lid = loc.json()['id']
    tok = request(client,headers,'staff1','POST',f'/api/locations/{lid}/tokens').json()
    assert cid not in tok['token']
    assert request(client,headers,'rider1','POST','/api/locations/tokens/resolve',{'token':tok['token']}).status_code==403
    assert request(client,headers,'staff1','POST','/api/locations/tokens/resolve',{'token':tok['token']}).json()['id']==lid
    assert request(client,headers,'staff1','POST',f"/api/locations/tokens/{tok['id']}/revoke").status_code==200
    assert request(client,headers,'staff1','POST','/api/locations/tokens/resolve',{'token':tok['token']}).status_code==404


def test_full_order_confirm_idempotent_and_charged_once(demo):
    client,headers,path=demo
    o,cid,lid=prepare_ride(client,headers)
    key=str(uuid.uuid4())
    url=f"/api/orders/{o['id']}/complete"
    data={'delivered_qty':3,'returned_empties_qty':2}
    completed=request(client,headers,'rider1','POST',url,data,{'Idempotency-Key':key})
    assert completed.status_code==200, completed.text
    assert completed.json()['charge_minor']==3*o['unit_price_minor']
    retry=request(client,headers,'rider1','POST',url,data,{'Idempotency-Key':key})
    assert retry.status_code==200 and retry.json()==completed.json()
    assert request(client,headers,'rider1','POST',url,{'delivered_qty':2,'returned_empties_qty':2},{'Idempotency-Key':key}).status_code==409
    assert request(client,headers,'rider1','POST',url,data,{'Idempotency-Key':str(uuid.uuid4())}).status_code==409
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM delivery_confirmations WHERE order_id=?',(o['id'],)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM account_entries WHERE order_id=?',(o['id'],)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM container_movements WHERE order_id=?',(o['id'],)).fetchone()[0]==2
        assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE target_id=? AND action='ORDER_COMPLETED'",(o['id'],)).fetchone()[0]==1
    c=request(client,headers,'staff1','GET','/api/customers/'+cid).json()
    assert c['amount_due_minor']>=completed.json()['charge_minor']


def test_completion_is_atomic_when_charge_fails(demo):
    client,headers,path=demo
    o,_,_=prepare_ride(client,headers)
    with sqlite3.connect(path) as conn:
        conn.execute('''CREATE TRIGGER simulate_posting_failure BEFORE INSERT ON account_entries
             WHEN NEW.kind='CHARGE' BEGIN SELECT RAISE(ABORT, 'forced demo failure'); END;''')
    # The low-level service must roll back all writes. An API 500 is expected under injected DB failure.
    from refillops import service
    from refillops.db import connect
    with connect() as conn:
        rider = dict(conn.execute("SELECT id,station_id,role,display_name FROM users WHERE role='RIDER' AND display_name='Demo Rider A'").fetchone())
    try:
        service.complete_order(rider,o['id'],3,2,'failure-test')
        assert False, 'Injected DB failure was not triggered'
    except sqlite3.IntegrityError:
        pass
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT status FROM delivery_orders WHERE id=?',(o['id'],)).fetchone()[0]=='OUT_FOR_DELIVERY'
        assert conn.execute('SELECT COUNT(*) FROM delivery_confirmations WHERE order_id=?',(o['id'],)).fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM container_movements WHERE order_id=?',(o['id'],)).fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM idempotency_records WHERE request_key=?',('failure-test',)).fetchone()[0]==0


def test_price_snapshot_and_invoice_uniqueness(demo):
    client,headers,path=demo
    o,cid,_=prepare_ride(client,headers)
    with sqlite3.connect(path) as conn:
        conn.execute('UPDATE stations SET unit_price_minor=9000')
    result=request(client,headers,'rider1','POST',f"/api/orders/{o['id']}/complete",{'delivered_qty':3,'returned_empties_qty':2},{'Idempotency-Key':'price-snap-1'})
    assert result.status_code==200 and result.json()['charge_minor']==o['unit_price_minor']*3
    month=datetime.now(ZoneInfo('Asia/Manila')).strftime('%Y-%m')
    first=request(client,headers,'owner','POST','/api/billing/invoices',{'customer_id':cid,'month':month})
    assert first.status_code==201, first.text
    assert request(client,headers,'owner','POST','/api/billing/invoices',{'customer_id':cid,'month':month}).status_code==409
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM invoice_lines il JOIN account_entries a ON il.account_entry_id=a.id WHERE a.order_id=?',(o['id'],)).fetchone()[0]==1


def test_station_scope_and_rider_visibility(demo):
    client,headers,path=demo
    # Inject another entirely fictional station/customer and ensure station filtering rejects identifiers.
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO stations VALUES ('foreign','Other Fake Station',14.65,121.05,1.5,'Asia/Manila','PHP',3000)")
        conn.execute("INSERT INTO customers (id,station_id,display_name,opening_containers,created_at) VALUES ('foreign-cust','foreign','Other Tenant',0,'2026-10-28T00:00:00Z')")
    assert request(client,headers,'staff1','GET','/api/customers/foreign-cust').status_code==404
    assert request(client,headers,'staff1','POST','/api/locations',{'customer_id':'foreign-cust','label':'Fail','lat':14.65,'lon':121.05}).status_code==404
    # Rider cannot see unassigned or other rider's orders.
    listed=request(client,headers,'rider1','GET','/api/orders').json()
    assert all(o['rider_id'] for o in listed)
    staff_orders=request(client,headers,'staff1','GET','/api/orders').json()
    foreign_rider_orders=[o for o in staff_orders if o['rider_id'] and o['rider_id'] not in {row['rider_id'] for row in listed}]
    if foreign_rider_orders:
        assert request(client,headers,'rider1','GET','/api/orders/'+foreign_rider_orders[0]['id']).status_code==404


def test_failure_and_owner_exception_review(demo):
    client,headers,_=demo
    o,_,_=prepare_ride(client,headers)
    fail=request(client,headers,'rider1','POST',f"/api/orders/{o['id']}/fail",{'reason':'Fictional customer not present'})
    assert fail.status_code==200
    assert fail.json()['status']=='DELIVERY_FAILED'
    exceptions=request(client,headers,'owner','GET','/api/exceptions').json()
    e=next(e for e in exceptions if e['entity_id']==o['id'])
    reviewed=request(client,headers,'owner','POST',f"/api/exceptions/{e['id']}/review",{'note':'Reviewed demo delivery exception'})
    assert reviewed.status_code==200
    audit=request(client,headers,'owner','GET','/api/audit').json()
    assert any(a['action']=='EXCEPTION_REVIEWED' and a['target_id']==e['id'] for a in audit)


def test_owner_correction_is_append_only_and_audited(demo):
    client,headers,path=demo
    customer_id=request(client,headers,'staff1','GET','/api/customers').json()[0]['id']
    before=request(client,headers,'staff1','GET',f'/api/customers/{customer_id}').json()
    body={'reason':'Fictional reconciliation','container_delta':-1,'amount_delta_minor':-250}
    assert request(client,headers,'staff1','POST',f'/api/customers/{customer_id}/adjustments',body).status_code==403
    adjustment=request(client,headers,'owner','POST',f'/api/customers/{customer_id}/adjustments',body)
    assert adjustment.status_code==201,adjustment.text
    after=request(client,headers,'staff1','GET',f'/api/customers/{customer_id}').json()
    assert after['container_position']==before['container_position']-1
    assert after['amount_due_minor']==before['amount_due_minor']-250
    assert any(e['kind']=='ADJUSTMENT' for e in after['account_entries'])
    assert any(a['action']=='OWNER_ADJUSTMENT' for a in request(client,headers,'owner','GET','/api/audit').json())


def test_printable_invoice_detail_scoped(demo):
    client,headers,_=demo
    month=datetime.now(ZoneInfo('Asia/Manila')).strftime('%Y-%m')
    preview=request(client,headers,'owner','GET',f'/api/billing/preview?month={month}').json()
    assert len(preview['invoices'])>=1
    invoice_id=preview['invoices'][0]['id']
    detail=request(client,headers,'owner','GET','/api/billing/invoices/'+invoice_id)
    assert detail.status_code==200 and len(detail.json()['lines'])>=1
    assert sum(line['amount_minor'] for line in detail.json()['lines'])==detail.json()['total_minor']
    assert request(client,headers,'rider1','GET','/api/billing/invoices/'+invoice_id).status_code==403


def test_numeric_alias_resolves_destination_not_gallon(demo):
    client,headers,_=demo
    customer=request(client,headers,'staff1','GET','/api/customers').json()[0]
    loc=request(client,headers,'staff1','GET','/api/customers/'+customer['id']).json()['locations'][0]
    assert loc['numeric_alias'].isdigit()
    found=request(client,headers,'staff1','POST','/api/locations/aliases/resolve',{'alias':loc['numeric_alias']})
    assert found.status_code==200
    assert found.json()['id']==loc['id']
    assert request(client,headers,'rider1','POST','/api/locations/aliases/resolve',{'alias':loc['numeric_alias']}).status_code in (200,403)
    assert request(client,headers,'staff1','POST','/api/locations/aliases/resolve',{'alias':'ABC123'}).status_code==422


def test_customer_orders_reflect_lifecycle_without_premature_charges(demo):
    client, headers, _ = demo
    order, cid, _ = new_order(client, headers, qty=3)
    before = request(client, headers, 'staff1', 'GET', f'/api/customers/{cid}').json()
    created = next(o for o in before['orders'] if o['id'] == order['id'])
    assert created['status'] == 'CREATED'
    assert created['requested_qty'] == 3
    assert created['delivered_qty'] is None
    assert created['charge_minor'] == 0
    directory = request(client, headers, 'staff1', 'GET', '/api/customers').json()
    summary = next(c for c in directory if c['id'] == cid)
    active_before = summary['active_orders']
    completed_before = summary['completed_orders']
    assert active_before >= 1
    assert summary['total_orders'] >= 1
    assert summary['amount_due_minor'] == before['amount_due_minor']
    assert summary['container_position'] == before['container_position']

    rider = next(r for r in request(client, headers, 'staff1', 'GET', '/api/riders').json()
                 if r['display_name'] == 'Demo Rider A')
    assert request(client, headers, 'staff1', 'POST', f"/api/orders/{order['id']}/assign", {'rider_id': rider['id']}).status_code == 200
    assert request(client, headers, 'rider1', 'POST', f"/api/orders/{order['id']}/dispatch").status_code == 200
    during = request(client, headers, 'staff1', 'GET', f'/api/customers/{cid}').json()
    current = next(o for o in during['orders'] if o['id'] == order['id'])
    assert current['status'] == 'OUT_FOR_DELIVERY'
    assert current['rider_name'] == 'Demo Rider A'
    assert during['amount_due_minor'] == before['amount_due_minor']

    completion = request(client, headers, 'rider1', 'POST', f"/api/orders/{order['id']}/complete",
                         {'delivered_qty': 3, 'returned_empties_qty': 2}, {'Idempotency-Key': str(uuid.uuid4())})
    assert completion.status_code == 200, completion.text
    after = request(client, headers, 'staff1', 'GET', f'/api/customers/{cid}').json()
    finished = next(o for o in after['orders'] if o['id'] == order['id'])
    assert finished['status'] == 'COMPLETED'
    assert finished['delivered_qty'] == 3
    assert finished['returned_empties_qty'] == 2
    assert finished['charge_minor'] == completion.json()['charge_minor']
    assert after['amount_due_minor'] == before['amount_due_minor'] + finished['charge_minor']
    assert after['container_position'] == before['container_position'] + 1
    directory = request(client, headers, 'staff1', 'GET', '/api/customers').json()
    summary = next(c for c in directory if c['id'] == cid)
    assert summary['completed_orders'] == completed_before + 1
    assert summary['active_orders'] == active_before - 1


def test_customer_can_link_multiple_houses_and_orders_reject_cross_customer_house(demo):
    client, headers, path = demo
    customers = request(client, headers, 'staff1', 'GET', '/api/customers').json()
    customer = next(c for c in customers if c['display_name']=='Sample Customer A')
    other = next(c for c in customers if c['display_name']=='Sample Customer B')
    assert customer['house_count']==1
    assert customer['house_labels']=='Sample House A'
    detail = request(client,headers,'staff1','GET',f"/api/customers/{customer['id']}").json()
    house_a = detail['locations'][0]
    assert house_a['label']=='Sample House A'
    wrong = request(client,headers,'staff1','POST','/api/orders',
       {'customer_id':other['id'], 'location_id':house_a['id'], 'requested_qty':2})
    assert wrong.status_code==422
    new_house = request(client,headers,'staff1','POST','/api/locations',
       {'customer_id':customer['id'],'label':'Sample House A Annex','lat':14.6501,'lon':121.0501})
    assert new_house.status_code==201
    updated = request(client,headers,'staff1','GET','/api/customers').json()
    assert next(c for c in updated if c['id']==customer['id'])['house_count']==2
    order = request(client,headers,'staff1','POST','/api/orders',
       {'customer_id':customer['id'], 'location_id':new_house.json()['id'], 'requested_qty':2})
    assert order.status_code==201
    linked = request(client,headers,'staff1','GET',f"/api/customers/{customer['id']}").json()
    assert any(o['location_label']=='Sample House A Annex' for o in linked['orders'])


def test_optional_demo_relabel_preserves_order_and_account_ids(demo):
    from refillops.cli import relabel_demo
    client,headers,path=demo
    with sqlite3.connect(path) as conn:
        customer_id = conn.execute("SELECT id FROM customers WHERE display_name='Sample Customer A'").fetchone()[0]
        order_ids_before = [r[0] for r in conn.execute('SELECT id FROM delivery_orders ORDER BY id')]
        container_before = conn.execute('SELECT opening_containers FROM customers WHERE id=?', (customer_id,)).fetchone()[0]
        conn.execute("UPDATE customers SET display_name='Sample House A' WHERE id=?", (customer_id,))
        conn.execute("UPDATE delivery_locations SET label='Demo Pin 1' WHERE customer_id=?", (customer_id,))
    relabel_demo()
    relabel_demo() # safe to rerun
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT display_name FROM customers WHERE id=?',(customer_id,)).fetchone()[0]=='Sample Customer A'
        assert conn.execute('SELECT label FROM delivery_locations WHERE customer_id=?',(customer_id,)).fetchone()[0]=='Sample House A'
        assert [r[0] for r in conn.execute('SELECT id FROM delivery_orders ORDER BY id')]==order_ids_before
        assert conn.execute('SELECT opening_containers FROM customers WHERE id=?',(customer_id,)).fetchone()[0]==container_before
