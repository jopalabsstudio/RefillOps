# Build order — milestone ledger

This document tracks **evidence**, not promises. Keep it in sync with `docs/STATUS.md`.

| Phase | Target | Exit evidence | Current state |
| --- | --- | --- | --- |
| M0 | Packaging, schema, demo identities, seed and tests | Fresh local install and test invocation | Implemented locally; validate on target workstation |
| M1 | Customers, destinations, QR tokens, 1.5km check | Revocation + authorization + radius tests | Implemented in API; UI needs broad usability review |
| M2 | Create → assign → dispatch → complete → accounting | Database rollback + idempotency + state-machine tests | Implemented in API; pilot validation pending |
| M3 | Owner dashboard, audit, exception review | Seed data and reproducible exception | Implemented in API; operational validation pending |
| M4 | Payments, invoices, hosted-safe public experience | Double-invoice test, complete interactive demo, hosted read-only plan | Basic API and local UI implemented; hosted experience not implemented |

## Sequence for future improvements

1. Review local install on Windows and capture reproducible setup logs.
2. Strengthen tests on concurrent completion attempts and unexpected failures.
3. Add dedicated authenticated sessions (do not publish seeded bearer tokens).
4. Split operations UI into responsive owner, staff, rider views; improve accessibility and navigation.
5. Evaluate PostgreSQL migrations before any actual multi-user pilot.
6. Keep production integrations and business-specific optimizations private.

**Never mark a phase complete based only on screens or untested code.**
