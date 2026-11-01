# Development

Contributions are welcome in a fork; this initial release does not promise review or merge availability. Do not submit secrets or private deployment data.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip install --no-deps -e .
python -m pytest
ruff check .
ruff format --check .
# Optional interface integration test, requires Node 20+:
npm ci
python scripts/ui_smoke.py
```

The integration test creates a temporary database and random temporary password, starts the real server on loopback, drives the UI with jsdom, and deletes the test workspace afterward. It does not contact an existing deployment. jsdom validates DOM/application flows, not browser layout, focus behavior, or accessibility conformance.

The production UI has no npm dependencies or compilation step. `package.json` exists only for the optional test harness. Run one Uvicorn process; do not add replicas or change SQLite connection settings without addressing consistency and locking.

Add numbered SQL files for schema changes; never edit a released migration. Test fresh startup and upgrades. Preserve role-specific revision selection in search and backlinks. Add regression tests for permission and persistence changes. Page/run mutations must keep optimistic version checks. Avoid adding remote fetching or command execution to this project.

Locks pin transitive dependencies and hashes. To update them intentionally with uv installed:

```sh
uv pip compile pyproject.toml --universal --generate-hashes -o requirements.lock
uv pip compile pyproject.toml --extra dev --universal --generate-hashes -o requirements-dev.lock
```

Review the diff and upstream licenses/advisories, then rerun tests and the Docker build. The Python base image remains a moving patch tag so it can receive upstream fixes; pin a verified digest in your deployment if exact image reproducibility is required.
