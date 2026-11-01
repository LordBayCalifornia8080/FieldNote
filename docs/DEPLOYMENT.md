# Deployment and recovery

## Single server

Use the Docker Compose quick start in the README. The image runs as UID/GID 10001, with a read-only root filesystem and a writable `/data` named volume. A new Docker-managed volume inherits the image directory ownership. For a bind mount, the host directory must be writable by UID 10001. One application process and SQLite on local storage are intentional constraints.

The default host listener is `127.0.0.1:8081`. For remote access put a maintained HTTPS reverse proxy on the host in front of that address. Preserve the original `Host` header. Example Caddy configuration (replace the example hostname with your own):

```caddyfile
notes.example.com {
    request_body {
        max_size 4MB
    }
    reverse_proxy 127.0.0.1:8081 {
        header_up Host {host}
    }
}
```

Set `FN_COOKIE_SECURE=true` in `.env`, then run `docker compose up -d` to recreate the service with secure cookies. The proxy must forward the external host unchanged; login checks the browser Origin against that host and the configured HTTPS scheme. The application ignores forwarded client-IP headers, so rate limiting groups proxied traffic by proxy address. Configure additional limits at your proxy when necessary. TLS termination and certificates belong to the proxy; Caddy is an optional example, not bundled.

Do not publish port 8000/8081 directly to the Internet. If the proxy is in another container, adapt the network and upstream address deliberately instead of assuming its loopback reaches the app. Prefer a VPN for a private group. Public code hosting on GitHub is separate from hosting a running instance.

## Accounts

```sh
docker compose exec app fieldnotes user create admin
docker compose exec app fieldnotes user create writer --role editor
docker compose exec app fieldnotes user reset-password admin
docker compose exec app fieldnotes user disable writer
```

Passwords are requested interactively, never passed as command-line arguments. Resetting a password reactivates the account and revokes its sessions. Administrators can add users in the UI and disable non-administrators there. Disabling an administrator requires the CLI, which refuses to disable the last active administrator. Roles are selected on creation; there is no role-change interface.

## Full backup

While the service is running, use SQLite's backup API through the CLI. Choose a new destination filename each time:

```sh
docker compose exec app fieldnotes backup /data/backup-001.db
docker compose cp app:/data/backup-001.db ./backup-001.db
```

For a direct installation: `fieldnotes backup backups/backup-001.db`.

The backup includes committed WAL data, documents, revisions, search indexes, accounts, sessions, runs, and audit metadata. It is integrity-checked before success. Store a copy off-host with restricted permissions, preferably encrypted by your storage/backup system. Do not simply copy a live `.db` file: recent changes may still be in its WAL. JSON content export is not a disaster-recovery backup.

## Restore to a new database

The included restore utility **never overwrites an existing destination**. It validates database integrity and expected migration version, copies through SQLite's backup API, and deletes session/login-throttle records from the restored copy. Keep the original intact until you have verified recovery.

Direct installation:

```sh
python scripts/restore_backup.py backup-001.db recovered.db
# Stop the old server, then configure FN_DATABASE_PATH to the absolute recovered.db path.
# Start the server again and sign in normally. Passwords are preserved.
```

Docker, using the backup retained in the existing volume:

```sh
docker compose stop app
docker compose run --rm app python scripts/restore_backup.py /data/backup-001.db /data/recovered.db
```

Change `FN_DATABASE_PATH` **inside compose.yaml's environment section** to `/data/recovered.db`, then run `docker compose up -d`. The Compose file deliberately fixes that path, so changing only `.env` does not override it. A host-only backup can be copied into the stopped container with `docker compose cp ./backup-001.db app:/data/backup-001.db`; ensure the copied file is readable by UID 10001. Never start two servers writing the same database. Verify document history, search, and checklist records after recovery. Keep the original volume and backup until verification is complete.

## Updates and troubleshooting

Before an update: create a full backup, record the current source version, stop the service, replace source, then rebuild and restart. Startup applies numbered SQL migrations transactionally. Unknown newer migration versions cause startup to refuse the database. A rollback means restoring the prior source and its matching pre-update backup; downgrading schema in place is unsupported.

Check `docker compose ps` and `docker compose logs --tail=100 app`. `/health/live` reports process availability and `/health/ready` checks database access; neither checks disk capacity or validates all data. There are no scheduled jobs. Review dates are calculated on request; no email is sent. All application dates are stored in UTC and displayed in the browser's locale.
