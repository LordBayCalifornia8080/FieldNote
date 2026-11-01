import time
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(16), default="reader")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float, index=True)


class LoginBucket(Base):
    __tablename__ = "login_buckets"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[float] = mapped_column(Float, index=True)


class Notebook(Base):
    __tablename__ = "notebooks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80))
    name_key: Mapped[str] = mapped_column(String(160), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    notebook_id: Mapped[str] = mapped_column(
        ForeignKey("notebooks.id", ondelete="RESTRICT"), index=True
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    current_revision: Mapped[int] = mapped_column(Integer, default=1)
    published_revision: Mapped[int | None] = mapped_column(Integer)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    published_at: Mapped[float | None] = mapped_column(Float)
    reviewed_at: Mapped[float | None] = mapped_column(Float)
    review_interval_days: Mapped[int] = mapped_column(Integer, default=90)


class Revision(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(String(500), default="")
    body: Mapped[str] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    author: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    __table_args__ = (UniqueConstraint("page_id", "number", name="uq_page_revision"),)


class Reference(Base):
    __tablename__ = "references"
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("revisions.id", ondelete="CASCADE"), primary_key=True
    )
    target_slug: Mapped[str] = mapped_column(String(100), primary_key=True, index=True)


class Bookmark(Base):
    __tablename__ = "bookmarks"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    page_id: Mapped[str] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[float] = mapped_column(Float, default=time.time)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    source_revision: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(160))
    steps: Mapped[list] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(16), default="open")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[float] = mapped_column(Float, default=time.time)
    finished_at: Mapped[float | None] = mapped_column(Float)
    __table_args__ = (Index("ix_runs_owner_time", "owner_id", "created_at"),)


class Audit(Base):
    __tablename__ = "audit"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[float] = mapped_column(Float, default=time.time, index=True)
