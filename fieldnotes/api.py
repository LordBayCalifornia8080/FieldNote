import difflib
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from . import __version__
from .config import get_settings
from .content import (
    add_revision,
    content_data,
    get_or_404,
    list_pages,
    lock_page,
    page_json,
    revision_for,
    selected_revision,
    visible_query,
)
from .db import Database
from .markup import render
from .middleware import BodyLimitMiddleware
from .models import Audit, Bookmark, Notebook, Page, Reference, Revision, Run, SessionToken, User
from .schemas import (
    ActiveInput,
    ArchiveInput,
    Content,
    Login,
    NotebookInput,
    NotebookUpdate,
    PageCreate,
    PageUpdate,
    PasswordChange,
    RestoreInput,
    RunCreate,
    StepUpdate,
    UserCreate,
    VersionInput,
    WorkspaceBundle,
)
from .security import (
    COOKIE,
    DUMMY_HASH,
    admin,
    audit,
    current_principal,
    db_session,
    digest,
    editor,
    hasher,
    login_budget,
    new_secret,
    verify_password,
)
from .transfer import export_bundle, import_bundle

STATIC = Path(__file__).parent / "static"


def fields(item, names):
    return {name: getattr(item, name) for name in names.split()}


def user_json(user):
    return fields(user, "id username role active created_at")


def run_json(run):
    return fields(
        run, "id page_id owner_id source_revision title steps state version created_at finished_at"
    )


def create_app(settings=None, database=None):
    settings = settings or get_settings()
    database = database or Database(settings.database_path)

    @asynccontextmanager
    async def lifespan(_app):
        database.migrate()
        yield
        database.close()

    app = FastAPI(
        title="Fieldnotes API",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.db, app.state.settings = database, settings
    app.add_middleware(BodyLimitMiddleware)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'",
            }
        )
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.exception_handler(IntegrityError)
    async def conflict(_request, _error):
        return JSONResponse(
            {"detail": "Conflicting name, slug, or reference. Reload and try again."}, 409
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, error):
        return JSONResponse(
            {"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in error.errors()]}, 422
        )

    @app.get("/health/live", include_in_schema=False)
    def live():
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    def ready(db=Depends(db_session)):
        try:
            db.scalar(select(User.id).limit(1))
        except SQLAlchemyError:
            raise HTTPException(503, "Database unavailable") from None
        return {"status": "ok"}

    @app.get("/api/openapi.json", dependencies=[Depends(current_principal)])
    def openapi():
        return app.openapi()

    @app.post("/api/auth/login")
    def login(data: Login, request: Request, response: Response, db=Depends(db_session)):
        origin = request.headers.get("origin")
        scheme = "https" if settings.cookie_secure else request.url.scheme
        if origin and origin.rstrip("/") != f"{scheme}://{request.headers.get('host', '')}":
            raise HTTPException(403, "Cross-origin login rejected")
        login_budget(
            db,
            data.username,
            request.client.host if request.client else "unknown",
            settings.login_limit,
        )
        user = db.scalar(select(User).where(User.username == data.username))
        valid = verify_password(user.password_hash if user else DUMMY_HASH, data.password)
        if not valid or not user or not user.active:
            raise HTTPException(401, "Invalid username or password")
        if hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hasher.hash(data.password)
        token, csrf = new_secret(), new_secret()
        db.add(
            SessionToken(
                token_hash=digest(token),
                user_id=user.id,
                csrf=csrf,
                expires_at=time.time() + settings.session_hours * 3600,
            )
        )
        audit(db, user.username, "auth.login", user.id)
        db.commit()
        response.set_cookie(
            COOKIE,
            token,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            max_age=settings.session_hours * 3600,
            path="/",
        )
        return {"user": user_json(user), "csrf_token": csrf}

    @app.get("/api/auth/me")
    def me(principal=Depends(current_principal)):
        return {
            "user": user_json(principal.user),
            "csrf_token": principal.session.csrf,
            "site_name": settings.site_name,
            "version": __version__,
        }

    @app.post("/api/auth/logout", status_code=204)
    def logout(response: Response, principal=Depends(current_principal), db=Depends(db_session)):
        db.delete(principal.session)
        db.commit()
        response.delete_cookie(COOKIE, path="/")

    @app.post("/api/auth/password", status_code=204)
    def change_password(
        data: PasswordChange,
        response: Response,
        principal=Depends(current_principal),
        db=Depends(db_session),
    ):
        if not verify_password(principal.user.password_hash, data.current_password):
            raise HTTPException(400, "Current password is incorrect")
        principal.user.password_hash = hasher.hash(data.new_password)
        db.execute(delete(SessionToken).where(SessionToken.user_id == principal.user.id))
        audit(db, principal.user.username, "auth.password_changed", principal.user.id)
        db.commit()
        response.delete_cookie(COOKIE, path="/")

    @app.get("/api/notebooks", dependencies=[Depends(current_principal)])
    def notebooks(db=Depends(db_session)):
        return {
            "items": [
                fields(n, "id name description version created_at")
                for n in db.scalars(select(Notebook).order_by(Notebook.name_key))
            ]
        }

    @app.post("/api/notebooks", status_code=201)
    def create_notebook(data: NotebookInput, principal=Depends(editor), db=Depends(db_session)):
        notebook = Notebook(**data.model_dump(), name_key=data.name.casefold())
        db.add(notebook)
        db.flush()
        audit(db, principal.user.username, "notebook.created", notebook.id)
        db.commit()
        return fields(notebook, "id name description version created_at")

    @app.put("/api/notebooks/{notebook_id}")
    def edit_notebook(
        notebook_id: str, data: NotebookUpdate, principal=Depends(editor), db=Depends(db_session)
    ):
        get_or_404(db, Notebook, notebook_id)
        changed = db.execute(
            update(Notebook)
            .where(Notebook.id == notebook_id, Notebook.version == data.base_version)
            .values(
                name=data.name,
                name_key=data.name.casefold(),
                description=data.description,
                version=Notebook.version + 1,
            )
        ).rowcount
        if not changed:
            raise HTTPException(409, "Notebook changed; reload before saving")
        audit(db, principal.user.username, "notebook.updated", notebook_id)
        db.commit()
        return {"id": notebook_id}

    @app.delete("/api/notebooks/{notebook_id}", status_code=204)
    def delete_notebook(notebook_id: str, principal=Depends(admin), db=Depends(db_session)):
        notebook = get_or_404(db, Notebook, notebook_id)
        if db.scalar(select(Page.id).where(Page.notebook_id == notebook_id).limit(1)):
            raise HTTPException(
                409, "Move all documents, including archived ones, before deleting this notebook"
            )
        db.delete(notebook)
        audit(db, principal.user.username, "notebook.deleted", notebook_id)
        db.commit()

    @app.get("/api/summary")
    def summary(principal=Depends(current_principal), db=Depends(db_session)):
        user = principal.user
        _, total = list_pages(db, user, limit=1)
        _, due = list_pages(db, user, review_due=True, limit=1)
        _, bookmarks = list_pages(db, user, bookmarked=True, limit=1)
        drafts = (
            db.scalar(
                select(func.count())
                .select_from(Page)
                .where(
                    Page.archived.is_(False),
                    (Page.published_revision.is_(None))
                    | (Page.published_revision != Page.current_revision),
                )
            )
            if user.role != "reader"
            else None
        )
        open_runs = db.scalar(
            select(func.count())
            .select_from(Run)
            .where(Run.owner_id == user.id, Run.state == "open")
        )
        return {
            "documents": total,
            "review_due": due,
            "bookmarks": bookmarks,
            "drafts": drafts,
            "open_runs": open_runs,
        }

    @app.get("/api/pages")
    def pages(
        q: str = Query("", max_length=160),
        notebook_id: str | None = None,
        tag: str | None = Query(None, max_length=32),
        bookmarked: bool = False,
        archived: bool = False,
        review_due: bool = False,
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=100),
        principal=Depends(current_principal),
        db=Depends(db_session),
    ):
        items, total = list_pages(
            db,
            principal.user,
            q=q,
            notebook_id=notebook_id,
            tag=tag,
            bookmarked=bookmarked,
            archived=archived,
            review_due=review_due,
            offset=offset,
            limit=limit,
        )
        return {"items": items, "total": total}

    @app.post("/api/pages", status_code=201)
    def create_page(data: PageCreate, principal=Depends(editor), db=Depends(db_session)):
        get_or_404(db, Notebook, data.notebook_id)
        page = Page(
            notebook_id=data.notebook_id,
            slug=data.slug,
            review_interval_days=data.review_interval_days,
        )
        db.add(page)
        db.flush()
        revision = add_revision(
            db,
            page,
            Content(**{k: getattr(data, k) for k in Content.model_fields}),
            principal.user.username,
            "Initial draft",
        )
        audit(db, principal.user.username, "page.created", page.id)
        db.commit()
        return page_json(db, page, revision, principal.user, True)

    @app.get("/api/pages/by-slug/{slug}")
    def by_slug(slug: str, principal=Depends(current_principal), db=Depends(db_session)):
        page = db.scalar(select(Page).where(Page.slug == slug))
        if not page:
            raise HTTPException(404, "Document not found or not published")
        ordinal = selected_revision(page, principal.user.role)
        return page_json(db, page, revision_for(db, page, ordinal), principal.user, True)

    @app.get("/api/pages/{page_id}")
    def page_detail(page_id: str, principal=Depends(current_principal), db=Depends(db_session)):
        page = get_or_404(db, Page, page_id)
        ordinal = selected_revision(page, principal.user.role)
        return page_json(db, page, revision_for(db, page, ordinal), principal.user, True)

    @app.put("/api/pages/{page_id}")
    def edit_page(
        page_id: str, data: PageUpdate, principal=Depends(editor), db=Depends(db_session)
    ):
        get_or_404(db, Notebook, data.notebook_id)
        page = lock_page(db, page_id, data.base_version)
        page.current_revision += 1
        page.notebook_id = data.notebook_id
        page.review_interval_days = data.review_interval_days
        revision = add_revision(
            db,
            page,
            Content(**{k: getattr(data, k) for k in Content.model_fields}),
            principal.user.username,
            data.message,
        )
        audit(db, principal.user.username, "page.draft_saved", page.id)
        db.commit()
        return page_json(db, page, revision, principal.user, True)

    @app.post("/api/pages/{page_id}/publish")
    def publish(
        page_id: str, data: VersionInput, principal=Depends(editor), db=Depends(db_session)
    ):
        page = lock_page(db, page_id, data.base_version)
        if page.archived:
            raise HTTPException(409, "Restore the archived document before publishing")
        page.published_revision = page.current_revision
        page.published_at = page.reviewed_at = time.time()
        audit(db, principal.user.username, "page.published", page.id)
        db.commit()
        return {"version": page.version}

    @app.post("/api/pages/{page_id}/unpublish")
    def unpublish(
        page_id: str, data: VersionInput, principal=Depends(editor), db=Depends(db_session)
    ):
        page = lock_page(db, page_id, data.base_version)
        page.published_revision = page.published_at = page.reviewed_at = None
        audit(db, principal.user.username, "page.unpublished", page.id)
        db.commit()
        return {"version": page.version}

    @app.post("/api/pages/{page_id}/archive")
    def archive(
        page_id: str, data: ArchiveInput, principal=Depends(editor), db=Depends(db_session)
    ):
        page = lock_page(db, page_id, data.base_version)
        page.archived = data.archived
        audit(
            db,
            principal.user.username,
            "page.archived" if data.archived else "page.unarchived",
            page.id,
        )
        db.commit()
        return {"version": page.version}

    @app.post("/api/pages/{page_id}/review")
    def review(page_id: str, data: VersionInput, principal=Depends(editor), db=Depends(db_session)):
        page = lock_page(db, page_id, data.base_version)
        if page.archived or not page.published_revision:
            raise HTTPException(409, "Only active published documents can be marked reviewed")
        if page.current_revision != page.published_revision:
            raise HTTPException(
                409,
                "There is an unpublished draft; publish it or restore the published copy before marking reviewed",
            )
        page.reviewed_at = time.time()
        audit(db, principal.user.username, "page.reviewed", page.id)
        db.commit()
        return {"version": page.version}

    @app.get("/api/pages/{page_id}/revisions", dependencies=[Depends(editor)])
    def revisions(page_id: str, offset: int = Query(0, ge=0), db=Depends(db_session)):
        get_or_404(db, Page, page_id)
        items = db.scalars(
            select(Revision)
            .where(Revision.page_id == page_id)
            .order_by(Revision.number.desc())
            .offset(offset)
            .limit(50)
        ).all()
        return {"items": [fields(r, "number title author message created_at") for r in items]}

    @app.get("/api/pages/{page_id}/revisions/{number}", dependencies=[Depends(editor)])
    def revision_detail(page_id: str, number: int, db=Depends(db_session)):
        revision = revision_for(db, get_or_404(db, Page, page_id), number)
        return {
            **content_data(revision),
            **fields(revision, "number author message created_at"),
            "html": render(revision.body),
        }

    @app.get("/api/pages/{page_id}/diff", dependencies=[Depends(editor)])
    def diff(
        page_id: str, older: int = Query(ge=1), newer: int = Query(ge=1), db=Depends(db_session)
    ):
        page = get_or_404(db, Page, page_id)
        before, after = revision_for(db, page, older), revision_for(db, page, newer)
        import json

        left = json.dumps(content_data(before), ensure_ascii=False, indent=2).splitlines()
        right = json.dumps(content_data(after), ensure_ascii=False, indent=2).splitlines()
        # Pretty JSON keeps each Markdown body on one escaped line; bounded to the content limit.
        difference = "\n".join(
            difflib.unified_diff(
                left, right, fromfile=f"revision-{older}", tofile=f"revision-{newer}", lineterm=""
            )
        )
        return {"diff": difference}

    @app.post("/api/pages/{page_id}/restore")
    def restore(
        page_id: str, data: RestoreInput, principal=Depends(editor), db=Depends(db_session)
    ):
        page = lock_page(db, page_id, data.base_version)
        old = revision_for(db, page, data.revision)
        page.current_revision += 1
        revision = add_revision(
            db,
            page,
            Content(**content_data(old)),
            principal.user.username,
            f"Restored revision {old.number}",
        )
        audit(db, principal.user.username, "page.revision_restored", page.id)
        db.commit()
        return page_json(db, page, revision, principal.user, True)

    @app.get("/api/pages/{page_id}/backlinks")
    def backlinks(page_id: str, principal=Depends(current_principal), db=Depends(db_session)):
        page = get_or_404(db, Page, page_id)
        selected_revision(page, principal.user.role)
        rows = db.execute(
            visible_query(principal.user)
            .where(Page.archived.is_(False))
            .join(Reference, Reference.revision_id == Revision.id)
            .where(Reference.target_slug == page.slug)
            .order_by(Revision.title)
            .limit(100)
        ).all()
        return {"items": [{"id": p.id, "slug": p.slug, "title": r.title} for p, r in rows]}

    @app.put("/api/pages/{page_id}/bookmark")
    def bookmark(
        page_id: str,
        data: ActiveInput,
        principal=Depends(current_principal),
        db=Depends(db_session),
    ):
        selected_revision(get_or_404(db, Page, page_id), principal.user.role)
        if data.active:
            from sqlalchemy.dialects.sqlite import insert

            db.execute(
                insert(Bookmark)
                .values(user_id=principal.user.id, page_id=page_id)
                .on_conflict_do_nothing(index_elements=[Bookmark.user_id, Bookmark.page_id])
            )
        else:
            db.execute(
                delete(Bookmark).where(
                    Bookmark.user_id == principal.user.id, Bookmark.page_id == page_id
                )
            )
        db.commit()
        return {"bookmarked": data.active}

    @app.post("/api/preview", dependencies=[Depends(editor)])
    def preview(data: Content):
        return {"html": render(data.body)}

    @app.post("/api/runs", status_code=201)
    def create_run(data: RunCreate, principal=Depends(current_principal), db=Depends(db_session)):
        page = get_or_404(db, Page, data.page_id)
        # Execution always snapshots the published copy, even for editors.
        ordinal = selected_revision(page, "reader")
        revision = revision_for(db, page, ordinal)
        if not revision.steps:
            raise HTTPException(409, "This published document has no checklist")
        run = Run(
            page_id=page.id,
            owner_id=principal.user.id,
            source_revision=ordinal,
            title=revision.title,
            steps=[{"label": label, "done": False, "note": ""} for label in revision.steps],
        )
        db.add(run)
        db.flush()
        audit(db, principal.user.username, "run.started", run.id)
        db.commit()
        return run_json(run)

    def owned_run(db, identifier, user):
        run = get_or_404(db, Run, identifier)
        if run.owner_id != user.id:
            raise HTTPException(404, "Not found")
        return run

    def claim_run(db, identifier, version, user):
        owned_run(db, identifier, user)
        changed = db.execute(
            update(Run)
            .where(
                Run.id == identifier,
                Run.owner_id == user.id,
                Run.version == version,
                Run.state == "open",
            )
            .values(version=Run.version + 1)
            .execution_options(synchronize_session=False)
        ).rowcount
        if not changed:
            raise HTTPException(409, "This checklist changed or is closed; reload before saving")
        return db.get(Run, identifier, populate_existing=True)

    @app.get("/api/runs")
    def runs(
        offset: int = Query(0, ge=0),
        state: Literal["all", "open", "completed", "cancelled"] = "all",
        principal=Depends(current_principal),
        db=Depends(db_session),
    ):
        query = select(Run).where(Run.owner_id == principal.user.id)
        if state != "all":
            query = query.where(Run.state == state)
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        return {
            "items": [
                run_json(r)
                for r in db.scalars(
                    query.order_by(Run.created_at.desc(), Run.id).offset(offset).limit(50)
                )
            ],
            "total": count,
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, principal=Depends(current_principal), db=Depends(db_session)):
        return run_json(owned_run(db, run_id, principal.user))

    @app.patch("/api/runs/{run_id}")
    def edit_run(
        run_id: str, data: StepUpdate, principal=Depends(current_principal), db=Depends(db_session)
    ):
        run = claim_run(db, run_id, data.base_version, principal.user)
        if data.index >= len(run.steps):
            raise HTTPException(422, "Checklist step does not exist")
        steps = [dict(s) for s in run.steps]
        steps[data.index].update(done=data.done, note=data.note)
        run.steps = steps
        db.commit()
        return run_json(run)

    @app.post("/api/runs/{run_id}/{action}")
    def finish_run(
        run_id: str,
        action: Literal["complete", "cancel"],
        data: VersionInput,
        principal=Depends(current_principal),
        db=Depends(db_session),
    ):
        run = claim_run(db, run_id, data.base_version, principal.user)
        if action == "complete" and not all(s["done"] for s in run.steps):
            raise HTTPException(409, "Complete every step first")
        run.state = "completed" if action == "complete" else "cancelled"
        run.finished_at = time.time()
        audit(db, principal.user.username, "run." + run.state, run.id)
        db.commit()
        return run_json(run)

    @app.get("/api/users", dependencies=[Depends(admin)])
    def users(db=Depends(db_session)):
        return {"items": [user_json(u) for u in db.scalars(select(User).order_by(User.username))]}

    @app.post("/api/users", status_code=201)
    def create_user(data: UserCreate, principal=Depends(admin), db=Depends(db_session)):
        user = User(
            username=data.username, role=data.role, password_hash=hasher.hash(data.password)
        )
        db.add(user)
        db.flush()
        audit(db, principal.user.username, "user.created", user.id)
        db.commit()
        return user_json(user)

    @app.patch("/api/users/{user_id}")
    def set_active(
        user_id: str, data: ActiveInput, principal=Depends(admin), db=Depends(db_session)
    ):
        user = get_or_404(db, User, user_id)
        if user.role == "admin" and not data.active:
            raise HTTPException(409, "Disable administrators through the server CLI")
        user.active = data.active
        if not data.active:
            db.execute(delete(SessionToken).where(SessionToken.user_id == user.id))
        audit(
            db, principal.user.username, "user.enabled" if data.active else "user.disabled", user.id
        )
        db.commit()
        return user_json(user)

    @app.get("/api/audit", dependencies=[Depends(admin)])
    def audit_log(offset: int = Query(0, ge=0), db=Depends(db_session)):
        return {
            "items": [
                fields(a, "id actor action target created_at")
                for a in db.scalars(
                    select(Audit)
                    .order_by(Audit.created_at.desc(), Audit.id)
                    .offset(offset)
                    .limit(100)
                )
            ]
        }

    @app.get("/api/export", dependencies=[Depends(admin)])
    def export(
        offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100), db=Depends(db_session)
    ):
        payload = export_bundle(db, offset, limit)
        total = db.scalar(select(func.count()).select_from(Page))
        return JSONResponse(
            payload,
            headers={
                "Content-Disposition": f'attachment; filename="fieldnotes-content-{offset}.json"',
                "X-Total-Documents": str(total),
                "X-Next-Offset": str(offset + len(payload["documents"]))
                if offset + len(payload["documents"]) < total
                else "",
            },
        )

    @app.post("/api/import")
    def import_content(
        data: WorkspaceBundle,
        conflict: Literal["skip", "rename"] = "skip",
        dry_run: bool = True,
        principal=Depends(admin),
        db=Depends(db_session),
    ):
        return import_bundle(db, data, principal.user.username, conflict, dry_run)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    return app
