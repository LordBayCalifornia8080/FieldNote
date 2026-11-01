import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import URL, create_engine, event
from sqlalchemy.orm import sessionmaker


class Database:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.path)),
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def migrate(self):
        """Apply immutable SQL revisions under a single SQLite write lock."""
        files = sorted((Path(__file__).parent / "migrations").glob("*.sql"))
        with closing(sqlite3.connect(self.path, timeout=30)) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"
            )
            installed = {
                row[0] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            available = {int(path.name.split("_")[0]) for path in files}
            if installed - available:
                raise RuntimeError("Database was created by a newer application; refusing to start")
            for path in files:
                version = int(path.name.split("_")[0])
                if version in installed:
                    continue
                statement = ""
                for line in path.read_text().splitlines(keepends=True):
                    statement += line
                    if sqlite3.complete_statement(statement):
                        connection.execute(statement)
                        statement = ""
                if statement.strip():
                    raise RuntimeError(f"Incomplete migration: {path.name}")
                connection.execute("INSERT INTO schema_migrations VALUES (?)", (version,))

    def backup(self, destination: Path):
        destination = Path(destination).resolve()
        if destination == self.path or destination.exists():
            raise ValueError("Backup destination must be a new file")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Reserve the file with private permissions; the backup API includes WAL content.
        import os

        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            with (
                closing(sqlite3.connect(self.path)) as source,
                closing(sqlite3.connect(destination)) as target,
            ):
                source.backup(target)
                result = target.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise RuntimeError("Backup integrity check failed")
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def close(self):
        self.engine.dispose()
