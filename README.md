# RefillOps

**One station. Every delivery accounted for.**

RefillOps is a **locally runnable, fictional, source-visible portfolio demonstration** of operations software for a neighborhood water-refilling station. It helps tell the operational story from customer destination registration to rider dispatch, delivery confirmation, container exchanges, account ledger, monthly invoices, exceptions, and remote owner oversight.

> **Status: local portfolio demo, not production-ready.** It does not process live payments, manage real customer data, host a secure public multi-user tenant environment, or claim actual station validation. See [implementation status](docs/STATUS.md).

## The important difference

A QR/token or numeric alias belongs to a **delivery destination**, *not* to a physical water gallon. Containers can be exchanged freely. RefillOps tracks **delivered full gallons**, **returned empties**, **outstanding containers**, **billed quantities**, and **paid amounts** separately. Water consumed by a household cannot be inferred reliably from deliveries alone.

## Customer ↔ house relationship

A **Customer** is an account holder and billing identity. A **House** is a pinned delivery
location (stored in `delivery_locations`) with its own QR / numeric alias. In V1, one
customer may have multiple houses, while each house belongs to exactly one accountable
customer. Each order contains both customer and destination IDs, and the API rejects
orders where they do not match. Billing and container positions remain on the customer
account; a new order does not itself record a delivery or a charge.

For fictional seed data, the entities are now named separately: `Sample Customer A`
receives orders at `Sample House A`. For an **existing local demo created before v0.1.3**,
stop the server and optionally run the **non-destructive** command below. It only relabels
matching original fictional samples and preserves IDs, orders, account balances, and keys:

```powershell
.\.venv\Scripts\python.exe -m refillops.cli relabel-demo
```

Do **not** run `seed --reset` to update labels: that would erase your locally entered demo
records. Multi-account shared households and changing the responsible billing customer
are out of scope for this first relationship model.

## What you can demonstrate

- Create customers and fictional pinned delivery locations within a default **1.5 km straight-line** service radius.
- Generate opaque, revocable location tokens and numeric aliases; authorization is required to resolve either.
- Create an order with a price snapshot, assign it, dispatch it, and confirm actual delivered/returned quantities.
- Commit confirmation, container movement, charge, and audit events in **one transaction**.
- Retry completion with the same idempotency key without double-billing.
- Record manual payments and owner-approved append-only adjustments; preview station-timezone billing and issue unique monthly invoice lines with a readable summary.
- Inspect owner dashboard counts, exceptions, immutable material audit history.

### Local setup

Requires **Python 3.11+**. Windows PowerShell:

```powershell
cd RefillOps
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m refillops.cli seed
python -m refillops.cli serve
```

macOS / Linux:

```bash
cd RefillOps
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m refillops.cli seed
python -m refillops.cli serve
```

Visit **http://127.0.0.1:8000/**. Open `.local/demo_access.json` and paste a generated key (Owner, Staff, Rider, or a read-only fictional Customer) into the browser console login. **Never commit, upload, or share this local key file.** Switch role to see different workflows.

Optional developer API documentation: **http://127.0.0.1:8000/docs**. All privileged operations need an `Authorization: Bearer <generated-key>` header.

To reset **only the configured local demo database**, run:

```bash
python -m refillops.cli seed --reset
```

The seed includes fictional people/locations, orders at multiple statuses, completed deliveries, a payment, an issued invoice, and reproducible exceptions.

### Automated verification

```bash
pytest -q
python -m compileall -q src
```

CI repeats the tests on push / pull request. Tests use an independent temporary SQLite database and do not touch your regular demo data.

### Quick example: idempotent delivery confirmation

```text
POST /api/orders/{id}/complete
Authorization: Bearer <rider-key>
Idempotency-Key: <unique-command-key>
Content-Type: application/json

{"delivered_qty": 3, "returned_empties_qty": 2}
```

On success, the backend records **3 full containers delivered**, **2 empties returned**, increases outstanding-container position by **1**, and records a charge based on the order's frozen unit price. Retrying the exact request with the same key returns the original result; a reused key with a changed payload returns conflict.

## Repository architecture

- **FastAPI + Python domain service**: route validation, role enforcement, business invariants, auditable commands.
- **SQLite**: zero-infrastructure local demo with transaction and uniqueness constraints. PostgreSQL could be evaluated for a future pilot; no such pilot is claimed.
- **Accessible HTML/CSS/vanilla JS operator console**: owner, staff and rider tasks, intentionally lightweight; not a standalone native mobile app.
- **Pytest + HTTP integration tests**: critical rules, permission denial, station-scope checks, idempotency, injected rollback failure, invoice uniqueness.

See [folder and file mapping](docs/FOLDER_FILE_MAP.md), [build order](docs/BUILD_ORDER.md), [full PRD](docs/PRD.md), [reviewer demo](docs/DEMO_SCRIPT.md), and [public/commercial boundary decision](docs/adr/0001-public-commercial-boundary.md). For safe publication steps, see [GitHub publishing](docs/GITHUB_PUBLISH.md).

## Safety and deployment constraints

This repository is configured to run only on loopback through the provided CLI. It uses **locally generated bearer keys**, not production identity management. Do **not** serve it through an internet-facing reverse proxy, publish generated keys, connect a live payment gateway, or import customer records. A public showcase should be **read-only** or use separately isolated disposable accounts, which are *not implemented* here.

## Ownership and rights

Created by **JoPa Labs Studio**. Publicly viewable source is not automatically open source. No redistribution/reuse license has been granted; see [RIGHTS.md](RIGHTS.md). Proprietary future features are deliberately kept in a separate private product boundary.


## Browser preview compatibility (v0.1.1)

Operational questions (exception review, delivery confirmation, failed delivery,
order cancellation, invoice issuance) use in-page accessible forms rather than
`window.prompt()` / `window.confirm()`. This allows testing in VS Code browser
previews that block native JavaScript dialogs. No schema migration or reseed is
needed when upgrading from v0.1.0; stop and restart the server and hard refresh
the page to load updated static assets.


## Customer order visibility (v0.1.2)

The Customers directory shows active, completed, and failed order counts for each
customer. **View & manage** includes that customer's order history, status,
requested/delivered/returned quantities, assigned rider, and charge if confirmed.
Creating an order changes the order view immediately, **not** the customer's
financial or container position; those values change only after delivery is
confirmed. This is a read/query + interface update, so no database migration or
reseed is required when upgrading from v0.1.1.

## Order-centric relational status (v0.1.4)

**One Order Number, one authoritative transaction, three perspectives.** Owner, rider and a read-only fictional customer can inspect the **same human-readable Order Number** as the order progresses from **ORDERED → OUT FOR DELIVERY → DELIVERED**. Payment is a **separate** dimension: `NOT DUE` before delivery, then `UNPAID`, `PARTIALLY PAID` or `PAID` based on receipts **explicitly allocated to that order**. This avoids treating an unrelated customer-account payment as proof that a specific delivery was paid.

The owner/staff Billing page can allocate a manual receipt to an Order Number. Rider and customer accounts cannot post payments. Existing legacy receipts remain unallocated; no financial history is rewritten or inferred. Customer demo keys allow read-only access to **only their own orders**; customer-initiated ordering, production login, notifications and payment gateways are not part of this version.

### Upgrade an existing v0.1.3 VS Code project — keep your data

Stop the server (`Ctrl+C`), extract the **v0.1.4 patch** into your RefillOps project folder using **overwrite** (no `.local/` data is bundled), then run:

```powershell
.\.venv\Scripts\python.exe -m refillops.cli upgrade
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m refillops.cli serve
```

`upgrade` creates a local, gitignored SQLite backup, assigns stable Order Numbers to existing orders, and adds local read-only customer keys to `.local/demo_access.json` under **`customers`**, preserving existing `actors` keys. The command can be run again without changing existing references or keys. **Do not reseed** your test database. The Orders page checks for status changes about every 10 seconds while idle.

For first-time setup, the normal `seed` command initializes all v0.1.4 fields and generates the role keys directly. See [Order relationships and acceptance steps](docs/ORDER_RELATIONSHIPS.md).

## Appearance themes (v0.1.5)

The top-right **Theme** menu switches between **Dark**, **Light**, and **System** (follows your operating-system preference). This preference is saved only in the browser and does not affect station records, roles, payment, or order state. Dark is the default for a new browser. The page's styles are served from `/static/styles.css?v=0.1.5`.

**Upgrade from v0.1.4:** Stop the server, overwrite the files in the v0.1.5 patch inside the *existing project root*, and restart. **Do not run `seed` or `upgrade`** for this cosmetic patch. Refresh with `Ctrl+Shift+R`. If the page appears as plain text, open `http://127.0.0.1:8000/static/styles.css?v=0.1.5` directly to check whether CSS is being served.
