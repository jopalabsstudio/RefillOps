# Folder and file mapping

```text
RefillOps/
├── README.md                      Public showcase, setup, demo access
├── RIGHTS.md                      No license assumed; reserved rights
├── pyproject.toml                 Python package and test configuration
├── .env.example                   Local config template (no secrets)
├── .gitignore                     Ignores DB, keys, env, caches
├── .github/workflows/ci.yml       CI automated tests
├── docs/
│   ├── PRD.md                     Product requirements / invariants
│   ├── FOLDER_FILE_MAP.md         Responsibility map (this file)
│   ├── BUILD_ORDER.md             Milestones and verification order
│   ├── STATUS.md                  Actual implementation vs planned
│   ├── DEMO_SCRIPT.md             Reviewer walkthrough
│   ├── GITHUB_PUBLISH.md          Staging and public-push safety checks
│   └── adr/
│       └── 0001-public-commercial-boundary.md
├── src/refillops/
│   ├── __init__.py                 Package marker
│   ├── schema.sql                  SQLite model and constraints
│   ├── db.py                       Connection, transactional access
│   ├── domain.py                   Pure business calculations and state rules
│   ├── auth.py                     Local demo keys and role guards
│   ├── service.py                  Transactional application commands and queries
│   ├── api.py                      FastAPI request/response contract
│   ├── cli.py                      Init/seed/run command interface
│   └── static/
│       ├── index.html              Local responsive operator console
│       ├── app.js                  Browser state and API client
│       └── styles.css              UI styling
├── tests/
│   ├── conftest.py                 Ephemeral DB and identities
│   ├── test_domain.py              Invariant/unit tests
│   └── test_api.py                 Permissions, atomicity, billing, scenarios
└── .local/                         UNTRACKED generated SQLite DB and tokens
```

## API ownership

- `auth.py`: authorization; a client-supplied station ID is never trusted as authority.
- `domain.py`: role-independent calculations; no database or HTTP dependency.
- `service.py`: transactional boundaries, station scoped reads/writes, immutable accounting and audit logging.
- `schema.sql`: relational uniqueness, foreign keys, integer minor currency units, and idempotency keys.
- `api.py`: validation, HTTP status mapping, server-side actor-derived scope.

## Commercial exclusion boundary

Do **not** add `src/private/`, live integrations, pilot datasets, production settlement logic, undisclosed pricing policies, or private scoring/optimization modules here. A future commercial edition requires an independent private codebase.


### v0.1.4 relationship extension

- `docs/ORDER_RELATIONSHIPS.md`: order-number relationships, dual status semantics and migration.
- `src/refillops/schema.sql`, `db.py`: order number, order-payment allocations, local customer access and idempotent non-destructive migration.
- `src/refillops/service.py`: shared role-scoped order projections and receipt allocation.
- `src/refillops/auth.py`, `api.py`, `cli.py`: read-only customer demo access, payment routing and safe upgrade.
- `src/refillops/static/app.js`, `styles.css`: role-specific order views and payment selection.
- `tests/test_order_relationships.py`: order status, payment, isolation, access rotation and migration coverage.
