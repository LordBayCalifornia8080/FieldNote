# API guide

All `/api` endpoints except login require a local session. The machine-readable schema is available at `/api/openapi.json` after authentication. The browser has no bearer tokens or public read API.

A minimal Python client, using an existing account:

```python
import getpass
import httpx

with httpx.Client(base_url="http://127.0.0.1:8000") as client:
    response = client.post(
        "/api/auth/login",
        json={
            "username": input("Username: "),
            "password": getpass.getpass(),
        },
    )
    response.raise_for_status()
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    response = client.get("/api/pages", params={"q": "workshop", "limit": 25})
    response.raise_for_status()
    for page in response.json()["items"]:
        print(page["slug"], page["title"])
    client.post("/api/auth/logout").raise_for_status()
```

| Method and path | Purpose | Role |
| --- | --- | --- |
| POST `/api/auth/login` | Obtain session cookie and CSRF token | Anonymous |
| GET `/api/auth/me` | Account, CSRF token, site metadata | All |
| POST `/api/auth/password` | Change password, revoke all sessions | All |
| GET `/api/pages` | Search/filter/paginate selected revisions | All |
| POST `/api/pages` | Create initial draft | Editor/admin |
| GET `/api/pages/by-slug/{slug}` | Resolve wiki link | All |
| GET/PUT `/api/pages/{id}` | Read selected copy / save draft | All / editor/admin |
| POST `/api/pages/{id}/publish` | Publish current draft | Editor/admin |
| POST `/api/pages/{id}/unpublish` | Hide published copy | Editor/admin |
| POST `/api/pages/{id}/archive` | Archive/unarchive (`archived` boolean) | Editor/admin |
| POST `/api/pages/{id}/review` | Mark current published copy reviewed | Editor/admin |
| GET `/api/pages/{id}/revisions` | Revision history | Editor/admin |
| GET `/api/pages/{id}/diff?older=1&newer=2` | Compare structured content | Editor/admin |
| POST `/api/pages/{id}/restore` | Restore `revision` as new draft | Editor/admin |
| PUT `/api/pages/{id}/bookmark` | Set `active` boolean | All |
| GET/POST `/api/runs` | List own runs / snapshot published `page_id` | All |
| PATCH `/api/runs/{id}` | Save `index`, `done`, `note` | Owner |
| POST `/api/runs/{id}/complete` or `/cancel` | Close run | Owner |
| GET `/api/export?offset=0&limit=25` | Download a content batch | Admin |
| POST `/api/import?dry_run=true&conflict=skip` | Preview/import JSON bundle | Admin |
| GET `/api/audit` | Audit metadata, batches of 100 | Admin |

Page edits/actions, notebook edits, and run edits/actions require `base_version` from the latest GET response. A 409 means the state changed or an action is invalid. Fetch fresh state and let the user reconcile; do not blindly retry with a new version. A failed action rolls back its version increment. A 401 means sign in; 403 means role/CSRF/origin failure; 404 can intentionally hide an unavailable document; 413 means body/batch too large; 422 means invalid fields; 429 is the login budget.

Search supports `q`, `tag`, `notebook_id`, `bookmarked`, `review_due`, `archived`, `offset`, and `limit`. Archived views never expose unpublished content to readers. There is no arbitrary SQL or raw FTS query syntax. The OpenAPI schema is authoritative for all field limits and remaining notebook/user endpoints.
