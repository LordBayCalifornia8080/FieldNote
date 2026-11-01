"""Run UI integration checks against an isolated temporary server and database."""

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

from fieldnotes.cli import seed_demo
from fieldnotes.db import Database
from fieldnotes.models import User
from fieldnotes.security import hasher

ROOT = Path(__file__).resolve().parent.parent


def main():
    with tempfile.TemporaryDirectory(prefix="fieldnotes-ui-") as temporary:
        db = Database(Path(temporary) / "ui.db")
        db.migrate()
        password = secrets.token_urlsafe(24)
        with db.sessions.begin() as session:
            session.add(
                User(username="demo-admin", role="admin", password_hash=hasher.hash(password))
            )
        seed_demo(db)
        db.close()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "FN_DATABASE_PATH": str(db.path),
            "FN_COOKIE_SECURE": "false",
            "SMOKE_BASE_URL": base,
            "SMOKE_PASSWORD": password,
            "PYTHONPATH": str(ROOT),
        }
        with (Path(temporary) / "server.log").open("w+") as log:
            server = subprocess.Popen(
                [sys.executable, "-m", "fieldnotes.cli", "serve", "--port", str(port)],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=log,
            )
            try:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError("Test server exited unexpectedly")
                    try:
                        if (
                            httpx.get(
                                base + "/health/ready", timeout=0.5, trust_env=False
                            ).status_code
                            == 200
                        ):
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Test server did not become ready")
                subprocess.run(
                    ["node", "scripts/ui_smoke.mjs"], cwd=ROOT, env=env, check=True, timeout=90
                )
            except Exception:
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
