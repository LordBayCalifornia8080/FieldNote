import time

from fastapi import HTTPException
from sqlalchemy import and_, exists, select, text, update

from .markup import references, render, search_query
from .models import Bookmark, Notebook, Page, Reference, Revision
from .schemas import Content


def get_or_404(db, model, identifier):
    item = db.get(model, identifier)
    if item is None:
        raise HTTPException(404, "Not found")
    return item


def content_data(revision):
    return {name: getattr(revision, name) for name in Content.model_fields}


def add_revision(db, page, content, author, message="", number=None):
    revision = Revision(
        page_id=page.id,
        number=number or page.current_revision,
        **content.model_dump(),
        author=author,
        message=message,
    )
    db.add(revision)
    db.flush()
    db.execute(
        text(
            "INSERT INTO revision_search (revision_id,title,summary,body,tags) VALUES (:id,:title,:summary,:body,:tags)"
        ),
        {
            "id": revision.id,
            "title": revision.title,
            "summary": revision.summary,
            "body": revision.body,
            "tags": " ".join(revision.tags),
        },
    )
    for target in references(revision.body):
        db.add(Reference(revision_id=revision.id, target_slug=target))
    return revision


def lock_page(db, identifier, version):
    changed = db.execute(
        update(Page)
        .where(Page.id == identifier, Page.version == version)
        .values(version=Page.version + 1)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not changed:
        if db.get(Page, identifier) is None:
            raise HTTPException(404, "Not found")
        raise HTTPException(
            409, "This document changed. Reload before saving; your draft was not applied."
        )
    return db.get(Page, identifier, populate_existing=True)


def selected_revision(page, role):
    if role == "reader":
        if page.archived or page.published_revision is None:
            raise HTTPException(404, "Not found")
        return page.published_revision
    return page.current_revision


def revision_for(db, page, number):
    revision = db.scalar(
        select(Revision).where(Revision.page_id == page.id, Revision.number == number)
    )
    if revision is None:
        raise HTTPException(404, "Revision not found")
    return revision


def page_json(db, page, revision, user, detailed=False):
    bookmarked = db.get(Bookmark, (user.id, page.id)) is not None
    result = {
        "id": page.id,
        "slug": page.slug,
        "notebook_id": page.notebook_id,
        "notebook": db.get(Notebook, page.notebook_id).name,
        "version": page.version,
        "revision": revision.number,
        "title": revision.title,
        "summary": revision.summary,
        "tags": revision.tags,
        "step_count": len(revision.steps),
        "updated_at": revision.created_at,
        "published_at": page.published_at,
        "reviewed_at": page.reviewed_at,
        "review_interval_days": page.review_interval_days,
        "review_due_at": (page.reviewed_at or page.published_at or time.time())
        + page.review_interval_days * 86400
        if page.published_revision
        else None,
        "bookmarked": bookmarked,
        "state": "archived"
        if page.archived
        else "draft"
        if page.published_revision is None
        else "published",
    }
    if user.role != "reader":
        result.update(
            current_revision=page.current_revision,
            published_revision=page.published_revision,
            has_draft=page.published_revision is not None
            and page.current_revision != page.published_revision,
        )
    if detailed:
        result.update(body=revision.body, html=render(revision.body), steps=revision.steps)
        result["published_step_count"] = (
            len(revision_for(db, page, page.published_revision).steps)
            if page.published_revision and not page.archived
            else 0
        )
    return result


def visible_query(user):
    ordinal = Page.published_revision if user.role == "reader" else Page.current_revision
    query = select(Page, Revision).join(
        Revision, and_(Revision.page_id == Page.id, Revision.number == ordinal)
    )
    if user.role == "reader":
        query = query.where(Page.archived.is_(False), Page.published_revision.is_not(None))
    return query


def list_pages(
    db,
    user,
    *,
    q="",
    notebook_id=None,
    tag=None,
    bookmarked=False,
    archived=False,
    review_due=False,
    offset=0,
    limit=50,
):
    query = visible_query(user).where(Page.archived == archived)
    if notebook_id:
        query = query.where(Page.notebook_id == notebook_id)
    if tag:
        # SQLite JSON functions compare complete tag values, not substrings.
        query = query.where(
            text("EXISTS (SELECT 1 FROM json_each(revisions.tags) WHERE json_each.value = :tag)")
        ).params(tag=tag.casefold())
    if bookmarked:
        query = query.where(
            exists(
                select(Bookmark.page_id).where(
                    Bookmark.page_id == Page.id, Bookmark.user_id == user.id
                )
            )
        )
    if review_due:
        from sqlalchemy import func

        query = query.where(
            Page.published_revision.is_not(None),
            func.coalesce(Page.reviewed_at, Page.published_at) + Page.review_interval_days * 86400
            <= time.time(),
        )
    terms = search_query(q)
    if q and not terms:
        return [], 0
    if terms:
        query = query.where(
            text(
                "revisions.id IN (SELECT revision_id FROM revision_search WHERE revision_search MATCH :search)"
            )
        )
        query = query.params(search=terms)
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.execute(
        query.order_by(Revision.created_at.desc(), Page.id).offset(offset).limit(limit)
    ).all()
    return [page_json(db, page, revision, user) for page, revision in rows], total
