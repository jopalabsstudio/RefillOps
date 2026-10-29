# Order-Centric Relational Management (v0.1.4)

**Status:** Implemented in the local fictional demo, not a production deployment. Validate any commercial business rules with station operators before adapting this model to live operations.

## Shared reference

One stable, station-unique **Order Number** (`RO-000001`, `RO-000002`, ...) links:

- the responsible customer/account;
- the house/delivery location (which retains its own permanent location identity and QR/number alias);
- the currently assigned rider and dispatch progress;
- confirmation of full gallons delivered and empties returned;
- the order-specific financial charge and allocated receipt(s);
- related audit activity and invoice line.

The human-readable Order Number is an externally recognizable reference, while the internal immutable order UUID remains the database primary/foreign-key identifier. Two separate orders must never share an Order Number in the same station. Customer, location and rider identities persist across many orders.

## Two independent status dimensions

| Raw operational state | Shown delivery status | Shown payment status |
|---|---|---|
| `CREATED` or `ASSIGNED` | **ORDERED** | **NOT DUE** |
| `OUT_FOR_DELIVERY` | **OUT FOR DELIVERY** | **NOT DUE** |
| `COMPLETED` with zero allocated receipts | **DELIVERED** | **UNPAID** |
| `COMPLETED` with some but insufficient allocated receipts | **DELIVERED** | **PARTIALLY PAID** |
| `COMPLETED` with full allocated receipts | **DELIVERED** | **PAID** |
| `DELIVERY_FAILED` | **DELIVERY FAILED** | **NOT DUE** |
| `CANCELLED` | **CANCELLED** | **NOT DUE** |

Do not make `PAID` an alternative delivery status: delivery and payment can change independently. The business event `COMPLETE_ORDER` posts the delivery, container movements and charge atomically. `PAYMENT_RECORDED` posts a separate signed receipt; for a specified order, an allocation links the receipt and marks payment state **only when fully settled**. Payment authority remains with staff/owner, never the rider or customer.

### Existing customer payments

Receipts created before v0.1.4 are **unallocated** to orders. They remain valid in the customer ledger and customer balance, but the system **does not guess which order was paid**. The staff can select an Order Number for **new** payments. Reconciliation and allocation of historical receipts remains a future, explicitly approved workflow; do not double-post money to force an order to appear paid. In a real commercial product, payment allocation across multiple orders, credits, deposits, returns and payment reversals require operational rules and stronger controls.

## Three views, one authoritative transaction

- **Owner/staff:** all orders in the authorized station, including delivery and payment state and readable Order Number.
- **Rider:** only assigned orders, with the same Order Number and statuses. Rider can dispatch/confirm/fail but cannot post payments.
- **Customer demo:** separately generated read-only credential, only that customer's orders, with the same Order Number and safe status/amount details. The customer cannot see other customers' records or access station finances. Customers cannot create orders in this v0.1.4 demo.

Order views are re-read from the database (and the Orders page refreshes about every 10 seconds when not editing a form). This is **local polling**, not a live messaging, production customer notification or push service.

## Non-destructive upgrade on an existing local demo

1. Stop the local server (`Ctrl+C`).
2. Apply the v0.1.4 patch to the existing repository without replacing `.local/`.
3. Run `python -m refillops.cli upgrade`. The command writes a private local SQLite backup the first time, migrates existing order numbers while retaining original IDs, adds payment allocation and read-only customer key tables, and preserves the existing owner/staff/rider credentials in `.local/demo_access.json`.
4. Run `python -m pytest -q`, followed by `python -m refillops.cli serve`.
5. Under `.local/demo_access.json`, the new top-level `customers` object contains local read-only demo keys for previously registered fictional customers. Use the key for Sample Customer A to inspect only its orders.

**Do not use `seed --reset` when upgrading.** It deletes the active local demo database.

## Manual acceptance path

Use fictional data only. Create a new order, record its Order Number, assign a rider, switch to Rider A/B and dispatch, then confirm 2 delivered / 1 returned. Switch back to Owner/Staff and verify the same order shows **DELIVERED / UNPAID**. Select that Order Number in Billing and record its exact amount, then verify **DELIVERED / PAID** in Owner, Rider and the linked Customer's read-only view. Confirm invoice and audit records refer back to the same Order Number.
