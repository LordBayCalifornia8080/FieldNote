# Validation record — 0.1.0

Checks executed against the delivered source:

- 50 pytest cases pass on Python 3.12, covering authentication/CSRF, role boundaries, draft isolation, search input handling, safe Markdown, bookmarks/backlinks, revision restore, concurrent version conflicts, review dates, personal checklist snapshots, import/export, account administration, migrations, backup/recovery, and request limits.
- The DOM integration harness passes against a real temporary Uvicorn server and SQLite database. It exercises login, notebook creation, Markdown preview, draft save/publication, bookmarks, editing, history/diff/restore, checklist snapshots/notes/completion, account creation, audit display, and logout.
- Ruff lint and formatting checks pass; JavaScript syntax checks pass.
- Hash-locked Python dependencies install successfully; pip reports no broken requirements. The Python wheel builds and includes static assets and SQL migrations.
- Source packaging uses an explicit allowlist and includes a SHA-256 file manifest. No database, real environment file, virtual environment, node_modules, or personal author metadata is included.

Limits of this record:

- Docker is unavailable in the creation environment. The Docker build and container smoke workflow are supplied for GitHub Actions but were not executed locally.
- jsdom is not a full browser. No claim is made of visual cross-browser testing, accessibility certification, or mobile device testing.
- Python 3.13 is included in CI but was not executed locally.
- FastAPI's current TestClient dependency emitted one deprecation warning about its HTTPX transport; it did not fail the tests.
- No external security audit, vulnerability certification, sustained-load benchmark, or high-availability test was performed. See SECURITY.md for the operating assumptions.

Reproduce checks using CONTRIBUTING.md. A future code/dependency change invalidates this record until checks are rerun.
