# Fieldnotes

**A self-hosted home for useful knowledge and repeatable routines.**

Keep workshop manuals, household guides, club handbooks, and project notes in one place. Turn a published guide into a reusable checklist, then keep a separate record each time you follow it.

Fieldnotes is a complete Python application with a responsive browser interface, SQLite storage, local accounts, and no frontend build step. It requires no cloud account, email provider, paid API, telemetry service, or AI service.

## What it does

- **Notebooks and tags:** organize Markdown documents, summaries, and checklist templates.
- **Drafts and publication:** editors work on a draft while readers see the last published snapshot.
- **Immutable revisions:** inspect history, compare content, or restore an earlier revision as a new draft.
- **Search and links:** SQLite full-text prefix search, `[[document-slug]]` links, and permission-aware backlinks.
- **Review queue:** configurable review intervals and an in-app list of documents due for review.
- **Personal checklists:** snapshot published steps, save progress and notes, finish or cancel a run.
- **Bookmarks:** a personal collection of frequently used documents.
- **Local permissions:** administrator, editor, and reader accounts; no public registration.
- **Portable content:** preview JSON imports, skip or rename conflicts, and export content in batches.
- **Recovery:** transactionally consistent SQLite backups and a safe restore-to-new-file utility.
- **Administration:** audit metadata, account disabling, password recovery from the server CLI, and health endpoints.

This is an organizational tool. It does not scan networks, run document commands, execute checklist steps, send webhooks, fetch remote images, or connect to external accounts. A checklist records human actions; it does not automate them.

## Quick start with Docker

Install Docker Engine with the Compose plugin (or Docker Desktop). In the extracted repository:

```sh
docker compose up -d --build
docker compose exec app fieldnotes user create admin
# Optional: three synthetic example documents; only works before documents exist.
docker compose exec app fieldnotes demo
```

Enter your own password when prompted. There are **no default credentials**. Open **http://localhost:8081**. The service binds to the host loopback interface by default; it is not exposed to your LAN or the Internet. Data lives in the `fieldnotes_data` named volume.

Stop with `docker compose down`. Do not add `-v` unless you intend to delete the data volume.

## Run directly with Python

Requires Python 3.12 or newer, SQLite with FTS5, and pip. Python's standard builds normally include FTS5.

```sh
python -m venv .venv
# macOS/Linux:
. .venv/bin/activate
# Windows PowerShell instead: .venv\Scripts\Activate.ps1
python -m pip install --require-hashes -r requirements.lock
python -m pip install --no-deps .
fieldnotes user create admin
fieldnotes demo
fieldnotes serve
```

Open http://127.0.0.1:8000. The database defaults to `fieldnotes.db` in the working directory. Keep that working directory consistent, or set an absolute `FN_DATABASE_PATH`.

## First workflow

1. Sign in and create a notebook.
2. Create a document. Add Markdown, tags, a review interval, and optional checklist steps.
3. Save the draft, preview it, then publish it.
4. Create reader or editor accounts from Workspace if you need them.
5. Start a checklist from a published document. Save each completed step, then finish the run.
6. Revisit the review queue and back up the database regularly.

All signed-in users can see notebook names and descriptions. Readers see all active published documents. Editors and administrators can see all drafts, archived documents, and revision histories. There are **no per-notebook access controls**. Checklist runs are personal through the application API; server operators can read the underlying database.

## Configuration

Environment variables or a local `.env` file are supported. See [.env.example](.env.example).

| Variable | Default | Meaning |
| --- | --- | --- |
| `FN_DATABASE_PATH` | `fieldnotes.db` | Local SQLite file; use an absolute path in production |
| `FN_COOKIE_SECURE` | `false` | Set `true` when serving through HTTPS |
| `FN_SITE_NAME` | `Fieldnotes` | Workspace label, at most 80 characters |
| `FN_SESSION_HOURS` | `12` | Session lifetime, 1–168 hours |
| `FN_LOGIN_LIMIT` | `20` | Login attempts per username per 15-minute window; peer limit is five times this |

For remote access use HTTPS and follow [deployment guidance](docs/DEPLOYMENT.md). Changing the repository visibility on GitHub does not deploy or run the application.

## Documentation

- [Deployment, accounts, backup and recovery](docs/DEPLOYMENT.md)
- [Architecture and data semantics](docs/ARCHITECTURE.md)
- [API examples](docs/API.md)
- [Upload the source through GitHub's interface](docs/GITHUB.md)
- [Security model and maintenance status](SECURITY.md)
- [Development and testing](CONTRIBUTING.md)
- [Validation record](docs/VALIDATION.md)

## Scope and maintenance

Version 0.1.0 is an initial source release, provided as-is. **No ongoing maintenance, support response, or security update schedule is promised.** A new maintainer may change this policy explicitly.

Designed for a small trusted group on one server. It is not a regulated records system, password vault, emergency procedure system, or safety-critical checklist product. It has no encryption at rest, MFA, SSO, email recovery, attachments, real-time collaborative editing, or automated reminders. Revision history and backups retain earlier content. Search indexes documents; it does not search personal checklist notes.

Use a single application process and a local disk. SQLite storage on NFS/SMB and multi-replica deployments are unsupported. See [SECURITY.md](SECURITY.md) before exposing an instance to the Internet.

## License

[MIT](LICENSE). Third-party dependencies have their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md). The repository contains synthetic examples and no publisher contact details or deployment credentials.
