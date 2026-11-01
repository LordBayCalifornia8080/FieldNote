import sqlite3
import sys

import pytest
from sqlalchemy import select

from fieldnotes import cli
from fieldnotes.config import get_settings
from fieldnotes.db import Database
from fieldnotes.models import Page, User
from scripts.restore_backup import restore


def test_restore_revokes_sessions_and_retains_content(client, page, workspace, tmp_path):
    backup = tmp_path / "backup.db"
    recovered = tmp_path / "recovered.db"
    workspace[2].backup(backup)
    restore(backup, recovered)
    with sqlite3.connect(recovered) as db:
        assert db.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM pages").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 3
    with pytest.raises(ValueError, match="new file"):
        restore(backup, recovered)
    assert recovered.stat().st_mode & 0o777 == 0o600 if sys.platform != "win32" else True


def test_restore_rejects_missing_and_wrong_schema(tmp_path):
    with pytest.raises(ValueError, match="exist"):
        restore(tmp_path / "missing.db", tmp_path / "out.db")
    bad = tmp_path / "bad.db"
    with sqlite3.connect(bad) as db:
        db.execute("CREATE TABLE schema_migrations (version INTEGER)")
        db.execute("INSERT INTO schema_migrations VALUES (999)")
    with pytest.raises(ValueError, match="schema"):
        restore(bad, tmp_path / "out.db")
    assert not (tmp_path / "out.db").exists()


def test_demo_is_synthetic_and_only_seeds_empty_workspace(tmp_path):
    database = Database(tmp_path / "demo.db")
    database.migrate()
    cli.seed_demo(database)
    with database.sessions() as db:
        assert len(db.scalars(select(Page)).all()) == 3
        assert not db.scalars(select(User)).all()
    with pytest.raises(ValueError, match="empty"):
        cli.seed_demo(database)
    database.close()


def test_cli_accounts_and_last_admin_invariant(monkeypatch, tmp_path):
    path = tmp_path / "cli.db"
    monkeypatch.setenv("FN_DATABASE_PATH", str(path))
    get_settings.cache_clear()
    monkeypatch.setattr(cli, "read_password", lambda: "local-test-password")
    try:
        monkeypatch.setattr(sys, "argv", ["fieldnotes", "user", "create", "operator"])
        cli.main()
        monkeypatch.setattr(sys, "argv", ["fieldnotes", "user", "disable", "operator"])
        with pytest.raises(SystemExit) as error:
            cli.main()
        assert error.value.code == 1
        monkeypatch.setattr(sys, "argv", ["fieldnotes", "user", "create", "second"])
        cli.main()
        monkeypatch.setattr(sys, "argv", ["fieldnotes", "user", "disable", "operator"])
        cli.main()
        db = Database(path)
        with db.sessions() as session:
            assert not session.scalar(select(User).where(User.username == "operator")).active
        db.close()
    finally:
        get_settings.cache_clear()


def test_password_prompt_checks_mismatch(monkeypatch):
    entries = iter(["first-test-password", "different-test-password"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _: next(entries))
    with pytest.raises(ValueError, match="match"):
        cli.read_password()
