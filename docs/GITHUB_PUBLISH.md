# Publishing this portfolio safely

This is a local runnable demo, **not a hosted production service**. Run the automated tests and verify every committed file before pushing.

```bash
python -m pip install -e '.[dev]'
pytest -q
git init
git add .
git status --short
```

**Before committing**, check that the staged files do not include `.local/`, `demo_access.json`, `*.sqlite3`, real customer records, actual location histories, `.env`, backup archives, private commercial modules, or API keys. `.gitignore` helps but does not replace manual review. Then:

```bash
git commit -m "Initial RefillOps public portfolio demonstration"
git branch -M main
# Create a blank GitHub repository in your own account, then:
git remote add origin https://github.com/YOUR-ACCOUNT/RefillOps.git
git push -u origin main
```

Suggested description: **Operations platform demo for water-refilling stations—destination-linked delivery, container exchanges, billing, and remote owner oversight.**

Suggested topics: `fastapi`, `python`, `sqlite`, `operations-management`, `delivery-management`, `portfolio-project`, `audit-trail`, `billing`.

Do not add a license without intentionally deciding on reuse rights. See `RIGHTS.md` and `docs/adr/0001-public-commercial-boundary.md`. A public GitHub repo does not make this demo safe to host for anonymous users; avoid exposing its bearer-key mechanism publicly.
