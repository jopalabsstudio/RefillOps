# Reviewer demo — fictional data only

1. Install and seed as described in [README](../README.md). Read generated `.local/demo_access.json` locally.
2. Sign in as **Owner**; observe status totals, receivables, and existing exception(s). Open Activity to see auditable seed changes.
3. Switch to **Staff**, visit Customers, create a synthetic customer, view the record and add a pinned location using coordinates near `14.6500, 121.0500` (fictional example). Try a faraway location to see validation.
4. In that customer view, generate a destination token. Verify the token contains neither name nor coordinates. Optionally use `/docs` to resolve it as Staff. Revoke it and confirm it no longer resolves.
5. Go to Orders, select the destination and create a **3-gallon** order. Assign **Demo Rider A**.
6. Switch to **Rider A**, dispatch the assigned order, confirm **3 delivered**, **2 returned empties**. Look at the completion result: charge and container position are calculated by the server.
7. Switch to **Staff**; verify account and customer container position, then open Billing to record a fictional manual payment.
8. Switch to **Owner**, inspect monthly eligible charges and issue the new customer's invoice. Attempt to issue it again: the API must refuse duplicate posting. Review exceptions and activity logs.
9. Run `pytest -q`. The API tests include retrying the same idempotency key, reusing it with a changed payload, attempting a wrong-station read, attempting forbidden roles, and simulating a failed financial insert to verify rollback.

**What not to claim:** This demo does not measure real household consumption, track individual gallon serial numbers, offer route optimization, charge live cards, authorize external customers, or prove fitness for a live station.
