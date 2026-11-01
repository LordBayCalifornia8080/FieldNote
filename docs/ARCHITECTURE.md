# Architecture

The browser loads local HTML/CSS/ES modules and calls a same-origin FastAPI JSON API. SQLAlchemy uses SQLite with foreign keys, WAL, and a 30-second busy timeout. FTS5 indexes immutable revisions. There is no message broker, scheduler, external search service, or background worker.

## Content model

A notebook contains pages. A page has a stable slug, mutable notebook/review settings, and pointers to its current and published revisions. A revision snapshots title, summary, Markdown, tags, and checklist steps. Saving creates a new revision; publishing moves the published pointer. Notebook assignment and review interval changes apply immediately, even before draft content is published. A page version increments on mutations and protects against stale writes with an atomic compare-and-swap update.

Readers select only the published revision of active pages. Editors select the latest revision. Search, tags, and backlinks use the same role-specific selection so draft content cannot leak through those views. FTS queries use at most 12 quoted prefix terms joined by AND, with SQL parameters. Results are ordered by latest selected revision, not relevance. Links use ASCII slugs, while document text and tags support Unicode. Slugs cannot be renamed through the API.

Unpublishing removes the published pointer. Archiving hides the page while retaining its publication; unarchiving reveals that prior publication again. Restoring history creates a new draft; it never rewrites history or automatically publishes. The application does not implement permanent page deletion.

## Checklist model

Starting a run always snapshots the published revision, including for editors. Each step stores its original label, done state, and personal note. Updating a template cannot change earlier runs. Each run belongs to one account; being an administrator does not bypass the run API's owner check. Server operators can still inspect the database. Completion requires every saved step to be done. Completed/cancelled runs are immutable through the API. A run survives unpublishing or archiving its source.

## Import and export

Admin content exports are paginated by stable page ID (default 25, maximum 100). They include current drafts and published copies, archive flags, and review intervals, but no accounts, personal runs, audit records, or complete history. Empty notebooks are omitted. Each batch must fit the 4 MiB/50-notebook import limits; reduce the batch size if necessary. Avoid concurrent content creation while exporting multiple batches because offsets are not a point-in-time snapshot.

Import validates the complete schema, defaults to a non-mutating preview, and commits accepted records in one transaction. Conflicts are skipped or assigned new slugs; existing pages are never overwritten. Casefolded notebook names merge into existing notebooks without changing their descriptions. Imports start new revision histories and review timelines. Rename mode rewrites all literal `[[slug]]` occurrences that refer to imported pages, including occurrences inside code examples. Links to skipped or missing pages remain unchanged. Preview slugs are not reserved and may differ at commit time.

## Modules

| Module | Responsibility |
| --- | --- |
| `api.py` | HTTP endpoints, serialization, authorization dependencies |
| `security.py` | Accounts, sessions, CSRF, login budgets, audit helper |
| `content.py` | Revision creation, visibility, optimistic locking, search |
| `markup.py` | Safe Markdown rendering and wiki-link parsing |
| `transfer.py` | Validated content import/export |
| `db.py`, `models.py`, `migrations/` | Persistence, migration application, backups |
| `cli.py` | Server startup and operator account/content commands |
| `static/` | Responsive browser interface with no build tool |

Request bodies are limited before JSON parsing (512 KiB normally, 4 MiB for import). Individual content fields have additional bounds. Histories and audit/run collections have no global storage quota or automatic retention policy. Back up and monitor disk use.
