import argparse
import getpass
from pathlib import Path

from sqlalchemy import delete, func, select

from .config import get_settings
from .content import add_revision
from .db import Database
from .models import Notebook, Page, SessionToken, User
from .schemas import Content, UserCreate
from .security import audit, hasher


def read_password():
    password = getpass.getpass("Password (12–256 characters): ")
    repeated = getpass.getpass("Repeat password: ")
    if password != repeated or not 12 <= len(password) <= 256:
        raise ValueError("Passwords must match and contain 12–256 characters")
    return password


def seed_demo(db):
    """Only synthetic reference material. No sample credentials or public accounts."""
    with db.sessions.begin() as session:
        if session.scalar(select(func.count()).select_from(Page)):
            raise ValueError("Demo content can only be added to an empty document workspace")
        existing = session.scalar(select(Notebook).where(Notebook.name_key == "workshop"))
        notebook = existing or Notebook(
            name="Workshop",
            name_key="workshop",
            description="A sample place for practical knowledge",
        )
        if not existing:
            session.add(notebook)
            session.flush()
        examples = [
            (
                "welcome-to-fieldnotes",
                "A home for useful knowledge",
                "Start small. Write down the things worth remembering.",
                "# Welcome to your workspace\n\nFieldnotes keeps manuals, practical notes, and repeatable routines together.\n\n## A useful first page\n\nWrite a short guide to something you do often. Add a summary, a few tags, and a review interval.\n\n- Drafts stay with editors.\n- Readers see the published copy.\n- Revisions preserve your changes.\n\nTry the [[weekly-workshop-reset]] checklist or read [[documenting-a-process]].\n",
                ["getting-started"],
                [],
            ),
            (
                "weekly-workshop-reset",
                "The weekly workshop reset",
                "A ten-minute routine for a clearer workspace.",
                "# Make space for next week\n\nUse this checklist to organize your notes and workspace. It records each run separately, so editing this template will not alter an existing run.\n\n## Before you start\n\nPut unfinished ideas in an inbox and return reference material to its notebook. See [[documenting-a-process]] for writing your own routine.\n",
                ["routine", "workshop"],
                [
                    "Collect loose notes into the inbox",
                    "Return reference books to their shelf",
                    "Write down one improvement for next week",
                    "Choose the next project to focus on",
                ],
            ),
            (
                "documenting-a-process",
                "Write a process someone can follow",
                "A practical structure for clear, reusable documentation.",
                "# Explain the outcome first\n\nStart with what the reader will accomplish and what they need.\n\n## Keep steps observable\n\nEach step should produce a result the reader can check. Prefer concrete verbs and explain unfamiliar terms.\n\n| Section | What belongs here |\n| --- | --- |\n| Purpose | The outcome |\n| Preparation | Materials and prerequisites |\n| Steps | Actions in order |\n| Review | How to know it worked |\n\n## Keep it current\n\nAssign a sensible review interval. A reminder to review is an organizational aid, not a guarantee that a document is correct.\n",
                ["writing", "guide"],
                [],
            ),
        ]
        import time

        for slug, title, summary, body, tags, steps in examples:
            page = Page(
                notebook_id=notebook.id,
                slug=slug,
                published_revision=1,
                published_at=time.time(),
                reviewed_at=time.time(),
            )
            session.add(page)
            session.flush()
            add_revision(
                session,
                page,
                Content(title=title, summary=summary, body=body, tags=tags, steps=steps),
                "sample-content",
                "Synthetic starter content",
            )
            audit(session, "server-cli", "page.demo_created", page.id)


def main():
    parser = argparse.ArgumentParser(description="Fieldnotes server administration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations")
    serve = sub.add_parser("serve", help="Run the HTTP server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    backup = sub.add_parser("backup", help="Create a transactionally consistent SQLite backup")
    backup.add_argument("destination", type=Path)
    sub.add_parser("demo", help="Add optional synthetic starter content to an empty workspace")
    users = sub.add_parser("user")
    actions = users.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("username")
    create.add_argument("--role", choices=["admin", "editor", "reader"], default="admin")
    for action in ("reset-password", "disable"):
        command = actions.add_parser(action)
        command.add_argument("username")
    args = parser.parse_args()
    settings = get_settings()
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "fieldnotes.api:create_app",
            factory=True,
            host=args.host,
            port=args.port,
            workers=1,
            proxy_headers=False,
            access_log=False,
        )
        return
    db = Database(settings.database_path)
    try:
        db.migrate()
        if args.command == "migrate":
            print("Database schema is current.")
        elif args.command == "backup":
            db.backup(args.destination)
            print(f"Backup created: {args.destination}")
        elif args.command == "demo":
            seed_demo(db)
            print("Added three synthetic starter documents. No accounts were created.")
        else:
            password = read_password() if args.action != "disable" else None
            with db.sessions.begin() as session:
                # Serialize administrative writes, including the last-admin invariant.
                from sqlalchemy import text

                session.execute(text("BEGIN IMMEDIATE"))
                user = session.scalar(select(User).where(User.username == args.username))
                if args.action == "create":
                    if user:
                        raise ValueError("Username already exists")
                    data = UserCreate(username=args.username, password=password, role=args.role)
                    user = User(
                        username=data.username, password_hash=hasher.hash(password), role=data.role
                    )
                    session.add(user)
                    session.flush()
                else:
                    if not user:
                        raise ValueError("Username does not exist")
                    if args.action == "disable":
                        count = session.scalar(
                            select(func.count())
                            .select_from(User)
                            .where(User.active.is_(True), User.role == "admin")
                        )
                        if user.active and user.role == "admin" and count <= 1:
                            raise ValueError("Cannot disable the last active administrator")
                        user.active = False
                    else:
                        user.password_hash = hasher.hash(password)
                        user.active = True
                    session.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
                audit(session, "server-cli", "user." + args.action, user.id)
            print("Account updated.")
    except ValueError as error:
        parser.exit(1, f"{error}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
