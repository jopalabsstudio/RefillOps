"""Local-only demonstration API. Do not host this with real data or shared demo keys."""
from pathlib import Path
from typing import Annotated
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from refillops import service
from refillops.auth import current_actor, require

app = FastAPI(title='RefillOps — Fictional Local Demo', version='0.1.5',
              description='Portfolio demonstration with synthetic records; no live operations or payments.')
Actor = Annotated[dict, Depends(current_actor)]


@app.exception_handler(service.AppError)
def business_error(_request: Request, exc: service.AppError):
    return JSONResponse(status_code=exc.status, content={'detail': exc.message})


@app.middleware('http')
async def local_only(request: Request, call_next):
    # Local test runner has host "testclient". This is not a production security boundary.
    if not request.client or request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
        return JSONResponse(status_code=403, content={'detail': 'RefillOps demo is local-only; do not expose it publicly'})
    return await call_next(request)


class CustomerIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    opening_containers: int = Field(default=0, ge=0, le=100000)


class LocationIn(BaseModel):
    customer_id: str
    label: str = Field(default='Home', max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class AliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=12)


class TokenIn(BaseModel):
    token: str = Field(min_length=1)


class OrderIn(BaseModel):
    customer_id: str
    location_id: str
    requested_qty: int = Field(gt=0, le=10000)


class AssignIn(BaseModel):
    rider_id: str


class CompleteIn(BaseModel):
    delivered_qty: int = Field(gt=0, le=10000)
    returned_empties_qty: int = Field(ge=0, le=10000)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PaymentIn(BaseModel):
    customer_id: str
    amount_minor: int = Field(gt=0, le=100_000_000)
    method: str = Field(min_length=1, max_length=100)
    reference: str = Field(default='', max_length=200)
    order_id: str | None = None


class InvoiceIn(BaseModel):
    customer_id: str
    month: str


class AdjustmentIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    container_delta: int = Field(default=0, ge=-100000, le=100000)
    amount_delta_minor: int = Field(default=0, ge=-100_000_000, le=100_000_000)


class ReviewIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)


@app.get('/api/health')
def health():
    return {'status': 'local-demo', 'disclaimer': 'fictional data, not production-ready'}


@app.get('/api/me')
def whoami(actor: Actor):
    return actor


@app.get('/api/station')
def station(actor: Actor):
    return service.station(actor)


@app.get('/api/riders')
def riders(actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.riders(actor)


@app.get('/api/customers')
def customers(actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.list_customers(actor)


@app.post('/api/customers', status_code=201)
def create_customer(body: CustomerIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.create_customer(actor, body.display_name, body.opening_containers)


@app.get('/api/customers/{customer_id}')
def customer_detail(customer_id: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.get_customer(actor, customer_id)


@app.post('/api/customers/{customer_id}/portal-access', status_code=201)
def customer_access(customer_id: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.issue_customer_access(actor, customer_id)


@app.post('/api/customers/{customer_id}/adjustments', status_code=201)
def adjust_customer(customer_id: str, body: AdjustmentIn, actor: Actor):
    require(actor, 'OWNER')
    return service.post_owner_adjustment(actor, customer_id, body.reason, body.container_delta, body.amount_delta_minor)


@app.post('/api/locations', status_code=201)
def location(body: LocationIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.create_location(actor, body.customer_id, body.label, body.lat, body.lon)


@app.post('/api/locations/{location_id}/tokens', status_code=201)
def location_token(location_id: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.create_token(actor, location_id)


@app.post('/api/locations/aliases/resolve')
def resolve_alias(body: AliasIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF', 'RIDER')
    return service.resolve_alias(actor, body.alias)


@app.post('/api/locations/tokens/resolve')
def resolve_token(body: TokenIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF', 'RIDER')
    return service.resolve_token(actor, body.token)


@app.post('/api/locations/tokens/{token_id}/revoke')
def revoke_token(token_id: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.revoke_token(actor, token_id)


@app.get('/api/orders')
def orders(actor: Actor):
    return service.orders(actor)


@app.get('/api/orders/{order_id}')
def get_order(order_id: str, actor: Actor):
    return service.get_order(actor, order_id)


@app.post('/api/orders', status_code=201)
def create_order(body: OrderIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.create_order(actor, body.customer_id, body.location_id, body.requested_qty)


@app.post('/api/orders/{order_id}/assign')
def assign(order_id: str, body: AssignIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.assign_order(actor, order_id, body.rider_id)


@app.post('/api/orders/{order_id}/dispatch')
def dispatch(order_id: str, actor: Actor):
    require(actor, 'RIDER')
    return service.dispatch_order(actor, order_id)


@app.post('/api/orders/{order_id}/complete')
def complete(order_id: str, body: CompleteIn, actor: Actor,
             idempotency_key: Annotated[str | None, Header(alias='Idempotency-Key')] = None):
    require(actor, 'RIDER')
    if not idempotency_key:
        raise HTTPException(422, 'Idempotency-Key header is required')
    return service.complete_order(actor, order_id, body.delivered_qty, body.returned_empties_qty, idempotency_key)


@app.post('/api/orders/{order_id}/cancel')
def cancel(order_id: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.cancel_order(actor, order_id)


@app.post('/api/orders/{order_id}/fail')
def fail(order_id: str, body: ReasonIn, actor: Actor):
    require(actor, 'RIDER')
    return service.fail_order(actor, order_id, body.reason)


@app.get('/api/deliveries')
def deliveries(actor: Actor):
    require(actor, 'RIDER')
    return service.orders(actor)


@app.get('/api/billing/preview')
def billing(month: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.billing_preview(actor, month)


@app.post('/api/billing/payments', status_code=201)
def payment(body: PaymentIn, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.post_payment(actor, body.customer_id, body.amount_minor, body.method, body.reference, body.order_id)


@app.post('/api/billing/invoices', status_code=201)
def invoice(body: InvoiceIn, actor: Actor):
    require(actor, 'OWNER')
    return service.issue_invoice(actor, body.customer_id, body.month)


@app.get('/api/billing/invoices/{invoice_id}')
def get_invoice(invoice_id: str, actor: Actor):
    require(actor, 'OWNER', 'STAFF')
    return service.invoice_detail(actor, invoice_id)


@app.get('/api/dashboard')
def dashboard(actor: Actor):
    require(actor, 'OWNER')
    return service.dashboard(actor)


@app.get('/api/exceptions')
def exceptions(actor: Actor):
    require(actor, 'OWNER')
    return service.list_exceptions(actor)


@app.post('/api/exceptions/{exception_id}/review')
def exception_review(exception_id: str, body: ReviewIn, actor: Actor):
    require(actor, 'OWNER')
    return service.review_exception(actor, exception_id, body.note)


@app.get('/api/audit')
def audit(actor: Actor):
    require(actor, 'OWNER')
    return service.audit_history(actor)


STATIC = Path(__file__).parent / 'static'
app.mount('/static', StaticFiles(directory=str(STATIC)), name='static')


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(STATIC / 'index.html')
