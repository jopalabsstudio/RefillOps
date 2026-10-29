# ADR-0001 — Public portfolio versus commercial product

**Date:** 2026-10-28  
**Status:** Accepted for initial public baseline

## Context

RefillOps should demonstrate sound engineering and business operations understanding while preserving the possibility of an independently developed commercial edition.

## Decision

- Public repository is independently runnable with fictional seed data and no imports from private modules.
- Publish domain invariants, state machine, accountable delivery, audit trail, transparent monthly billing, and representative tests. These are the portfolio's proof of competence.
- **Do not commit** real station/customer data; real API credentials; payment provider setup; production operating procedures; proprietary pricing/optimization/fraud models; customer contracts; any code or configurations intended only for commercial pilots.
- Future commercial functions must live in a separate private repository / service, not in a hidden `private/` directory inside this public repo.
- No license is granted by default; see `RIGHTS.md`. Revisit before accepting contributions or commercializing this repo.
- Local demo actor credentials are ephemeral, created during seed, excluded by `.gitignore`. The demo service binds only to loopback.

## Consequences

The public repo can explain the problem and demonstrate a coherent vertical slice without disclosing operating differentiators. No claim is made that the public demo is certified, production secure, or suitable for live payments.
