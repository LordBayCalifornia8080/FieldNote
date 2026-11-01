# Security and maintenance

This initial source release has **no promised ongoing maintenance, security response, or patch schedule**. No external security audit or penetration test has been performed. Deployers must assess suitability, monitor dependency advisories, update their copies, and control access. Tests demonstrate particular behavior; they do not prove absence of vulnerabilities.

## Intended boundary

One trusted group, one server, one local database. Administrators create accounts; public signup is absent. Readers can access every active published document, and notebook names/descriptions. Editors can access every draft and historical revision. Notebook separation is organizational, not a security boundary. Run owners can access their own checklist records through the API. An operator with filesystem/database access can read all data and reset accounts.

Passwords use Argon2; session tokens are random and stored as SHA-256 digests. Cookies are HttpOnly and SameSite=Strict. Mutations require a session-bound CSRF token. Login attempts are limited by username and direct peer address in fixed windows. Behind a reverse proxy, clients share the peer budget; add proxy-side rate limiting as needed. This is not DDoS protection. There is no MFA or automatic account lockout recovery by email.

Markdown disables raw HTML, rejects unsafe link schemes through markdown-it's link validation, and displays image descriptions instead of loading images. CSP blocks inline scripts and third-party resources. Ordinary links may navigate to external sites when clicked. Imported content is still untrusted information: review it before publishing.

The application has no server-side URL fetcher, command runner, plugin loader, filesystem browser, or remote integrations. Installation and dependency downloads require network access. Anyone who can edit the deployed source code or installed packages can change what the server does.

## Deployment precautions

- Keep the default loopback binding until HTTPS and access controls are configured.
- Set `FN_COOKIE_SECURE=true` for HTTPS. Keep the upstream server unreachable except through the proxy.
- Use unique passwords and minimal roles. Protect server access and backups.
- Keep database files outside the web root and Git repository. SQLite data is not encrypted at rest.
- Do not store credentials, personal records, or information that requires regulated retention controls here.
- Back up off-host and test recovery. Disk exhaustion, oversized history growth, and availability management remain operator responsibilities.

History, checklist snapshots, audit records, and backups persist. Unpublishing or archiving a page hides it from readers but does not erase previous content. Content exports include drafts and published copies; full backups include accounts, password hashes, active sessions, audit metadata, and run notes. Restoring a backup with the supplied utility revokes its sessions. There is no selective permanent erasure interface or automatic retention cleanup for documents/audits/runs.

## Reporting

Do not publish credentials, private documents, or exploitable deployment details in a public issue. If the repository owner has enabled GitHub private vulnerability reporting, use it. Otherwise inspect the repository's current contact policy before sending sensitive details. No reporting channel or response time is guaranteed by this source release. A maintainer who adopts the project should replace this section with an actual monitored process.
