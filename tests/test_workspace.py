import json
import sqlite3
import time

import pytest
from conftest import PASSWORD, edit, login, mutate
from sqlalchemy import select

from fieldnotes.markup import references, render
from fieldnotes.models import Page, SessionToken
from fieldnotes.security import digest


def test_health_and_shell(workspace):
    client = workspace[1]
    assert client.get("/health/ready").json() == {"status": "ok"}
    shell = client.get("/")
    assert shell.status_code == 200
    assert "script-src 'self'" in shell.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/pages").status_code == 401


def test_authentication_csrf_and_hashed_sessions(client, workspace):
    raw = client.cookies.get("fn_session")
    with workspace[2].sessions() as db:
        assert db.get(SessionToken, digest(raw))
        assert db.get(SessionToken, raw) is None
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/notebooks", json={"name": "Blocked"}).status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_origin_and_invalid_login(workspace):
    client = workspace[1]
    data = {"username": "admin", "password": PASSWORD}
    assert (
        client.post(
            "/api/auth/login", json=data, headers={"Origin": "https://other.example"}
        ).status_code
        == 403
    )
    data["password"] = "incorrect"
    assert client.post("/api/auth/login", json=data).status_code == 401


def test_login_throttling(workspace):
    app, client, _ = workspace
    app.state.settings.login_limit = 2
    for _ in range(2):
        assert (
            client.post(
                "/api/auth/login", json={"username": "nobody", "password": "bad"}
            ).status_code
            == 401
        )
    response = client.post("/api/auth/login", json={"username": "nobody", "password": "bad"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_password_change_revokes_sessions(client):
    response = client.post(
        "/api/auth/password",
        json={"current_password": PASSWORD, "new_password": "a-new-test-password"},
    )
    assert response.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": "a-new-test-password"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize("role", ["reader", "editor"])
@pytest.mark.parametrize("path", ["/api/users", "/api/audit", "/api/export"])
def test_admin_routes_protected(client, role, path):
    login(client, role)
    assert client.get(path).status_code == 403


def test_readers_cannot_write_or_read_drafts(client, page):
    login(client, "reader")
    assert client.get("/api/pages").json()["total"] == 0
    assert client.get("/api/pages/" + page["id"]).status_code == 404
    assert client.get("/api/pages/by-slug/welcome").status_code == 404
    assert client.get(f"/api/pages/{page['id']}/revisions").status_code == 403
    assert client.post("/api/notebooks", json={"name": "No"}).status_code == 403


def test_publication_is_separate_snapshot(client, page):
    assert mutate(client, page, "publish").status_code == 200
    assert (
        edit(
            client, page, title="Secret draft", body="unpublished giraffe", tags=["secret"]
        ).status_code
        == 200
    )
    login(client, "reader")
    public = client.get("/api/pages/" + page["id"]).json()
    assert public["title"] == "Welcome"
    assert public["body"] == page["body"]
    assert "current_revision" not in public
    assert client.get("/api/pages?q=giraffe").json()["total"] == 0
    assert client.get("/api/pages?q=eleph").json()["total"] == 1
    assert client.get("/api/pages?tag=secret").json()["total"] == 0


def test_stale_writes_are_rejected(client, page):
    body = {
        k: page[k]
        for k in (
            "title",
            "summary",
            "body",
            "tags",
            "steps",
            "notebook_id",
            "review_interval_days",
        )
    }
    body["base_version"] = page["version"]
    assert client.put("/api/pages/" + page["id"], json=body).status_code == 200
    body["title"] = "Lost update"
    assert client.put("/api/pages/" + page["id"], json=body).status_code == 409
    assert client.get("/api/pages/" + page["id"]).json()["title"] == "Welcome"


def test_restore_creates_draft_and_diff(client, page):
    mutate(client, page, "publish")
    edit(client, page, title="Second title")
    mutate(client, page, "publish")
    response = mutate(client, page, "restore", revision=1)
    assert response.json()["current_revision"] == 3
    assert response.json()["published_revision"] == 2
    assert (
        "Second title" in client.get(f"/api/pages/{page['id']}/diff?older=1&newer=2").json()["diff"]
    )
    login(client, "reader")
    assert client.get("/api/pages/" + page["id"]).json()["title"] == "Second title"


@pytest.mark.parametrize("action,extra", [("unpublish", {}), ("archive", {"archived": True})])
def test_hiding_publications(client, page, action, extra):
    mutate(client, page, "publish")
    assert mutate(client, page, action, **extra).status_code == 200
    login(client, "reader")
    assert client.get("/api/pages").json()["total"] == 0
    assert client.get("/api/pages/" + page["id"]).status_code == 404


def test_review_requires_published_current_copy(client, page, workspace):
    assert mutate(client, page, "review").status_code == 409
    mutate(client, page, "publish")
    with workspace[2].sessions.begin() as db:
        db.get(Page, page["id"]).reviewed_at = time.time() - 100 * 86400
    assert client.get("/api/pages?review_due=true").json()["total"] == 1
    assert mutate(client, page, "review").status_code == 200
    assert client.get("/api/pages?review_due=true").json()["total"] == 0
    edit(client, page, body="Draft changed")
    assert mutate(client, page, "review").status_code == 409


@pytest.mark.parametrize(
    "query", ['" OR *', "'; DROP TABLE pages; --", "NEAR(a b)", "***", "((", "a:b"]
)
def test_search_treats_queries_as_plain_terms(client, page, query):
    response = client.get("/api/pages", params={"q": query})
    assert response.status_code == 200
    assert client.get("/api/pages").json()["total"] == 1


def test_bookmarks_are_personal_and_idempotent(client, page):
    path = f"/api/pages/{page['id']}/bookmark"
    for _ in range(2):
        assert client.put(path, json={"active": True}).status_code == 200
    assert client.get("/api/pages?bookmarked=true").json()["total"] == 1
    login(client, "editor")
    assert client.get("/api/pages?bookmarked=true").json()["total"] == 0


def test_notebook_uniqueness_and_nonempty_guard(client, page):
    assert client.post("/api/notebooks", json={"name": "WORKSHOP"}).status_code == 409
    assert client.delete("/api/notebooks/" + page["notebook_id"]).status_code == 409


def test_backlinks_respect_publication(client, page):
    mutate(client, page, "publish")
    linked = client.post(
        "/api/pages",
        json={
            "notebook_id": page["notebook_id"],
            "slug": "linked",
            "title": "Link",
            "body": "[[welcome]]",
        },
    ).json()
    endpoint = f"/api/pages/{page['id']}/backlinks"
    assert len(client.get(endpoint).json()["items"]) == 1
    login(client, "reader")
    assert client.get(endpoint).json()["items"] == []
    login(client)
    mutate(client, linked, "publish")
    edit(client, linked, body="No link")
    login(client, "reader")
    assert len(client.get(endpoint).json()["items"]) == 1


@pytest.mark.parametrize(
    "body",
    [
        "<script>alert(1)</script>",
        "[x](javascript:alert(1))",
        "[x](data:text/html,evil)",
        "![x](https://example.com/tracker.png)",
    ],
)
def test_markdown_has_no_active_injection_or_images(body):
    html = render(body)
    assert "<script" not in html
    assert 'href="javascript:' not in html
    assert 'href="data:' not in html
    assert "<img" not in html


def test_wiki_parser_ignores_code_and_preserves_whitespace(client, page):
    assert references("[[real]] `[[fake]]`\n\n```\n[[fake2]]\n```") == {"real"}
    body = "    indented code\n\nTrailing space  \nNext line\n"
    assert edit(client, page, body=body).json()["body"] == body


def test_run_snapshot_completion_and_owner_isolation(client, page):
    mutate(client, page, "publish")
    run = client.post("/api/runs", json={"page_id": page["id"]}).json()
    url = "/api/runs/" + run["id"]
    edit(client, page, steps=["Different draft"])
    mutate(client, page, "unpublish")
    assert len(client.get(url).json()["steps"]) == 2
    assert client.post(url + "/complete", json={"base_version": 1}).status_code == 409
    for index in range(2):
        response = client.patch(
            url,
            json={"base_version": index + 1, "index": index, "done": True, "note": "Saved note"},
        )
        assert response.status_code == 200, response.text
    assert client.post(url + "/complete", json={"base_version": 3}).json()["state"] == "completed"
    assert client.patch(url, json={"base_version": 4, "index": 0, "done": False}).status_code == 409
    login(client, "editor")
    assert client.get(url).status_code == 404
    assert client.get("/api/runs").json()["total"] == 0


def test_run_stale_update_and_cancel(client, page):
    mutate(client, page, "publish")
    run = client.post("/api/runs", json={"page_id": page["id"]}).json()
    url = "/api/runs/" + run["id"]
    data = {"base_version": 1, "index": 0, "done": True}
    assert client.patch(url, json=data).status_code == 200
    assert client.patch(url, json=data).status_code == 409
    assert client.post(url + "/cancel", json={"base_version": 2}).json()["state"] == "cancelled"


def test_import_preview_skip_and_rename_roundtrip(client, page):
    mutate(client, page, "publish")
    edit(client, page, body="[[welcome]] draft")
    bundle = client.get("/api/export").json()
    assert "password" not in json.dumps(bundle)
    assert client.post("/api/import?conflict=rename", json=bundle).json()["dry_run"]
    assert client.get("/api/pages").json()["total"] == 1
    assert client.post("/api/import?dry_run=false", json=bundle).json()["skipped"] == 1
    result = client.post("/api/import?dry_run=false&conflict=rename", json=bundle).json()
    assert result["created"] == 1
    slug = result["plan"][0]["slug"]
    copied = client.get("/api/pages/by-slug/" + slug).json()
    assert copied["body"] == f"[[{slug}]] draft"
    login(client, "reader")
    assert client.get("/api/pages/by-slug/" + slug).json()["body"] == page["body"]


def test_import_rejects_invalid_bundle_atomically(client, page):
    bundle = client.get("/api/export").json()
    bundle["documents"].append(bundle["documents"][0])
    assert client.post("/api/import?dry_run=false&conflict=rename", json=bundle).status_code == 422
    assert client.get("/api/pages").json()["total"] == 1


def test_request_size_limit(client):
    assert (
        client.post(
            "/api/preview",
            content=b"x" * (512 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_validation_does_not_echo_password(client):
    response = client.post("/api/users", json={"username": "new", "password": "SECRET"})
    assert response.status_code == 422
    assert "SECRET" not in response.text


def test_disabling_account_revokes_access(client):
    users = client.get("/api/users").json()["items"]
    reader = next(u for u in users if u["role"] == "reader")
    assert client.patch("/api/users/" + reader["id"], json={"active": False}).status_code == 200
    assert (
        client.post(
            "/api/auth/login", json={"username": "reader", "password": PASSWORD}
        ).status_code
        == 401
    )
    admin = next(u for u in users if u["role"] == "admin")
    assert client.patch("/api/users/" + admin["id"], json={"active": False}).status_code == 409


def test_migrations_backup_and_forward_guard(client, page, workspace, tmp_path):
    db = workspace[2]
    db.migrate()
    destination = tmp_path / "backup.db"
    db.backup(destination)
    with sqlite3.connect(destination) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT count(*) FROM pages").fetchone()[0] == 1
        assert (
            connection.execute(
                "SELECT count(*) FROM revision_search WHERE revision_search MATCH 'elephant'"
            ).fetchone()[0]
            == 1
        )
    with pytest.raises(ValueError):
        db.backup(destination)
    with sqlite3.connect(db.path) as connection:
        connection.execute("INSERT INTO schema_migrations VALUES (999)")
    with pytest.raises(RuntimeError, match="newer"):
        db.migrate()


def test_expired_session_rejected(client, workspace):
    with workspace[2].sessions.begin() as db:
        db.scalar(select(SessionToken)).expires_at = 0
    assert client.get("/api/auth/me").status_code == 401


def test_concurrent_publications_have_one_winner(client, page):
    from concurrent.futures import ThreadPoolExecutor

    def publish(_):
        return client.post(f"/api/pages/{page['id']}/publish", json={"base_version": 1}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(publish, range(2))) == [200, 409]


def test_published_checklist_available_when_draft_removes_steps(client, page):
    mutate(client, page, "publish")
    draft = edit(client, page, steps=[]).json()
    assert draft["step_count"] == 0
    assert draft["published_step_count"] == 2
    assert len(client.post("/api/runs", json={"page_id": page["id"]}).json()["steps"]) == 2


def test_https_cookie_and_origin(workspace):
    app, client, _ = workspace
    app.state.settings.cookie_secure = True
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": PASSWORD},
        headers={"Origin": "https://testserver"},
    )
    assert response.status_code == 200
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "max-age=" in response.headers["strict-transport-security"]


def test_unarchive_reveals_previous_published_copy(client, page):
    mutate(client, page, "publish")
    edit(client, page, title="Unpublished")
    mutate(client, page, "archive", archived=True)
    mutate(client, page, "archive", archived=False)
    login(client, "reader")
    assert client.get("/api/pages/" + page["id"]).json()["title"] == "Welcome"
