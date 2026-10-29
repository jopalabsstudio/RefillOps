# RefillOps — Public Portfolio Product Requirements Document

**Document status:** Proposed baseline · **Version:** 0.1 · **Date:** 2026-10-28\
**Owner:** JoPa Labs Studio · **Project:** RefillOps · **Audience:** Engineering, reviewers, hiring teams, pilot stakeholders\
**Repository intent:** Public, source-visible, independently runnable portfolio application using **fictional demo data only**.\
**Related:** [`FOLDER_FILE_MAP.md`](./FOLDER_FILE_MAP.md), [`BUILD_ORDER.md`](./BUILD_ORDER.md), [`adr/0001-public-commercial-boundary.md`](./adr/0001-public-commercial-boundary.md)

> **Status clarity:** This PRD specifies the intended product. It does not claim that its features are implemented, deployed, or validated with real stations.

## 1. Executive summary

RefillOps is a responsive operations application for neighborhood water-refilling stations. It connects owners, station staff, and delivery riders in a traceable workflow covering customers, pinned delivery destinations, order assignments, delivery confirmation, container exchanges, monthly billing, and exception monitoring.

**North star:** A station owner can understand the day's operations and identify what needs attention without being physically present or manually checking every transaction.

**Foundational insight:** A QR/number identifies a **customer delivery destination/account**, not an individual refillable water gallon. Gallons may be swapped freely. Delivery, empty-return, billing, and payment movements remain tied to the correct customer and transaction.

**Positioning:** A working business operations demonstration, not just a dashboard mockup, generic delivery tracker, or proof-of-concept claiming production readiness.

## 2. Problem and opportunity

A small water station may use paper slips, messages, phone calls, and manual spreadsheets to track orders and balances. This creates gaps in four areas:

- **Dispatch visibility:** Which orders are pending, assigned, in transit, completed, or failed?
- **Container accountability:** How many full containers were delivered and empties returned for each customer?
- **Billing accuracy:** Which completed quantities were charged, invoiced, and paid, without duplicate charges?
- **Owner oversight:** Can exceptions be surfaced without micromanaging every rider and staff member?

RefillOps targets this operational chain with one auditable source of truth.

## 3. Product goals and success criteria

| ID | Goal                                    | Acceptance evidence for the public V1                                                                   |
| -- | --------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| G1 | Demonstrate an end-to-end workflow      | A demo order can be created, assigned, dispatched, completed, charged, and seen on the dashboard.       |
| G2 | Preserve correct identities             | QR/location code resolves to a delivery location; it never identifies an individual gallon.             |
| G3 | Prevent accidental duplicate accounting | Repeating a completion request with the same idempotency key does not double-post charges or movements. |
| G4 | Make activity traceable                 | Every material state transition and adjustment has an actor, timestamp, and audit entry.                |
| G5 | Demonstrate absentee-owner operations   | Owner dashboard shows status counts, pending items, basic exceptions, and billing position.             |
| G6 | Be verifiable by reviewers              | Setup, seeded synthetic data, automated tests, and a demo script are documented.                        |
| G7 | Keep commercial options open            | No private production rules, sensitive data, or private dependencies are required to run public V1.     |

**Portfolio definition of done:** A reviewer can clone the repository, follow documented commands, load fictional sample data, complete the walkthrough, and run tests without private credentials other than locally generated configuration.

## 4. Users, roles, permissions

| Role         | Primary jobs                                                                        | Allowed scope in public V1                                                                       |
| ------------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **OWNER**    | Review station health, customer balances, billing, and exceptions                   | Read all station activity; authorize adjustments and payments; view audit history.               |
| **STAFF**    | Register customers/destinations, create orders, assign riders, record payment       | Manage customer and order workflow for their authorized station; no privileged ledger overrides. |
| **RIDER**    | View assigned stops, validate destination, record delivered and returned quantities | Read own assigned jobs; dispatch/complete/fail assigned deliveries; no pricing edits.            |
| **CUSTOMER** | Eventually order, view deliveries and billing                                       | **Not a login role in V1.** Staff represents customer requests.                                  |

Roles are enforced **on the server**, not by hiding UI buttons. Demo role switching must never grant access to real records.

## 5. Scope

### 5.1 Must-have public V1 (P0)

1. **Single-station configuration:** one demonstrable station, a service-area center, a configurable starting radius of approximately **1.5 km**, local timezone, and price per delivered gallon.
2. **Customer directory:** create/list/view customer records, delivery location(s), and status. V1 can start with one active location per customer while modeling locations separately.
3. **Location-based QR/number:** opaque, revocable destination token or numeric alias resolving to a location within an authorized staff/rider session. Do not encode name, address, coordinates, or invoice data in QR payload.
4. **Delivery orders:** create an order with requested gallon quantity, customer and destination, a price snapshot, and initial state. Assign rider, dispatch, complete, fail, or cancel under defined transition rules.
5. **Delivery confirmation:** record full gallons delivered and empty containers returned as **separate values**, along with actor and time. Completion is a single atomic operation with idempotency protection.
6. **Customer container position:** outstanding-container balance derived from opening position and confirmed container movements; flag suspicious negative positions for review rather than silently rewriting history.
7. **Basic customer account ledger:** post delivery charges for completed quantities; separately record manual payments and approved corrections; expose amount due. No payment processor in V1.
8. **Monthly billing preview and invoices:** aggregate eligible charges within a selected calendar month and station timezone; ensure an entry cannot be invoiced twice. Provide printable/readable invoice summary.
9. **Owner dashboard:** orders by status, deliveries completed today, billable activity, account receivables, and a basic exception queue.
10. **Audit trail and guards:** role checks, validation, server-side station scoping, append-only material audit events, data consistency, and representative automated tests.
11. **Public demo experience:** seeded **fictional** station/customers/users, documented walkthrough, repeatable reset and local setup.

### 5.2 Should-have following V1 (P1)

- Customer request portal and status viewing.
- Rider-focused mobile/PWA ergonomics and optional offline queue with safe replay.
- Configurable delivery windows; route sequencing and map-based stop planning.
- Notifications (SMS/email/chat) with consent and rate limiting.
- PDF invoice export and optional CSV reporting.
- Station inventory for filled stock and refill production.

### 5.3 Intentionally excluded from public V1

- Live payment gateway, production integrations, real customer records, and real-location tracking.
- Automatic inference of water **consumed** from water **delivered** (consumption is not directly observed).
- Individual gallon serialization/tracking; container shells are interchangeable.
- Multi-station SaaS tenancy, subscription billing, enterprise administration, advanced routing optimization, proprietary fraud/risk scoring, or AI-driven operational recommendations.
- Guarantee of regulatory, accounting, or operational fitness for an actual commercial station.

## 6. Core domain rules (non-negotiable)

| Rule                        | Decision / invariant                                                                                                                                              |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ID-01: Destination identity | QR or location number maps to a **delivery location record**. It does not map to a physical gallon.                                                               |
| ID-02: Gallon exchange      | Containers can be swapped; only quantities of delivered full gallons and returned empties are recorded.                                                           |
| ID-03: Distinct measures    | `requested`, `delivered`, `returned_empties`, `billed`, `paid`, and `consumed` are different measures. V1 does **not** assert consumed quantity.                  |
| ID-04: Historical pricing   | The unit price applicable to an order is captured when the order is created/confirmed per documented policy; later price changes do not silently rewrite charges. |
| ID-05: Completion atomicity | Completing a delivery and posting container/financial movements succeed or fail as one database transaction.                                                      |
| ID-06: Idempotency          | A retried completion command cannot create duplicate movements, charges, or invoices.                                                                             |
| ID-07: Auditability         | Never silently edit completed delivery movements or issued charges. Corrections post compensating entries with reasons, authorization, and audit records.         |
| ID-08: Station isolation    | Every domain read/write is scoped to the authorized station, even though public V1 demonstrates one station.                                                      |
| ID-09: Service-area meaning | The 1.5 km value is an **initial straight-line geographic radius**, not guaranteed road travel distance. Show this distinction in UX/docs.                        |
| ID-10: Quantity semantics   | Positive integer gallon quantities for a successful delivery; `returned_empties` may differ from `delivered`, subject to container-balance checks.                |
| ID-11: Safe demo            | Publicly accessible demos use fictional data. Mutable public demos must be resettable or isolated per visitor; read-only demo mode is acceptable initially.       |

**Container example:** Customer balance starts at 2 outstanding empties. Rider delivers 3 full gallons and collects 2 empties. New outstanding-container position = `2 + 3 - 2 = 3`. Billing uses the 3 delivered gallons, subject to the recorded unit price, not the empty-return count.

## 7. Key workflows

### WF-01 — Register a destination

1. Staff creates or selects a customer.
2. Staff pins a delivery location; system stores its lat/long in the **demo database only for fictional locations**.
3. System checks distance from station against the configured service radius.
4. System creates a random opaque location token and/or non-sensitive numeric alias; QR references the token.
5. Authorized rider/staff can scan the token to resolve the correct customer destination. Unknown or revoked tokens fail safely.

**Acceptance:** Scanning the same valid location QR resolves the location regardless of which physical container is delivered; token contents do not reveal customer PII.

### WF-02 — Create, assign, dispatch, and complete an order

1. Staff selects destination, enters requested quantity, confirms price snapshot, and creates order (`CREATED`).
2. Staff assigns a rider (`ASSIGNED`).
3. Rider starts the trip (`OUT_FOR_DELIVERY`).
4. Rider verifies destination, records `delivered_qty` and `returned_empties_qty`, and confirms (`COMPLETED`).
5. In **one transaction**, system records confirmation, container movements, a charge ledger entry, and an audit event.
6. Dashboard updates using committed data only.

**Permitted transitions:** `CREATED -> ASSIGNED -> OUT_FOR_DELIVERY -> COMPLETED`; `CREATED|ASSIGNED|OUT_FOR_DELIVERY -> CANCELLED` with documented authorization, provided completion has not happened; `OUT_FOR_DELIVERY -> DELIVERY_FAILED` with reason and authorized re-assignment path. The service enforces this state machine.

**Acceptance:** A second identical completion request produces the original result without duplicate accounting. Completing a cancelled or already-completed order with a different payload fails safely.

### WF-03 — Monthly billing and payments

1. A completed delivery creates a charge associated with the customer, order, quantity, price snapshot, and station.
2. Owner/staff can record a manual payment with amount, method label, and reference (no external payment processor).
3. Billing preview shows the month's eligible charges and recorded payments, with opening/closing balance logic explained.
4. Owner issues an invoice; invoice lines reference posted charges and cannot be included in a second issued invoice.
5. Corrections are compensating entries with reasons and owner approval, not destructive edits.

**Acceptance:** Invoice totals reconcile with linked ledger items; paid and billed quantities/amounts remain separately visible; month boundary uses station-local dates.

### WF-04 — Exception handling and remote owner oversight

1. A basic rules engine produces exceptions for demo conditions, e.g. unassigned aging orders, container return anomalies, failed attempts, or unauthorized transition attempts (with the latter also security-logged).
2. Owner dashboard provides exception type, severity, order/customer context, and current status.
3. Owner can mark a business exception reviewed with a note; original transaction is unchanged.
4. Each review action is audited.

**Acceptance:** The demo seed includes at least one reproducible exception; the owner can explain its source and resolution from the UI.

## 8. Functional requirements and verification

| ID     | Requirement                                                    | Acceptance test                                                                                    |
| ------ | -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| FR-001 | Store one demo station, configured radius, timezone and prices | Setup seeds a station; owner can view configuration.                                               |
| FR-010 | Create/list customer and delivery-location records             | Valid input persists; invalid coordinates/empty required fields are rejected.                      |
| FR-011 | Generate and revoke location QR tokens                         | Valid token resolves only under authorization; revoked token fails.                                |
| FR-012 | Calculate service-radius eligibility                           | Inside/outside test fixtures yield expected straight-line distance results; boundaries documented. |
| FR-020 | Create order with quantity and price snapshot                  | Order contains reference, destination, unit price, state and actor.                                |
| FR-021 | Assign/dispatch under role and state guards                    | Disallowed actor/transition returns an error with no state change.                                 |
| FR-030 | Confirm delivery atomically                                    | Completion, movements, charge and audit entry commit together or roll back together.               |
| FR-031 | Make completion idempotent                                     | Retrying same key returns same result and creates no duplicate entries.                            |
| FR-032 | Track container positions by customer                          | Starting balance + deliveries - returned empties matches displayed balance.                        |
| FR-040 | Post and display charges, payments and approved corrections    | Account balance equals sum of signed ledger entries.                                               |
| FR-041 | Preview/issue monthly invoice without double-invoicing         | Linked charge entry appears in at most one issued invoice; totals reconcile.                       |
| FR-050 | Provide owner dashboard and exception queue                    | Seeded activity matches aggregate counts; one reproducible exception visible.                      |
| FR-060 | Enforce OWNER/STAFF/RIDER authorization server-side            | API test shows unauthorized access rejected, including cross-station identifier attempts.          |
| FR-061 | Audit material actions with actor/time/context                 | Create, assign, complete, issue invoice, and adjustment all write audit entries.                   |
| FR-070 | Deliver synthetic seed data, tests, and walkthrough            | Fresh clone can initialize DB, seed, run automated tests and complete demo.                        |

## 9. Screens and navigation

| Screen / route                             | Audience                     | Essential UI                                                                              |
| ------------------------------------------ | ---------------------------- | ----------------------------------------------------------------------------------------- |
| `/`                                        | Public visitor               | Product explanation, screenshots, repository and demo access; no false production claims. |
| `/demo`                                    | Reviewer                     | Demo instructions, role access method, reset policy, fictional-data warning.              |
| `/dashboard`                               | Owner                        | Today's activity, exceptions, receivables, key counts.                                    |
| `/customers` and `/customers/[customerId]` | Owner, Staff                 | Customer directory, delivery location, container position, charge/payment history.        |
| `/orders` and `/orders/[orderId]`          | Owner, Staff, assigned Rider | Order list/details, authorized actions and state changes.                                 |
| `/deliveries`                              | Rider, Staff                 | Assigned deliveries, destination verification, quantity confirmation.                     |
| `/billing`                                 | Owner, Staff (role-limited)  | Month picker, billing preview, invoices, payment records.                                 |
| `/exceptions`                              | Owner                        | Review queue and resolution notes.                                                        |
| `/audit`                                   | Owner                        | Read-only material action history.                                                        |

The landing page is **public-facing**; operational pages require appropriate demo or authenticated access.

## 10. Data model (conceptual)

- `Station`: ID, public/demo name, reference coordinates, service radius, currency, timezone.
- `User`: ID, station ID, role, status; auth material handled separately.
- `Customer`: ID, station ID, display name, optional fictional contact info, opening container position.
- `DeliveryLocation`: ID, station ID, customer ID, label, pin, active state; may have an alias.
- `LocationToken`: ID, station ID, delivery-location ID, opaque token hash, revoked timestamp.
- `DeliveryOrder`: ID, station/customer/location IDs, requested qty, unit price snapshot, status, assigned rider, creator, timestamps.
- `DeliveryConfirmation`: order ID (unique), delivered qty, returned empties, confirmed by, timestamp, request key.
- `ContainerMovement`: station/customer/order IDs, signed quantity, kind (`FULL_DELIVERED` / `EMPTY_RETURNED` / `ADJUSTMENT`), timestamp.
- `AccountEntry`: station/customer/order IDs, signed amount, kind (`CHARGE` / `PAYMENT` / `CREDIT` / `ADJUSTMENT`), reason/reference, timestamp.
- `Invoice` / `InvoiceLine`: station/customer, billing window, status, immutable issued totals, link to eligible account charge entries.
- `Exception`: station, linked entity, type, severity, state, owner note, timestamps.
- `AuditEvent`: station, actor, action, target, safe metadata, created timestamp.
- `IdempotencyRecord`: station, command, key, payload fingerprint, stored outcome.

**Relational safeguards:** unique delivery confirmation per order, unique invoice linkage for posted charge entries, unique idempotency namespace per station/action/key, and foreign keys covering station-scoped resources. Database transactions enforce monetary and movement invariants. Use integer minor currency units (e.g., Philippine centavos) rather than floating-point amounts.

## 11. API behavior guidelines

- HTTP JSON endpoints under `/api`. Parse and validate input server-side; derive station scope from the authenticated/demo session, never blindly trust `stationId` from a browser payload.
- Creation endpoints return stable IDs; invalid input returns 400/422; unauthenticated 401; forbidden 403; conflicting state/idempotency payload 409; not found/unauthorized object access 404 or consistent forbidden policy.
- POST completion requires an idempotency key; same key/same canonical payload returns prior outcome. Same key/different payload returns conflict.
- Record timestamps in UTC; compute daily/monthly reporting boundaries in station-configured timezone.
- All material state mutations write audit entries inside the relevant transaction where practical.
- No client-side calculation is the accounting authority. Backend is authoritative for charges, balances, and status transitions.

See file responsibilities and route mapping in [`FOLDER_FILE_MAP.md`](./FOLDER_FILE_MAP.md).

## 12. Non-functional requirements

| Category       | V1 target / gate                                                                                                                                                                 |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Security       | Server-enforced RBAC, session controls, scoped queries, rate limits on exposed mutations, input validation, no committed secrets, QR token entropy and revocation.               |
| Privacy        | Only fake customer names/locations in public seed or hosted demo. No real rider GPS history. Access to operational data is restricted.                                           |
| Data integrity | Transactional delivery posting, immutable financial/movement history plus compensating corrections, database constraints and idempotency.                                        |
| Accessibility  | Keyboard operability, accessible labels, semantic UI, visible validation and status changes.                                                                                     |
| Responsiveness | Desktop owner dashboard and mobile rider workflow; avoid requiring a mobile app installation.                                                                                    |
| Reliability    | Explicit error, retry, and conflict states; seed/reset scripts safe for demo-only databases.                                                                                     |
| Testing        | Unit tests on state machine, container math, charge math, distance, exception rules; DB-backed integration tests on transaction/idempotency/permissions; end-to-end golden path. |
| Operations     | Local dev with documented DB setup; migration and seed commands; CI lint/typecheck/test/build.                                                                                   |

**Performance:** Keep the dashboard and rider action flows responsive for seed-sized data; measure actual timings before publishing numeric performance claims. Avoid invented latency/availability guarantees.

## 13. Demo data and story

Use clearly synthetic identities and a fictional neighborhood/station. Seed at least:

- 1 station, 1 owner, 2 staff accounts, 2 riders.
- 8–12 customers with synthetic pinned locations inside/near a demonstration radius.
- 1 unassigned order, 1 assigned order, 1 in-transit order, 3 completed deliveries, 1 failed attempt.
- Non-equal delivered/returned counts to demonstrate container balances.
- Charges and one manual payment yielding a nonzero receivable; 1 issued invoice and 1 previewable month.
- 1 visible owner exception with an explained reason.

**Golden demo:** create customer and pin -> generate destination QR -> create order for 3 -> assign -> dispatch -> complete with 3 delivered and 2 empties returned -> see customer balance and charge -> preview monthly invoice -> owner dashboard/exception view. Include a test for duplicate completion request.

A hosted public demo should default to **read-only or disposable isolated sessions**; do not share a persistent writable owner database with anonymous visitors.

## 14. Milestones and release gates

| Milestone                    | Delivery outcome                                                                         | Exit gate                                                            |
| ---------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| M0 — Foundation              | Docs, repository, tooling, schema, dev DB, seed, roles                                   | Local setup reproducible; CI scaffold green.                         |
| M1 — Identity & destinations | Customer/location CRUD, QR token, radius validation                                      | Scan resolves only valid authorized destination; tests pass.         |
| M2 — Delivery vertical slice | Order create/assign/dispatch/complete; movements and charge                              | Atomic/idempotent end-to-end flow passes integration tests.          |
| M3 — Owner visibility        | Dashboard, audit log, simple exception rules                                             | Owner can explain a completed delivery and investigate an exception. |
| M4 — Billing & public polish | Payment posting, monthly preview/invoice, landing page, screenshots, README, walkthrough | All FR-070 steps pass on a clean environment; no secret/PII leak.    |

### Public release checklist

- Repository structure and docs reflect implemented behavior; no aspirational screenshot labeled as working.
- Fresh clone installs, migrates, seeds, starts and passes lint/typecheck/unit/integration/e2e instructions.
- No `.env.local`, real customer data, secrets, backups, or private commercial packages in commit history.
- Basic role-denial, QR token revocation, wrong-station ID, duplicate completion and double-invoicing tests pass.
- Clearly marked demo dataset, safety/reset behavior, status of deployment and known limitations.
- Public legal/licensing position consciously chosen before announcing reuse rights.

## 15. Risks and mitigations

| Risk                                     | Mitigation                                                                                             |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Scope creeps into fleet SaaS             | Limit first public implementation to one station and one deterministic delivery-to-billing path.       |
| Billing becomes inaccurate               | Use integer minor units, price snapshots, atomic posting, immutable records, and reconciliation tests. |
| QR leaks or grants broad access          | Store random revocable token; require role checks; keep token free of PII.                             |
| Real-world privacy exposure              | Seed only fictional locations; do not import real records to public deployments.                       |
| Reviewer thinks demo is production-ready | Label it portfolio/demo and document limitations and unimplemented features.                           |
| Public demo vandalism                    | Read-only shared showcase or isolated auto-reset demo sessions.                                        |
| Commercial advantage leaked accidentally | Separate private codebases before development; never reference private imports in the public build.    |

## 16. Open decisions before implementation

1. **Demo access:** read-only hosted view vs isolated interactive demo instances. Recommendation: local fully interactive demo first; hosted read-only until isolation/reset is built.
2. **Authentication:** select a maintained session solution and a development-only demo identity mechanism; production and public deployment must not rely on a role selector as authorization.
3. **Price rules:** fixed station price at order creation for V1; decide later whether delivery fees, discounts, credits, and deposits are supported.
4. **Container accounting:** opening balances editable only through audited owner adjustment; handling of more empties returned than outstanding must be explicit.
5. **Customer contacts:** omit or fake contact details in demo; obtain privacy review before any real pilot.
6. **License:** public visibility does not itself grant an open-source license. Choose an explicit license if public reuse/contributions are desired; otherwise document the reserved-rights stance without claiming open-source status.

## 17. Final V1 decision

**Build the public repo as a complete, runnable core workflow, not a UI shell.** Keep the future proprietary modules out of the repository entirely. The strongest portfolio proof is deterministic business logic, working APIs, auditable data, automated tests, and a clearly documented demonstration.
## 18. Post-baseline change record — order-centric relational status (v0.1.4)

This is an approved **local demo extension** to the original v0.1 requirements, not a claim that the customer portal is production-ready.

- An immutable, station-unique human-readable Order Number is the common transaction reference across Owner/Staff, assigned Rider, Customer demo views, invoice lines and relevant audit entries. Internal UUIDs remain database keys.
- Delivery state is visible as Ordered, Out for Delivery, Delivered (plus Failed/Cancelled), independent of a payment state Not Due, Unpaid, Partially Paid or Paid.
- A confirmed delivery creates its charge atomically. Paid/Unpaid on the **order** reflects only receipts explicitly allocated to that order. Existing customer-level unallocated payments retain their meaning and are not automatically assigned to any order.
- Local demo customer access is read-only and strictly scoped to the customer identity through separate generated access keys; it does not constitute production customer authentication. Customers cannot create orders in this demo.
- Staff/owner can record order-linked manual payments in the authorized station. Riders cannot record payments.
- Details: `docs/ORDER_RELATIONSHIPS.md`.
