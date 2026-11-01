import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SLUG = r"^[a-z0-9][a-z0-9-]{0,99}$"


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class UserCreate(Login):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,64}$")
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "editor", "reader"] = "reader"


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ActiveInput(Input):
    active: bool


class VersionInput(Input):
    base_version: int = Field(ge=1)


class NotebookInput(Input):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class NotebookUpdate(NotebookInput, VersionInput):
    pass


class Content(Input):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=60000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    steps: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("title", "summary")
    @classmethod
    def trim_labels(cls, value, info):
        value = value.strip()
        if info.field_name == "title" and not value:
            raise ValueError("A title is required")
        return value

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, tags):
        normalized = list(dict.fromkeys(t.strip().casefold() for t in tags))
        if any(not re.fullmatch(r"[\w-]{1,32}", t) for t in normalized):
            raise ValueError("Tags must have 1–32 letters, digits, underscores, or hyphens")
        return normalized

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps):
        steps = [s.strip() for s in steps]
        if any(not 1 <= len(s) <= 300 for s in steps):
            raise ValueError("Checklist steps must have 1–300 characters")
        return steps


class PageCreate(Content):
    notebook_id: str = Field(min_length=1, max_length=32)
    slug: str = Field(pattern=SLUG)
    review_interval_days: int = Field(default=90, ge=1, le=730)


class PageUpdate(Content, VersionInput):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    notebook_id: str = Field(min_length=1, max_length=32)
    review_interval_days: int = Field(default=90, ge=1, le=730)
    message: str = Field(default="", max_length=200)


class ArchiveInput(VersionInput):
    archived: bool


class RestoreInput(VersionInput):
    revision: int = Field(ge=1)


class RunCreate(Input):
    page_id: str = Field(min_length=1, max_length=32)


class StepUpdate(VersionInput):
    index: int = Field(ge=0, le=99)
    done: bool
    note: str = Field(default="", max_length=1000)


class ExportPage(Input):
    notebook: str = Field(min_length=1, max_length=80)
    slug: str = Field(pattern=SLUG)
    draft: Content
    published: Content | None = None
    archived: bool = False
    review_interval_days: int = Field(default=90, ge=1, le=730)


class WorkspaceBundle(Input):
    format: Literal["fieldnotes.workspace"]
    version: Literal[1]
    notebooks: list[NotebookInput] = Field(max_length=50)
    documents: list[ExportPage] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_identifiers(self):
        notebooks = [n.name.casefold() for n in self.notebooks]
        slugs = [d.slug for d in self.documents]
        if len(notebooks) != len(set(notebooks)) or len(slugs) != len(set(slugs)):
            raise ValueError("Notebook names and document slugs must be unique within the import")
        if any(d.notebook.casefold() not in notebooks for d in self.documents):
            raise ValueError("Every document must reference a notebook present in the bundle")
        return self
