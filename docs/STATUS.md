# Implementation status

**Scope:** Local, fictional, single-station portfolio demonstration. Not production-ready.

- API and SQLite schema: implemented for local demo; validation via automated tests.
- Local bearer-key demo identities: implemented; only locally generated keys; not full production authentication.
- Customer destination identifiers: numeric alias lookups and revocable opaque token resolution implemented; rendering/scanning QR images is not yet implemented.
- Straight-line service-radius checks: implemented.
- Delivery state machine, atomic confirmation, container movements and charges, idempotent duplicate completion: implemented.
- Owner dashboard, manual payment, audited owner corrections, invoice issue/detail, audit and exceptions: basic implemented endpoints.
- Browser UI: simple working operator console; not polished or reviewed with real users.
- Real customer login, real payments, route planning, SMS, offline delivery queue, public hosted mutable access: excluded.
- No real station deployments, live user trials, performance assurances, or commercial claims.

See `docs/PRD.md` for intended requirements. The PRD is a proposed baseline and is not a statement of release maturity.


- v0.1.1: Replaced unsupported native browser prompt/confirm calls in five
  operation actions with in-page dialogs; exception review notes still create
  server-side audit entries. This is a UI compatibility fix, not a release claim.

- v0.1.2: Customer directory displays linked order counters; customer detail shows
  per-order lifecycle and delivered/returned quantities. Created orders do not
  prematurely change balance or container positions. Existing local data is kept.

## v0.1.3 — customer / house semantics

- V1 house = delivery location, linked to a customer account through existing station-scoped FK.
- Separate fictional customer names from house labels in fresh seeds; optional non-destructive relabel command for original fictional seed.
- Customer list and order screens show the relationship explicitly; no new tables or billing migrations.

## v0.1.4 — order-centric linked status

- Each order has a stable `RO-000001`-style Order Number, distinct from immutable internal UUID. Older local orders are numbered by a non-destructive upgrade.
- Owner/staff, assigned rider, and **read-only synthetic customer demo** see the same server-derived order delivery and payment statuses.
- Delivered `COMPLETED` orders carry `UNPAID`, `PARTIALLY_PAID` or `PAID` based only on order-specific payment allocations. Before delivery, payment is `NOT_DUE`.
- Existing customer-level receipts remain **unallocated** and are never silently assumed to have paid a particular order.
- Invoice lines, audit events and customer financial records expose shared Order Number where applicable.
- Local Orders page polls approximately every 10 seconds when idle. This is not production real-time infrastructure.
- The `upgrade` CLI command backs up existing local SQLite data, migrates order references and issues separate private demo customer keys without reseeding.
- Read-only customer role is **local-demo extension** to the PRD's original V1 scope, not production customer authentication or a live customer portal.
- See [Order-Centric Relational Management](ORDER_RELATIONSHIPS.md) for design, status semantics, and acceptance checks.

## v0.1.5 — Dark / Light / System theme

- Refactored the stylesheet into complete, correctly scoped CSS rules; removed malformed nesting in responsive and print rules.
- Introduced shared theme tokens for the sidebar, navigation, forms, tables, badges, and in-page dialogs.
- Added a persistent browser appearance selector and support for OS-level color-scheme preference.
- No database migrations, additional access permissions, or business workflow changes.
