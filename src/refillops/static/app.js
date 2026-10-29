/* RefillOps: intentionally dependency-free local console. Browser is never the ledger authority. */
// Display preference is local to this browser and independent of all station records.
const THEME_SELECT = document.getElementById('theme-select');
const preferredScheme = window.matchMedia?.('(prefers-color-scheme: light)');
function syncThemeColor() {
  const selected = document.documentElement.dataset.theme || 'dark';
  const light = selected === 'light' || (selected === 'system' && !!preferredScheme?.matches);
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', light ? '#f4f8f5' : '#081419');
}
if (THEME_SELECT) {
  THEME_SELECT.value = document.documentElement.dataset.theme || 'dark';
  THEME_SELECT.addEventListener('change', () => {
    const choice = THEME_SELECT.value;
    if (!['dark', 'light', 'system'].includes(choice)) return;
    document.documentElement.dataset.theme = choice;
    try { localStorage.setItem('refillops-theme', choice); } catch (_) { /* private browsing */ }
    syncThemeColor();
  });
}
preferredScheme?.addEventListener?.('change', syncThemeColor);
syncThemeColor();

const ROOT = document.getElementById('content');
const NAV = document.getElementById('nav');
const pages = {
  dashboard: ['Overview', '▦'], orders: ['Orders', '≡'], customers: ['Customers', '◎'],
  billing: ['Billing', '◫'], exceptions: ['Exceptions', '!'], audit: ['Activity', '↺']
};
const state = {token: sessionStorage.getItem('refillops-key') || '', actor:null, page:'dashboard', month: new Date().toLocaleDateString('en-CA', {timeZone:'Asia/Manila'}).slice(0,7)};
const safe = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money = cents => '₱' + (Number(cents||0)/100).toLocaleString('en-PH',{minimumFractionDigits:2,maximumFractionDigits:2});
const badge = status => `<span class="badge ${safe(String(status||'').toLowerCase())}">${safe(status?.replaceAll('_',' ')||'—')}</span>`;
const short = s => safe(String(s||'').slice(0,8));
const orderRef = o => safe(o.order_number || short(o.id));
const deliveryBadge = o => badge(o.delivery_status || o.status);
const paymentBadge = o => badge(o.payment_status || 'NOT_DUE');
const blank = text => `<div class="empty">${safe(text)}</div>`;
const header = (eyebrow, title, desc, action='') => `<div class="heading"><div><div class="eyebrow">${safe(eyebrow)}</div><h1>${safe(title)}</h1><p>${safe(desc)}</p></div>${action}</div>`;
const formfield = (title, name, type, placeholder='', value='', min='') => `<div><label>${safe(title)}</label><input type="${type}" name="${name}" placeholder="${safe(placeholder)}" value="${safe(value)}" ${min} required></div>`;
const table = (heads, rows) => rows.length ? `<div class="table-wrap"><table><thead><tr>${heads.map(h=>`<th>${safe(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>` : blank('No demo records for this view');

// Native window.prompt/confirm dialogs are unavailable in some VS Code browser previews.
// All operational questions use the same accessible in-page dialog instead.
const modalHost = document.getElementById('action-modal-root');
let modalTrigger = null;
function closeActionModal() {
  if (!modalHost.firstElementChild) return;
  modalHost.innerHTML = '';
  document.body.classList.remove('has-action-modal');
  if (modalTrigger?.isConnected) modalTrigger.focus();
  modalTrigger = null;
}
function openActionModal(kind, id, trigger) {
  const specs = {
    review: {
      title: 'Review exception', description: 'Record what you checked. The original event and audit history remain intact.',
      submit: 'Record review', fields: `<label for="action-note">Review note <span aria-hidden="true">*</span></label><textarea id="action-note" name="note" rows="4" required minlength="2" maxlength="1000" placeholder="What did you verify, and what needs to happen next?"></textarea>`
    },
    complete: {
      title: 'Confirm delivery', description: 'Delivered full gallons and returned empty containers are recorded separately. This will post the delivery charge.',
      submit: 'Confirm delivery', fields: `<div class="dialog-fields"><div><label for="action-delivered">Full gallons delivered</label><input id="action-delivered" name="delivered_qty" type="number" min="1" max="10000" step="1" value="2" required></div><div><label for="action-returned">Empty containers returned</label><input id="action-returned" name="returned_empties_qty" type="number" min="0" max="10000" step="1" value="1" required></div></div>`
    },
    fail: {
      title: 'Report failed delivery', description: 'Provide the failure reason so the owner can investigate the delivery exception.',
      submit: 'Report failure', fields: `<label for="action-reason">Reason for failed delivery</label><textarea id="action-reason" name="reason" rows="4" minlength="2" maxlength="1000" placeholder="For example: Customer was unavailable" required></textarea>`
    },
    cancel: {
      title: 'Cancel order?', description: 'This changes the order status. It does not delete the original order or audit history.',
      submit: 'Cancel order', fields: ''
    },
    invoice: {
      title: 'Issue invoice?', description: 'This creates an immutable invoice for the customer’s currently eligible charges.',
      submit: 'Issue invoice', fields: ''
    }
  };
  const spec = specs[kind];
  if (!spec) throw new Error('Unsupported action');
  closeActionModal();
  modalTrigger = trigger;
  modalHost.innerHTML = `<div class="action-modal-backdrop"><section class="action-modal" role="dialog" aria-modal="true" aria-labelledby="action-modal-title" aria-describedby="action-modal-description"><h2 id="action-modal-title">${safe(spec.title)}</h2><p id="action-modal-description">${safe(spec.description)}</p><p class="small mono">${kind === 'review' ? 'Exception' : kind === 'invoice' ? 'Customer' : 'Order'} · ${short(id)}</p><form id="action-modal-form">${spec.fields}<p id="action-modal-error" role="alert" class="dialog-error" hidden></p><div class="dialog-actions"><button type="button" class="ghost" data-action="close-dialog">Go back</button><button type="submit" class="${kind === 'fail' || kind === 'cancel' ? 'danger' : 'primary'}">${safe(spec.submit)}</button></div></form></section></div>`;
  const form = document.getElementById('action-modal-form');
  form.dataset.kind = kind;
  form.dataset.id = id;
  // Keep one key through request retries to avoid duplicate ledger posting.
  if (kind === 'complete') form.dataset.idempotencyKey = crypto.randomUUID();
  document.body.classList.add('has-action-modal');
  (form.querySelector('textarea,input,button[type="submit"]') || form).focus();
}
async function submitActionModal(form) {
  const kind = form.dataset.kind, id = form.dataset.id;
  const submit = form.querySelector('button[type="submit"]');
  const error = document.getElementById('action-modal-error');
  const input = Object.fromEntries(new FormData(form).entries());
  error.hidden = true;
  submit.disabled = true;
  try {
    if (kind === 'review') {
      const note = input.note?.trim();
      if (!note) throw new Error('Review note is required');
      await api('/exceptions/' + id + '/review', 'POST', {note});
      toast('Review recorded in audit history');
    } else if (kind === 'complete') {
      const delivered_qty = Number(input.delivered_qty);
      const returned_empties_qty = Number(input.returned_empties_qty);
      if (!Number.isSafeInteger(delivered_qty) || delivered_qty <= 0 ||
          !Number.isSafeInteger(returned_empties_qty) || returned_empties_qty < 0)
        throw new Error('Enter valid whole-number quantities');
      const outcome = await api('/orders/' + id + '/complete', 'POST',
        {delivered_qty, returned_empties_qty}, {'Idempotency-Key': form.dataset.idempotencyKey});
      toast(`Completed. Charge ${money(outcome.charge_minor)}. Container position ${outcome.container_position}.`);
    } else if (kind === 'fail') {
      const reason = input.reason?.trim();
      if (!reason) throw new Error('Failure reason is required');
      await api('/orders/' + id + '/fail', 'POST', {reason});
      toast('Delivery failed; owner exception generated');
    } else if (kind === 'cancel') {
      await api('/orders/' + id + '/cancel', 'POST');
      toast('Order cancelled');
    } else if (kind === 'invoice') {
      const inv = await api('/billing/invoices', 'POST', {customer_id:id, month:state.month});
      toast(`Invoice issued: ${money(inv.total_minor)} (${inv.line_count} charges)`);
    } else throw new Error('Unsupported action');
    closeActionModal();
    await render();
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
    submit.disabled = false;
  }
}
function toast(msg,isError=false){let el=document.getElementById('toast');el.textContent=msg;el.className=isError?'error':'';el.style.display='block';clearTimeout(window._toastTimer);window._toastTimer=setTimeout(()=>el.style.display='none',6000)}
async function api(path, method='GET', body=null, extra={}) {
  const res=await fetch('/api'+path,{method,headers:{...(state.token?{'Authorization':'Bearer '+state.token}:{}),...(body?{'Content-Type':'application/json'}:{}),...extra},body:body?JSON.stringify(body):null});
  let data=await res.json().catch(()=>({detail:'Unparseable response'}));
  if(!res.ok)throw new Error(data.detail||`HTTP ${res.status}`);
  return data;
}
function authScreen(){
  NAV.innerHTML='';document.getElementById('identity').textContent='Not signed in';document.getElementById('logout').hidden=true;
  ROOT.innerHTML=`<div class="hero"><div><div class="eyebrow">Local portfolio demonstration</div><h1>Every refill.<br><em>Accounted for.</em></h1><p class="hero-desc">A traceable order-to-billing workflow for neighborhood water-refilling stations—focused on remote owner oversight.</p></div><div class="hero-mark" aria-hidden="true"><span>R</span></div></div>
  <div class="panel auth"><h2>Enter the fictional demo</h2><p>Run <code>python -m refillops.cli seed</code>, then open <code>.local/demo_access.json</code> to copy a generated Owner, Staff, Rider, or Customer demo key. Tokens are never stored in the repository.</p><form id="login-form"><label>Generated demo actor key</label><div class="form-row"><input name="token" type="password" required placeholder="Paste local bearer key" autocomplete="off" style="flex:1"><button class="primary">Enter console</button></div></form><p class="small muted">Local-only. No real people, real payments, or live station operations.</p></div>`;
}
function setupNav(){
  const role=state.actor.role;
  const allowed=role==='OWNER'?['dashboard','orders','customers','billing','exceptions','audit']:role==='STAFF'?['orders','customers','billing']:['orders'];
  if(!allowed.includes(state.page))state.page=allowed[0];
  NAV.innerHTML=allowed.map(k=>`<button class="nav-item ${state.page===k?'active':''}" data-nav="${k}"><b aria-hidden="true">${pages[k][1]}</b>${pages[k][0]}</button>`).join('');
  document.getElementById('identity').textContent=`${state.actor.display_name} · ${role}`;
  document.getElementById('logout').hidden=false;
  document.getElementById('active-page').textContent=(role==='CUSTOMER' ? 'MY ORDERS' : pages[state.page][0].toUpperCase());
}
async function render(){
  if(!state.actor){authScreen();return}
  setupNav(); ROOT.innerHTML='<div class="panel">Loading local demo data…</div>';
  try{
    if(state.page==='dashboard')await dashboard();
    if(state.page==='orders')await orders();
    if(state.page==='customers')await customers();
    if(state.page==='billing')await billing();
    if(state.page==='exceptions')await exceptions();
    if(state.page==='audit')await audit();
  }catch(e){ROOT.innerHTML=`<div class="panel"><h2>Unable to load view</h2><p>${safe(e.message)}</p><button class="ghost" data-action="retry">Retry</button></div>`}
}
async function dashboard(){
  const [d,st,orders]=await Promise.all([api('/dashboard'),api('/station'),api('/orders')]);
  const counts=d.orders_by_status;const total=Object.values(counts).reduce((a,b)=>a+b,0);
  ROOT.innerHTML=header('Owner control center','The station, at a glance','Know what needs attention without chasing every delivery.')+
  `<div class="grid kpis"><div class="kpi"><div class="label">Orders in system</div><strong class="value">${total}</strong><span class="foot">All demo states</span></div><div class="kpi"><div class="label">Completed today</div><strong class="value">${d.completed_today}</strong><span class="foot">Station-local date</span></div><div class="kpi"><div class="label">Outstanding balance</div><strong class="value">${money(d.receivables_minor)}</strong><span class="foot">Signed ledger entries</span></div><div class="kpi"><div class="label">Exceptions to review</div><strong class="value">${d.open_exceptions.length}</strong><span class="foot">Open queue items</span></div></div>`+
  `<div class="grid two"><section class="panel"><div class="panel-header"><h2>Delivery pipeline</h2><span class="chip">LIVE DEMO DATA</span></div>`+
  table(['Status','Orders'],Object.entries(counts).map(([key,val])=>`<tr><td>${badge(key==='CREATED'||key==='ASSIGNED'?'ORDERED':key==='COMPLETED'?'DELIVERED':key)}</td><td><strong>${val}</strong></td></tr>`))+
  `</section><section class="panel"><div class="panel-header"><h2>Needs attention</h2><button class="ghost button-small" data-nav="exceptions">All exceptions</button></div>${d.open_exceptions.length?d.open_exceptions.slice(0,5).map(e=>`<div class="item"><strong>${safe(e.kind.replaceAll('_',' '))}</strong><span class="muted small">${safe(e.severity)} · ${safe(e.order_number || short(e.entity_id))}</span></div>`).join(''):blank('No open exceptions')}</section></div>`+
  `<div class="panel"><h2>Station coverage</h2><div class="privacy">${safe(st.name)} · ${safe(st.radius_km)} km <strong>straight-line</strong> radius · ${safe(st.timezone)} · ${safe(st.currency)} ${money(st.unit_price_minor)} per delivered gallon. This is not a travel-time or road-distance guarantee.</div></div>`;
}
async function orders(){
  const role=state.actor.role;
  const requests=[api('/orders')];if(role==='OWNER'||role==='STAFF')requests.push(api('/customers'),api('/riders'));
  const res=await Promise.all(requests);const allOrders=res[0],customers=res[1]||[],riders=res[2]||[];
  let destinationOptions=[];
  if(role==='OWNER'||role==='STAFF'){
    const details=await Promise.all(customers.map(c=>api('/customers/'+c.id)));
    destinationOptions=details.flatMap(c=>c.locations.map(l=>({id:l.id,customer_id:c.id,label:`${l.label} (Customer: ${c.display_name})`})));
  }
  const isCustomer=role==='CUSTOMER', isRider=role==='RIDER';
  ROOT.innerHTML=header(isCustomer?'Read-only customer record':isRider?'Delivery execution':'Transaction management',isCustomer?'My orders':isRider?'My deliveries':'Orders & dispatch',
    'The same Order Number connects customer, house, rider, delivery events and recorded payment.')+
  ((isRider||isCustomer)?'':`<section class="panel"><h2>Create an order</h2><form id="create-order" class="form-grid"><div><label>House / customer account</label><select name="destination" required><option value="">Choose destination…</option>${destinationOptions.map(o=>`<option value="${safe(o.customer_id+'|'+o.id)}">${safe(o.label)}</option>`).join('')}</select></div>${formfield('Gallons requested','requested_qty','number','3','3','min="1" max="10000"')}<div><label>&nbsp;</label><button type="submit" class="primary">Create order</button></div></form></section>`)+
  `<section class="panel"><div class="panel-header"><h2>${isCustomer?'My recorded orders':isRider?'Assigned to me':'All station orders'}</h2><span class="chip">${allOrders.length} RECORDS</span></div>`+
  table(['Order Number / destination','Gallons','Delivery','Payment','Assigned Rider','Actions'],allOrders.map(o=>{
    let actions='';
    if(isRider&&o.status==='ASSIGNED') actions=`<button class="primary button-small" data-action="dispatch" data-id="${safe(o.id)}">Start delivery</button>`;
    if(isRider&&o.status==='OUT_FOR_DELIVERY') actions=`<button class="primary button-small" data-action="complete" data-id="${safe(o.id)}">Confirm</button><button class="danger button-small" data-action="fail" data-id="${safe(o.id)}">Failed</button>`;
    if(!isRider&&!isCustomer&&(o.status==='CREATED'||o.status==='DELIVERY_FAILED')) actions=`<select class="inline-select" id="rider-${safe(o.id)}"><option value="">Assign rider…</option>${riders.map(r=>`<option value="${safe(r.id)}">${safe(r.display_name)}</option>`).join('')}</select><button class="ghost button-small" data-action="assign" data-id="${safe(o.id)}">Assign</button>`;
    if(!isRider&&!isCustomer&&['CREATED','ASSIGNED','OUT_FOR_DELIVERY','DELIVERY_FAILED'].includes(o.status))actions+=`<button class="danger button-small" data-action="cancel" data-id="${safe(o.id)}">Cancel</button>`;
    return `<tr><td><strong class="order-number">${orderRef(o)}</strong><div class="small muted">${safe(o.customer_name)} · ${safe(o.location_label)}</div></td><td>${o.requested_qty}${o.delivered_qty!=null?`<div class="small muted">${o.delivered_qty} delivered</div>`:''}</td><td>${deliveryBadge(o)}</td><td>${paymentBadge(o)}${o.charge_minor>0?`<div class="small muted">Due ${money(o.order_due_minor)}</div>`:''}</td><td>${safe(o.rider_name||'Unassigned')}</td><td>${actions||'<span class="muted">Read only</span>'}</td></tr>`;
  }))+'</section><p class="counter-note">Delivery and payment are independent statuses. A confirmed delivery creates a charge; only a payment allocated to that Order Number marks it Paid. Customer-wide unallocated receipts do not silently mark orders paid. Open order views check for updates automatically.</p>';
}

async function customers(){
  const list=await api('/customers');
  ROOT.innerHTML=header('Location identity','Customers & destinations','Customers are account holders. Houses are pinned delivery locations linked to those customers; gallon exchanges never identify physical gallon IDs.')+
  `<section class="panel"><h2>Register a demo customer</h2><form id="create-customer" class="form-grid">${formfield('Fictional customer name','display_name','text','Sample Customer K')}${formfield('Opening outstanding containers','opening_containers','number','0','0','min="0"')}<div><label>&nbsp;</label><button class="primary">Create customer</button></div></form></section>`+
  `<section class="panel"><div class="panel-header"><h2>Resolve a destination number</h2><span class="chip">NOT A GALLON ID</span></div><form id="resolve-alias" class="form-row"><input name="alias" inputmode="numeric" pattern="[0-9]+" placeholder="e.g. 000001" aria-label="Numeric destination alias" required><button class="ghost">Look up location</button></form></section><section class="panel"><div class="panel-header"><h2>Customer directory</h2><span class="chip">${list.length} CUSTOMERS</span></div>`+
  table(['Customer','Linked house(s)','Orders','Containers out','Account due','Action'],list.map(c=>`<tr><td><strong>${safe(c.display_name)}</strong><div class="mono">${short(c.id)}</div></td><td><strong>${c.house_count} linked</strong><div class="small muted">${safe(c.house_labels||'No house registered')}</div></td><td><strong>${c.active_orders} active</strong><div class="small muted">${c.completed_orders} completed${c.failed_orders?` · ${c.failed_orders} failed`:''}</div></td><td>${c.container_position}</td><td>${money(c.amount_due_minor)}</td><td><button class="ghost button-small" data-action="customer" data-id="${c.id}">View & manage</button></td></tr>`))+'<p class="counter-note">Orders update when created or reassigned; financial and container balances update only after confirmed delivery.</p></section><div id="customer-details"></div>';
}
async function customerDetail(id){
  const c=await api('/customers/'+id);
  const orderRows=c.orders.map(o=>`<tr><td><strong class="order-number">${orderRef(o)}</strong><div class="small muted">House: ${safe(o.location_label)} · ${safe(o.created_at.slice(0,10))}</div></td><td>${o.requested_qty}</td><td>${deliveryBadge(o)}</td><td>${paymentBadge(o)}</td><td>${o.rider_name?safe(o.rider_name):'<span class="muted">Unassigned</span>'}</td><td>${o.delivered_qty==null?'<span class="muted">—</span>':`${o.delivered_qty} delivered / ${o.returned_empties_qty} returned`}</td><td>${o.status==='COMPLETED'?money(o.order_due_minor)+' due':'<span class="muted">Not charged</span>'}</td></tr>`);
  document.getElementById('customer-details').innerHTML=`<div class="panel"><div class="panel-header"><h2>${safe(c.display_name)} · account</h2><span class="chip">${c.container_position} CONTAINERS OUT</span></div><div class="grid two"><div><h3>Linked houses / destinations</h3><p class="small muted">A house identifies a delivery point; this customer is responsible for its account activity.</p>${c.locations.map(l=>`<div class="item"><strong>${safe(l.label)}</strong><div class="mono">Alias: ${safe(l.numeric_alias)} · ${safe(l.lat)}, ${safe(l.lon)}</div><button class="ghost button-small" data-action="token" data-id="${l.id}">Generate destination token</button></div>`).join('')||blank('No location registered')}<form id="create-location" class="form-grid" style="margin-top:14px"><input type="hidden" name="customer_id" value="${safe(c.id)}">${formfield('House / destination label','label','text','House K')}${formfield('Latitude','lat','number','14.650','14.650','step="any"')}${formfield('Longitude','lon','number','121.050','121.050','step="any"')}<button class="ghost">Add location</button></form></div><div><h3>Financial activity</h3><p>Amount due: <strong>${money(c.amount_due_minor)}</strong></p>${c.account_entries.length?c.account_entries.map(e=>`<div class="item"><strong>${safe(e.kind)} · ${money(e.amount_minor)}${e.order_number?' · '+safe(e.order_number):''}</strong><span class="mono">${safe(e.created_at.slice(0,10))}</span></div>`).join(''):blank('No financial entries yet')}</div></div><section style="margin-top:20px"><div class="panel-header"><h3>Orders linked to this customer and their houses</h3><span class="chip">${c.orders.length} ORDERS</span></div>${orderRows.length?table(['Order Number / destination','Requested','Delivery','Payment','Rider','Confirmed exchange','Amount'],orderRows):blank('No orders for this customer yet')}<p class="counter-note">An order is visible immediately after creation. Charges and container counts change only on successful delivery confirmation.</p></section>${state.actor.role==='OWNER'?`<form id="owner-adjustment" class="form-grid four" style="margin-top:20px"><input type="hidden" name="customer_id" value="${safe(c.id)}">${formfield('Correction reason','reason','text','Reconciled after review')}${formfield('Container delta','container_delta','number','0','0','step="1"')}${formfield('Account delta in PHP','amount','number','0.00','0.00','step="0.01"')}<div><label>&nbsp;</label><button class="ghost">Post audited adjustment</button></div></form>`:''}<button class="ghost button-small" data-action="customer-access" data-id="${safe(c.id)}">Issue read-only customer demo key</button><div id="token-output"></div></div>`;
  document.getElementById('customer-details').scrollIntoView({behavior:'smooth',block:'start'});
}

async function billing(){
  const [b,allOrders]=await Promise.all([api('/billing/preview?month='+encodeURIComponent(state.month)),api('/orders')]);
  const payable=allOrders.filter(o=>o.payment_status==='UNPAID'||o.payment_status==='PARTIALLY_PAID');
  ROOT.innerHTML=header('Financial control','Monthly billing','Allocate a receipt to the Order Number to update Paid/Unpaid across owner, rider and customer views.')+
  `<section class="panel"><div class="panel-header"><h2>Billing period</h2><form id="change-month" class="form-row"><input type="month" name="month" value="${safe(state.month)}" required><button class="ghost">View period</button></form></div><p class="small muted">${safe(b.note)}</p>`+
  table(['Customer','Uninvoiced charges','Uninvoiced total','Balance due','Action'],b.customers.map(c=>`<tr><td>${safe(c.display_name)}</td><td>${c.eligible_charges}</td><td>${money(c.uninvoiced_total_minor)}</td><td>${money(c.amount_due_minor)}</td><td>${state.actor.role==='OWNER'&&c.eligible_charges?`<button class="primary button-small" data-action="invoice" data-id="${safe(c.id)}">Issue invoice</button>`:'—'}</td></tr>`))+
  `</section><div class="grid two"><section class="panel"><h2>Record a payment</h2><form id="record-payment" class="form-grid" style="grid-template-columns:1fr 1fr">`+
  `<div><label>Customer</label><select name="customer_id" id="payment-customer" required><option value="">Select customer…</option>${b.customers.map(c=>`<option value="${safe(c.id)}">${safe(c.display_name)}</option>`).join('')}</select></div>`+
  `<div><label>Order Number to settle</label><select name="order_id" id="payment-order"><option value="">Unallocated customer payment</option>${payable.map(o=>`<option value="${safe(o.id)}" data-customer="${safe(o.customer_id)}">${orderRef(o)} · ${safe(o.customer_name)} · Due ${money(o.order_due_minor)}</option>`).join('')}</select></div>`+
  `${formfield('Amount in PHP','amount','number','30.00','30.00','min="0.01" step="0.01"')}${formfield('Method label','method','text','Cash')}${formfield('Reference','reference','text','Manual receipt')}<div><button class="primary">Record payment</button></div></form><p class="small muted">Selecting an order assigns the receipt to that order. Without an order selection, this remains an unallocated account payment and does not mark any order Paid.</p></section>`+
  `<section class="panel"><h2>Issued invoices · ${safe(state.month)}</h2>${b.invoices.length?b.invoices.map(i=>`<div class="item"><strong>${money(i.total_minor)}</strong><span class="mono">Invoice ${short(i.id)} · ${safe(i.issued_at.slice(0,10))}</span><div><button class="ghost button-small" data-action="invoice-detail" data-id="${safe(i.id)}">View invoice</button></div></div>`).join(''):blank('No invoices issued this period')}</section></div><div id="invoice-output"></div>`;
}

async function exceptions(){
  const entries=await api('/exceptions');
  ROOT.innerHTML=header('Remote owner oversight','Exceptions','Visible issues are reviewed, not silently erased from history.')+
  `<section class="panel"><h2>Exception queue</h2>`+table(['Exception','Severity','Status','Linked item','Action'],entries.map(e=>`<tr><td><strong>${safe(e.kind.replaceAll('_',' '))}</strong></td><td>${safe(e.severity)}</td><td>${badge(e.state)}</td><td class="mono">${safe(e.entity_type)} · ${safe(e.order_number || short(e.entity_id))}</td><td>${e.state==='OPEN'?`<button class="ghost button-small" data-action="review" data-id="${e.id}">Review</button>`:safe(e.note||'Reviewed')}</td></tr>`))+'</section>';
}
async function audit(){
  const entries=await api('/audit');
  ROOT.innerHTML=header('Traceability','Audit history','Material changes record actor, action, target, and time.')+
  `<section class="panel"><h2>Most recent 200 recorded events</h2>`+
  table(['Action','Actor','Target','UTC time'],entries.map(e=>`<tr><td><strong>${safe(e.action.replaceAll('_',' '))}</strong></td><td>${safe(e.actor_name)}</td><td class="mono">${safe(e.target_type)} · ${safe(e.order_number || short(e.target_id))}</td><td class="mono">${safe(e.created_at.slice(0,19))}</td></tr>`))+'</section>';
}
async function action(btn){const a=btn.dataset.action,id=btn.dataset.id;
  if(a==='retry')return render();
  if(a==='customer')return customerDetail(id);
  if(a==='assign'){const rider_id=document.getElementById('rider-'+id).value;if(!rider_id)throw new Error('Choose a rider');await api('/orders/'+id+'/assign','POST',{rider_id});toast('Rider assigned');return render();}
  if(a==='dispatch'){await api('/orders/'+id+'/dispatch','POST');toast('Delivery marked out for delivery');return render();}
  if(a==='close-dialog'){closeActionModal();return;}
  if(['complete','cancel','fail','review','invoice'].includes(a)){
    openActionModal(a,id,btn);return;
  }
  if(a==='customer-access'){
    const t=await api('/customers/'+id+'/portal-access','POST');
    document.getElementById('token-output').innerHTML=`<section class="panel"><h3>Read-only customer demo key (shown once)</h3><p>For ${safe(t.customer_name)}. Keep this local: it replaces any previous customer portal key.</p><span class="secret">${safe(t.api_key)}</span></section>`;
    toast('Customer demo key issued');return;
  }
  if(a==='token'){
    const t=await api('/locations/'+id+'/tokens','POST');document.getElementById('token-output').innerHTML=`<div class="panel"><h3>New opaque destination token (displayed once)</h3><span class="secret">${safe(t.token)}</span><p class="small">Only authorized staff/riders can resolve it; do not confuse it with a physical gallon ID.</p><button class="ghost button-small" data-action="copy-token" data-token="${safe(t.token)}">Copy token</button><button class="danger button-small" data-action="revoke-token" data-id="${safe(t.id)}">Revoke</button></div>`;toast('Destination token generated');return;
  }
  if(a==='copy-token'){await navigator.clipboard.writeText(btn.dataset.token);return toast('Copied local demo token');}
  if(a==='revoke-token'){await api('/locations/tokens/'+id+'/revoke','POST');toast('Token revoked');document.getElementById('token-output').innerHTML='';return;}
  if(a==='invoice-detail'){
    const invoice=await api('/billing/invoices/'+id);
    document.getElementById('invoice-output').innerHTML=`<section class="panel printable"><div class="panel-header"><h2>Invoice ${short(invoice.id)} · ${safe(invoice.customer_name)}</h2><span class="chip">ISSUED</span></div><p>Billing month: <strong>${safe(invoice.month)}</strong> · Issued: ${safe(invoice.issued_at)}</p>${table(['Order','Delivered','Unit price','Charge'],invoice.lines.map(line=>`<tr><td class="mono">${safe(line.order_number || short(line.order_id))}</td><td>${safe(line.delivered_qty)}</td><td>${money(line.unit_price_minor)}</td><td>${money(line.amount_minor)}</td></tr>`))}<p><strong>Total: ${money(invoice.total_minor)}</strong></p><button class="ghost button-small hide-on-print" data-action="print">Print summary</button></section>`;
    document.getElementById('invoice-output').scrollIntoView({behavior:'smooth',block:'start'});return;
  }
  if(a==='print'){window.print();return;}
}
document.addEventListener('click', async event=>{
  if (event.target.classList.contains('action-modal-backdrop')){closeActionModal();return;}
  const b=event.target.closest('[data-nav],[data-action]');if(!b)return;
  try{if(b.dataset.nav){closeActionModal();state.page=b.dataset.nav;return render();}await action(b)}catch(e){toast(e.message,true)}
});
document.addEventListener('keydown', event=>{
  if(event.key==='Escape' && modalHost.firstElementChild){event.preventDefault();closeActionModal();}
  if(event.key==='Tab' && modalHost.firstElementChild){
    const focusable=[...modalHost.querySelectorAll('input:not([disabled]),textarea:not([disabled]),button:not([disabled])')];
    if(!focusable.length)return;
    const first=focusable[0],last=focusable[focusable.length-1];
    if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
  }
});
document.getElementById('logout').addEventListener('click',()=>{closeActionModal();sessionStorage.removeItem('refillops-key');state.token='';state.actor=null;state.page='dashboard';authScreen()});
document.addEventListener('change',e=>{
  if(e.target.id==='payment-order' && e.target.value){
    const selected=e.target.selectedOptions[0];
    document.getElementById('payment-customer').value=selected.dataset.customer;
    const match=/Due ₱([0-9,.]+)/.exec(selected.textContent);
    if(match)document.querySelector('#record-payment [name="amount"]').value=match[1].replaceAll(',','');
  }
});
document.addEventListener('submit',async e=>{
  const form=e.target;if(!form.id)return;e.preventDefault();const o=Object.fromEntries(new FormData(form).entries());
  try{
    if(form.id==='action-modal-form')return submitActionModal(form);
    if(form.id==='login-form'){
      state.token=o.token;state.actor=await api('/me');sessionStorage.setItem('refillops-key',state.token);state.page=state.actor.role==='OWNER'?'dashboard':'orders';return render();
    }
    if(form.id==='resolve-alias'){
      const loc=await api('/locations/aliases/resolve','POST',{alias:o.alias});
      toast(`House: ${loc.label}. Customer: ${loc.customer_name}. This is not an individual gallon ID.`);
      return customerDetail(loc.customer_id);
    }
    if(form.id==='create-customer'){const c=await api('/customers','POST' ,{display_name:o.display_name,opening_containers:Number(o.opening_containers)});await render();await customerDetail(c.id);toast('Customer registered. Add a house / delivery pin to this account.');return;}
    if(form.id==='owner-adjustment'){
      const amount_delta_minor=Math.round(Number(o.amount)*100);
      await api('/customers/'+o.customer_id+'/adjustments','POST',{reason:o.reason,container_delta:Number(o.container_delta),amount_delta_minor});
      toast('Owner correction appended to audit trail');await render();return customerDetail(o.customer_id);
    }
    if(form.id==='create-location'){const c=o.customer_id;await api('/locations','POST',{customer_id:c,label:o.label,lat:Number(o.lat),lon:Number(o.lon)});toast('Destination registered');return customerDetail(c);}
    if(form.id==='create-order'){const [customer_id,location_id]=o.destination.split('|');await api('/orders','POST',{customer_id,location_id,requested_qty:Number(o.requested_qty)});toast('Order created with price snapshot');return render();}
    if(form.id==='change-month'){state.month=o.month;return render();}
    if(form.id==='record-payment'){const amount_minor=Math.round(Number(o.amount)*100);await api('/billing/payments','POST',{customer_id:o.customer_id,order_id:o.order_id||null,amount_minor,method:o.method,reference:o.reference});toast(o.order_id?'Order payment recorded; linked statuses updated':'Unallocated customer payment recorded');return render();}
  }catch(err){toast(err.message,true)}
});
(async()=>{if(state.token){try{state.actor=await api('/me');state.page=state.actor.role==='OWNER'?'dashboard':'orders';await render()}catch(e){state.token='';sessionStorage.removeItem('refillops-key');authScreen()}}else authScreen()})();

// Local multi-role demo: periodically refresh the connected order views. Never
// replace an active form/modal while someone is entering a business transaction.
let orderRefreshInFlight=false;
setInterval(async()=>{
  if(orderRefreshInFlight || !state.actor || state.page!=='orders' || modalHost.firstElementChild || document.hidden) return;
  const el=document.activeElement;
  if(el && ['INPUT','TEXTAREA','SELECT'].includes(el.tagName)) return;
  orderRefreshInFlight=true;
  try{await orders();}catch(_err){/* next navigation retains normal error display */}
  finally{orderRefreshInFlight=false;}
},10000);
