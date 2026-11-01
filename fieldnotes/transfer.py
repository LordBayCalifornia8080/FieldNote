import json
import time

from fastapi import HTTPException
from sqlalchemy import select

from .content import add_revision, content_data, revision_for
from .markup import WIKI
from .models import Notebook, Page, uid
from .schemas import Content, WorkspaceBundle
from .security import audit


def export_bundle(db, offset=0, limit=25):
    pages = db.scalars(select(Page).order_by(Page.id).offset(offset).limit(limit)).all()
    notebooks = {}
    documents = []
    for page in pages:
        notebook = db.get(Notebook, page.notebook_id)
        notebooks[notebook.id] = {"name": notebook.name, "description": notebook.description}
        current = revision_for(db, page, page.current_revision)
        published = (
            revision_for(db, page, page.published_revision) if page.published_revision else None
        )
        documents.append(
            {
                "notebook": notebook.name,
                "slug": page.slug,
                "draft": content_data(current),
                "published": content_data(published) if published else None,
                "archived": page.archived,
                "review_interval_days": page.review_interval_days,
            }
        )
    payload = {
        "format": "fieldnotes.workspace",
        "version": 1,
        "notebooks": list(notebooks.values()),
        "documents": documents,
    }
    if (
        len(notebooks) > 50
        or len(json.dumps(payload, ensure_ascii=False).encode()) > 4 * 1024 * 1024
    ):
        raise HTTPException(413, "Export exceeds an importable batch; choose a smaller limit")
    return WorkspaceBundle.model_validate(payload).model_dump()


def import_bundle(db, bundle, actor, conflict="skip", dry_run=False):
    occupied = set(db.scalars(select(Page.slug)))
    mapping, plan = {}, []
    for document in bundle.documents:
        slug = document.slug
        if slug in occupied and conflict == "skip":
            plan.append({"source": slug, "slug": slug, "action": "skip"})
            continue
        if slug in occupied:
            slug = slug[:90].rstrip("-") + "-" + uid()[:8]
            while slug in occupied:
                slug = document.slug[:90].rstrip("-") + "-" + uid()[:8]
        occupied.add(slug)
        mapping[document.slug] = slug
        plan.append({"source": document.slug, "slug": slug, "action": "create"})
    if dry_run:
        return {
            "dry_run": True,
            "plan": plan,
            "created": 0,
            "skipped": sum(p["action"] == "skip" for p in plan),
        }
    required = {d.notebook.casefold() for d in bundle.documents if d.slug in mapping}
    notebook_ids = {}
    for source in bundle.notebooks:
        if source.name.casefold() not in required:
            continue
        notebook = db.scalar(select(Notebook).where(Notebook.name_key == source.name.casefold()))
        if not notebook:
            notebook = Notebook(
                name=source.name, name_key=source.name.casefold(), description=source.description
            )
            db.add(notebook)
            db.flush()
        notebook_ids[source.name.casefold()] = notebook.id

    def remap(content):
        data = content.model_dump()
        data["body"] = WIKI.sub(
            lambda match: "[[" + mapping.get(match.group(1), match.group(1)) + "]]", data["body"]
        )
        return Content(**data)

    for source in bundle.documents:
        if source.slug not in mapping:
            continue
        draft = remap(source.draft)
        published = remap(source.published) if source.published else None
        same = published and published == draft
        page = Page(
            notebook_id=notebook_ids[source.notebook.casefold()],
            slug=mapping[source.slug],
            current_revision=1 if not published or same else 2,
            published_revision=1 if published else None,
            published_at=time.time() if published else None,
            reviewed_at=None,
            archived=source.archived,
            review_interval_days=source.review_interval_days,
        )
        db.add(page)
        db.flush()
        if published:
            add_revision(db, page, published, actor, "Imported published copy", number=1)
        if not published or not same:
            add_revision(db, page, draft, actor, "Imported draft", number=page.current_revision)
        audit(db, actor, "page.imported", page.id)
    db.commit()
    return {
        "dry_run": False,
        "plan": plan,
        "created": len(mapping),
        "skipped": len(plan) - len(mapping),
    }
