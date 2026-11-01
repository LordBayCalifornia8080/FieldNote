import pytest
from fastapi.testclient import TestClient

from fieldnotes.api import create_app
from fieldnotes.config import Settings
from fieldnotes.db import Database
from fieldnotes.models import User
from fieldnotes.security import hasher

PASSWORD = "test-password-only-123"


@pytest.fixture
def workspace(tmp_path):
    database = Database(tmp_path / "test.db")
    database.migrate()
    encoded = hasher.hash(PASSWORD)
    with database.sessions.begin() as session:
        for role in ("admin", "editor", "reader"):
            session.add(User(username=role, role=role, password_hash=encoded))
    app = create_app(Settings(database_path=database.path), database)
    with TestClient(app) as client:
        yield app, client, database


def login(client, username="admin"):
    response = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response.json()


@pytest.fixture
def client(workspace):
    client = workspace[1]
    login(client)
    return client


@pytest.fixture
def page(client):
    notebook = client.post("/api/notebooks", json={"name": "Workshop"}).json()
    response = client.post(
        "/api/pages",
        json={
            "notebook_id": notebook["id"],
            "slug": "welcome",
            "title": "Welcome",
            "summary": "Useful notes",
            "body": "Published elephant content",
            "tags": ["workshop"],
            "steps": ["Clear the desk", "Label the boxes"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def mutate(client, page, action, **extra):
    current = client.get("/api/pages/" + page["id"]).json()
    return client.post(
        f"/api/pages/{page['id']}/{action}", json={"base_version": current["version"], **extra}
    )


def edit(client, page, **changes):
    current = client.get("/api/pages/" + page["id"]).json()
    body = {
        key: current[key]
        for key in (
            "title",
            "summary",
            "body",
            "tags",
            "steps",
            "notebook_id",
            "review_interval_days",
        )
    }
    body.update(base_version=current["version"], **changes)
    return client.put("/api/pages/" + page["id"], json=body)
