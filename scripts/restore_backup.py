"""Validate a Fieldnotes backup and recover into a NEW file; never replace live data."""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path


def restore(source: Path, destination: Path):
    source, destination = source.resolve(), destination.resolve()
    if not source.is_file():
        raise ValueError("Backup file does not exist")
    if source == destination or destination.exists():
        raise ValueError("Destination must be a new file; existing files are never overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # URI mode=ro prevents accidental creation of a missing input database.
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
        original.execute("PRAGMA trusted_schema=OFF")
        if original.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Backup failed integrity validation")
        versions = {r[0] for r in original.execute("SELECT version FROM schema_migrations")}
        available = {
            int(p.name.split("_")[0])
            for p in (Path(__file__).resolve().parents[1] / "fieldnotes" / "migrations").glob(
                "*.sql"
            )
        }
        if versions != available:
            raise ValueError("Backup schema does not match this source release")
        required = {
            "users",
            "sessions",
            "login_buckets",
            "pages",
            "revisions",
            "revision_search",
            "runs",
        }
        tables = {
            r[0] for r in original.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if not required <= tables:
            raise ValueError("Backup is missing required Fieldnotes tables")
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(destination)) as recovered:
                original.backup(recovered)
                recovered.execute("DELETE FROM sessions")
                recovered.execute("DELETE FROM login_buckets")
                recovered.commit()
                if recovered.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Recovered database failed integrity validation")
                if recovered.execute("PRAGMA foreign_key_check").fetchone():
                    raise ValueError("Recovered database has broken references")
                recovered.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            destination.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                Path(str(destination) + suffix).unlink(missing_ok=True)
            raise
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        restored = restore(args.source, args.destination)
    except (ValueError, sqlite3.Error, OSError) as error:
        parser.exit(1, f"Restore failed: {error}\n")
    print(
        f"Recovered into {restored}. Sessions revoked. Point the stopped server at this file before restarting."
    )


if __name__ == "__main__":
    main()
