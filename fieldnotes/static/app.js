import { h, date, badge, empty } from "./common.js";

const $ = (selector) => document.querySelector(selector);
const state = {
  user: null,
  csrf: null,
  route: "library",
  notebook: null,
  notebooks: [],
  q: "",
  tag: "",
  offset: 0,
  page: null,
  run: null,
  editing: null,
  dirty: false,
  importData: null,
};
const canEdit = () => state.user && state.user.role !== "reader";
const isAdmin = () => state.user?.role === "admin";
const dialog = $("#dialog");
let generation = 0,
  toastTimer;
async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  if (state.csrf) headers["X-CSRF-Token"] = state.csrf;
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 204) return null;
  const data = await response
    .json()
    .catch(() => ({ detail: "Unexpected server response" }));
  if (!response.ok) {
    if (response.status === 401 && path !== "/auth/login") showLogin();
    throw new Error(
      Array.isArray(data.detail)
        ? data.detail
            .map((e) => e.loc.slice(1).join(".") + ": " + e.msg)
            .join("; ")
        : data.detail || "Request failed",
    );
  }
  return data;
}
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $("#toast").textContent = message;
  $("#toast").className = error ? "error" : "";
  $("#toast").hidden = false;
  toastTimer = setTimeout(() => {
    $("#toast").hidden = true;
  }, 6500);
}
function showLogin() {
  generation++;
  state.user = null;
  state.csrf = null;
  $("#login-screen").hidden = false;
  $("#app-screen").hidden = true;
  if (dialog.open) dialog.close();
}
function confirmLeave() {
  return !state.dirty || confirm("Discard the changes you have not saved?");
}
function resetView() {
  state.dirty = false;
  state.editing = null;
  state.page = null;
  state.run = null;
}
function heading(kicker, title, description, actions = "") {
  return `<div class="heading"><div><p class="eyebrow">${h(kicker)}</p><h1>${h(title)}</h1><p>${h(description)}</p></div><div class="actions">${actions}</div></div>`;
}
function formActions(label = "Save") {
  return `<p class="error" role="alert"></p><div class="form-actions"><button type="button" data-action="close">Cancel</button><button type="submit" class="primary">${h(label)}</button></div>`;
}
function openDialog(title, description, body) {
  $("#dialog-content").innerHTML =
    `<div class="dialog-head"><div><h2 id="dialog-title">${h(title)}</h2><p>${h(description)}</p></div><button class="icon" data-action="close" aria-label="Close dialog">×</button></div><div class="dialog-body">${body}</div>`;
  if (!dialog.open) dialog.showModal();
}
function download(name, data, type = "application/json") {
  const url = URL.createObjectURL(new Blob([data], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
async function sidebar() {
  const data = await api("/notebooks");
  state.notebooks = data.items;
  $("#notebook-nav").innerHTML = data.items
    .map(
      (n) =>
        `<button data-notebook="${h(n.id)}" class="${state.notebook === n.id ? "active" : ""}"><span>▱</span>${h(n.name)}</button>`,
    )
    .join("");
  document
    .querySelectorAll("[data-editor]")
    .forEach((n) => (n.hidden = !canEdit()));
  document
    .querySelectorAll("[data-admin]")
    .forEach((n) => (n.hidden = !isAdmin()));
}
async function start() {
  const info = await api("/auth/me");
  state.user = info.user;
  state.csrf = info.csrf_token;
  $("#site-name").textContent = info.site_name;
  $("#account-label").textContent = info.user.username + " · " + info.user.role;
  $("#version-label").textContent = "v" + info.version + " / LOCAL WORKSPACE";
  $("#login-screen").hidden = true;
  $("#app-screen").hidden = false;
  await sidebar();
  const slug = new URL(location.href).searchParams.get("page");
  if (slug) await openPage(null, slug);
  else await render();
}
function pager(count, total, size = 50) {
  return `<div class="pagination"><span>${total ? state.offset + 1 : 0}–${state.offset + count}${total !== null ? " of " + total : ""}</span><button class="small" data-action="previous" data-size="${size}" ${!state.offset ? "disabled" : ""}>← Previous</button><button class="small" data-action="next" data-size="${size}" ${total === null ? (count < size ? "disabled" : "") : state.offset + count >= total ? "disabled" : ""}>Next →</button></div>`;
}
function cards(items) {
  return `<div class="cards">${items.map((p) => `<article class="card"><div class="card-top"><span class="document-icon" aria-hidden="true">${p.step_count ? "☑" : "≡"}</span><div>${badge(p.state)}${p.has_draft ? " " + badge("draft") : ""}</div><button class="bookmark" data-action="bookmark" data-id="${h(p.id)}" data-active="${!p.bookmarked}" aria-label="${p.bookmarked ? "Remove bookmark" : "Bookmark"} ${h(p.title)}">${p.bookmarked ? "★" : "☆"}</button></div><button class="card-title" data-action="page" data-id="${h(p.id)}">${h(p.title)}</button><p>${h(p.summary || "A little knowledge, kept close at hand.")}</p><div class="tags">${p.tags.map((t) => `<button class="tag" data-tag="${h(t)}">${h(t)}</button>`).join("")}</div><div class="card-bottom"><span>${h(p.notebook)}</span><span>${p.step_count ? p.step_count + " steps · " : ""}${date(p.updated_at)}</span></div></article>`).join("")}</div>`;
}
async function render() {
  if (!state.user) return;
  const current = ++generation;
  document
    .querySelectorAll("[data-route]")
    .forEach((n) =>
      n.classList.toggle(
        "active",
        n.dataset.route === state.route && !state.notebook,
      ),
    );
  document
    .querySelectorAll("[data-notebook]")
    .forEach((n) =>
      n.classList.toggle("active", n.dataset.notebook === state.notebook),
    );
  let html = "";
  if (["library", "bookmarks", "reviews", "archive"].includes(state.route)) {
    const params = new URLSearchParams({
      q: state.q,
      offset: state.offset,
      limit: 50,
      archived: state.route === "archive",
      bookmarked: state.route === "bookmarks",
      review_due: state.route === "reviews",
    });
    if (state.notebook) params.set("notebook_id", state.notebook);
    if (state.tag) params.set("tag", state.tag);
    const [data, summary] = await Promise.all([
      api("/pages?" + params),
      api("/summary"),
    ]);
    const notebook = state.notebooks.find((n) => n.id === state.notebook);
    const titles = {
      library: "Good knowledge deserves a home.",
      bookmarks: "Keep the useful things close.",
      reviews: "A little care keeps knowledge useful.",
      archive: "Set aside. Still remembered.",
    };
    html = heading(
      notebook
        ? "NOTEBOOK"
        : state.route === "library"
          ? "YOUR WORKSPACE"
          : state.route.toUpperCase(),
      notebook ? notebook.name : titles[state.route],
      notebook
        ? notebook.description
        : state.route === "reviews"
          ? "Documents whose scheduled review date has arrived."
          : state.route === "archive"
            ? "Archived documents stay in history and are hidden from readers."
            : "Guides, notes, and repeatable routines. All in one place.",
      canEdit()
        ? `<button class="primary" data-action="new-page">+ New document</button>${notebook ? `<button class="small" data-action="edit-notebook" data-id="${h(notebook.id)}">Edit notebook</button>` : ""}`
        : "",
    );
    if (state.route === "library" && !notebook)
      html += `<div class="stats"><div class="stat"><small>DOCUMENTS <span>▤</span></small><strong>${summary.documents}</strong><p>Knowledge in your workspace</p></div><div class="stat"><small>BOOKMARKS <span>☆</span></small><strong>${summary.bookmarks}</strong><p>Your personal reference shelf</p></div><div class="stat"><small>REVIEW DUE <span>◷</span></small><strong>${summary.review_due}</strong><p>A chance to keep things current</p></div><div class="stat"><small>OPEN CHECKLISTS <span>☑</span></small><strong>${summary.open_runs}</strong><p>Routines you have in progress</p></div></div>`;
    html += `<div class="toolbar"><h3>${state.q ? "Search results" : state.tag ? "Tagged: " + h(state.tag) : "The reference shelf"} <small class="muted">/ ${data.total}</small></h3><div class="toolbar-controls"><form id="search-form"><input name="q" aria-label="Search documents" placeholder="Search your knowledge…" value="${h(state.q)}"></form>${state.tag ? '<button class="small" data-action="clear-tag">Clear tag ×</button>' : ""}</div></div>`;
    html += data.items.length
      ? cards(data.items)
      : empty(
          state.route === "reviews"
            ? "Nothing overdue"
            : state.route === "archive"
              ? "Nothing archived"
              : state.q || state.tag
                ? "No matching documents"
                : "Start with something worth remembering",
          state.route === "reviews"
            ? "Your published documents are within their review intervals."
            : "Create a notebook, add a guide, and publish it when it is ready.",
          canEdit() && state.route === "library"
            ? '<button class="primary small" data-action="new-page">Write your first document →</button>'
            : "",
        );
    if (data.total) html += pager(data.items.length, data.total);
  } else if (state.route === "runs") {
    const data = await api("/runs?offset=" + state.offset);
    html = heading(
      "REUSABLE ROUTINES",
      "One checklist. A fresh start, every time.",
      "Each run preserves the published steps as they were when you started.",
    );
    html += data.items.length
      ? `<section class="panel">${data.items.map((r) => `<div class="run-row"><div><button class="row-title" data-action="run" data-id="${h(r.id)}">${h(r.title)}</button><p>${r.steps.filter((s) => s.done).length} of ${r.steps.length} steps · Started ${date(r.created_at)} · Revision ${r.source_revision}</p></div>${badge(r.state)}</div>`).join("")}</section>${pager(data.items.length, data.total)}`
      : empty(
          "Your next routine starts in a document",
          "Open a published document with a checklist and choose Start checklist.",
        );
  } else if (state.route === "workspace") {
    const users = await api("/users");
    html = heading(
      "WORKSPACE SETTINGS",
      "A shared library. Clear responsibilities.",
      "Administrators manage access. Editors shape the library. Readers use published guides.",
      '<button class="primary" data-action="new-user">+ Add user</button>',
    );
    html += `<section class="panel"><div class="panel-head"><h3>People</h3></div><div class="table-wrap"><table class="data"><thead><tr><th>USERNAME</th><th>ROLE</th><th>STATUS</th><th></th></tr></thead><tbody>${users.items.map((u) => `<tr><td>${h(u.username)}</td><td>${h(u.role)}</td><td>${badge(u.active ? "active" : "archived")}</td><td>${u.role === "admin" ? '<small class="muted">Managed through server CLI</small>' : `<button class="small" data-action="toggle-user" data-id="${h(u.id)}" data-active="${!u.active}">${u.active ? "Disable" : "Enable"}</button>`}</td></tr>`).join("")}</tbody></table></div></section><section class="panel"><div class="panel-head"><h3>Portable content</h3></div><div class="panel-body"><p class="muted">Export documents in batches, or preview and import a Fieldnotes JSON bundle. Content exports preserve drafts and published copies. Full backups, including history and accounts, use the server CLI.</p><div class="actions"><button data-action="export">Export content ↓</button><button data-action="import">Import content ↑</button></div></div></section>`;
  } else if (state.route === "audit") {
    const data = await api("/audit?offset=" + state.offset);
    html = heading(
      "ACTIVITY LOG",
      "The story behind the workspace.",
      "Administrative and publishing events, without passwords or document bodies.",
    );
    html += `<section class="panel"><div class="table-wrap"><table class="data"><thead><tr><th>WHEN</th><th>WHO</th><th>ACTION</th><th>RECORD</th></tr></thead><tbody>${data.items.map((a) => `<tr><td>${date(a.created_at)}</td><td>${h(a.actor)}</td><td>${h(a.action)}</td><td class="mono">${h(a.target)}</td></tr>`).join("")}</tbody></table></div></section>${pager(data.items.length, null, 100)}`;
  }
  if (current === generation && state.user) {
    $("#main").innerHTML = html;
    $("#main").focus({ preventScroll: true });
  }
}
async function navigate(route, notebook = null) {
  if (!confirmLeave()) return;
  resetView();
  state.route = route;
  state.notebook = notebook;
  state.offset = 0;
  state.q = "";
  state.tag = "";
  history.replaceState(null, "", "/");
  await render();
}
async function openPage(id, slug = null) {
  if (!confirmLeave()) return;
  const current = ++generation;
  const page = await api(
    slug ? "/pages/by-slug/" + encodeURIComponent(slug) : "/pages/" + id,
  );
  const links = await api("/pages/" + page.id + "/backlinks");
  if (current !== generation || !state.user) return;
  resetView();
  state.page = page;
  history.replaceState(null, "", "/?page=" + encodeURIComponent(page.slug));
  if (dialog.open) dialog.close();
  $("#main").innerHTML =
    `<div class="breadcrumb"><button data-route="library">Library</button><span>/</span><button data-notebook="${h(page.notebook_id)}">${h(page.notebook)}</button></div><header class="document-header"><div class="actions">${badge(page.state)}${page.has_draft ? badge("draft") : ""}<button class="bookmark" data-action="bookmark" data-id="${h(page.id)}" data-active="${!page.bookmarked}" aria-label="${page.bookmarked ? "Remove bookmark" : "Bookmark"} document">${page.bookmarked ? "★" : "☆"}</button><button class="small quiet" data-action="print">Print</button>${canEdit() ? `<button class="small" data-action="edit-page">Edit draft</button><button class="small" data-action="history">History</button>${page.state !== "archived" ? `<button class="primary small" data-action="publish">Publish revision ${page.revision}</button>` : ""}<button class="small" data-action="archive" data-active="${page.state !== "archived"}">${page.state === "archived" ? "Restore document" : "Archive"}</button>` : ""}</div><h1>${h(page.title)}</h1><p>${h(page.summary)}</p><div class="document-meta"><span>${h(page.notebook)}</span><span>Revision ${page.revision}</span><span>Updated ${date(page.updated_at)}</span><span>${page.published_at ? "Published " + date(page.published_at) : "Not published"}</span></div></header>${page.has_draft ? `<div class="notice purple">You are reading draft revision ${page.revision}. Readers still see published revision ${page.published_revision}.</div>` : ""}${page.state === "archived" ? '<div class="notice">This document is archived. Restoring it will make its previous published copy visible to readers again.</div>' : ""}<div class="document-layout"><article class="prose">${page.html || '<p class="muted">This document is waiting for its first words.</p>'}${page.steps.length ? `<h2>Reusable checklist</h2><ol class="checklist-template">${page.steps.map((s) => `<li>${h(s)}</li>`).join("")}</ol>` : ""}${page.published_step_count ? `<div class="no-print"><button class="primary small" data-action="start-run">Start checklist →</button><p class="hint">Runs use the published steps, including when you are viewing a newer draft.</p></div>` : ""}</article><aside class="document-aside"><section class="aside-block"><h3>KEEP IT CURRENT</h3><p>${page.review_due_at ? "Next review: " + date(page.review_due_at) : "Publish this document to start its review schedule."}</p>${canEdit() && page.state === "published" ? '<button class="small" data-action="review">Mark reviewed</button>' : ""}</section><section class="aside-block"><h3>FILED UNDER</h3><div class="tags">${page.tags.map((t) => `<button class="tag" data-tag="${h(t)}">${h(t)}</button>`).join("") || '<span class="muted">No tags yet</span>'}</div></section><section class="aside-block"><h3>LINKED FROM</h3>${links.items.map((l) => `<a href="/?page=${h(l.slug)}" data-wiki="${h(l.slug)}">${h(l.title)} ↗</a>`).join("") || "<p>No incoming document links yet.</p>"}</section><section class="aside-block"><h3>LINK TO THIS PAGE</h3><code>[[${h(page.slug)}]]</code>${canEdit() && page.published_revision ? '<p><button class="small danger" data-action="unpublish">Unpublish</button></p>' : ""}</section></aside></div>`;
}
async function editorView(page = null) {
  if (!confirmLeave()) return;
  if (!state.notebooks.length) return notebookForm(null, true);
  generation++;
  resetView();
  state.editing = page;
  const draft = page || {
    title: "",
    summary: "",
    body: "",
    tags: [],
    steps: [],
    notebook_id: state.notebook || state.notebooks[0].id,
    review_interval_days: 90,
  };
  $("#main").innerHTML =
    heading(
      "THE WRITING DESK",
      page
        ? "Make the next version better."
        : "A new page, a useful beginning.",
      "Saving creates a draft. Publish separately when it is ready.",
      '<button data-action="cancel-edit">Cancel</button>',
    ) +
    `<form id="editor-form"><div class="editor-layout"><div class="editor-main"><label>Document title<input name="title" required maxlength="160" value="${h(draft.title)}" placeholder="What would you like to document?"></label><label>Short summary<input name="summary" maxlength="500" value="${h(draft.summary)}" placeholder="Help someone know when this page is useful."></label><div class="editor-tabs"><button type="button" class="active" data-action="write-tab">Write</button><button type="button" data-action="preview-tab">Preview</button></div><label id="body-label">Markdown content<textarea name="body" maxlength="60000" placeholder="# Start with the outcome\n\nWrite a clear, practical guide…">${h(draft.body)}</textarea></label><div id="editor-preview" class="editor-preview prose" hidden></div><p class="hint">Use Markdown headings, lists, tables, and code blocks. Link pages with [[document-slug]]. Embedded images and raw HTML are not rendered.</p>${page ? '<label>Revision note<input name="message" maxlength="200" placeholder="What changed in this revision?"></label>' : ""}<p class="error" role="alert"></p><div class="form-actions"><button type="submit" class="primary">Save draft →</button></div></div><aside class="editor-aside"><label>Notebook<select name="notebook_id">${state.notebooks.map((n) => `<option value="${h(n.id)}" ${n.id === draft.notebook_id ? "selected" : ""}>${h(n.name)}</option>`).join("")}</select></label>${!page ? '<label>Permanent slug<input name="slug" required pattern="[a-z0-9][a-z0-9-]{0,99}" maxlength="100" placeholder="a-useful-guide"><span class="hint">Lowercase letters, numbers, and hyphens. Used by page links.</span></label>' : ""}<label>Tags<input name="tags" value="${h(draft.tags.join(", "))}" placeholder="guide, workshop"><span class="hint">Comma-separated. Up to 12 tags.</span></label><label>Review every (days)<input name="review_interval_days" type="number" min="1" max="730" value="${draft.review_interval_days}" required></label><label class="full">Reusable checklist<textarea name="steps" placeholder="One step per line">${h(draft.steps.join("\n"))}</textarea><span class="hint">Optional. Up to 100 steps, 300 characters each. Readers can start separate runs of the published checklist.</span></label></aside></div></form>`;
}
function contentFrom(form) {
  const data = Object.fromEntries(new FormData(form));
  return {
    title: data.title,
    summary: data.summary || "",
    body: data.body || "",
    tags: (data.tags || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean),
    steps: (data.steps || "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean),
  };
}
function notebookForm(notebook = null, thenDocument = false) {
  openDialog(
    notebook ? "Edit notebook" : "Create a notebook",
    "Give related documents a shared place.",
    `<form data-form="notebook" data-id="${h(notebook?.id || "")}" data-version="${notebook?.version || ""}" data-next="${thenDocument}"><label>Name<input name="name" maxlength="80" required value="${h(notebook?.name || "")}" placeholder="Workshop"></label><label>Description<textarea name="description" maxlength="500">${h(notebook?.description || "")}</textarea></label>${formActions(notebook ? "Save notebook" : "Create notebook")}${notebook && isAdmin() ? `<button class="danger small" type="button" data-action="delete-notebook" data-id="${h(notebook.id)}">Delete empty notebook</button>` : ""}</form>`,
  );
}
async function historyView(offset = 0) {
  const data = await api(`/pages/${state.page.id}/revisions?offset=${offset}`);
  openDialog(
    "Revision history",
    "Restoring creates a new draft; earlier revisions remain intact.",
    `<div>${data.items.map((r) => `<div class="history-row"><div><strong>Revision ${r.number} · ${h(r.title)}</strong><p>${h(r.author)} · ${date(r.created_at)}</p><p>${h(r.message || "No revision note")}</p></div><div class="actions"><button class="small" data-action="view-revision" data-number="${r.number}">View</button><button class="small" data-action="diff" data-number="${r.number}">Compare</button><button class="small" data-action="restore-revision" data-number="${r.number}">Restore</button></div></div>`).join("")}</div><div class="actions"><button class="small" data-action="history-page" data-offset="${Math.max(0, offset - 50)}" ${offset === 0 ? "disabled" : ""}>Newer</button><button class="small" data-action="history-page" data-offset="${offset + 50}" ${data.items.length < 50 ? "disabled" : ""}>Older</button></div>`,
  );
}
async function openRun(id) {
  if (!confirmLeave()) return;
  const run = await api("/runs/" + id);
  generation++;
  resetView();
  state.run = run;
  history.replaceState(null, "", "/");
  renderRun();
}
function renderRun() {
  const r = state.run,
    done = r.steps.filter((s) => s.done).length;
  $("#main").innerHTML =
    heading(
      "YOUR CHECKLIST",
      r.title,
      `Published revision ${r.source_revision} · Started ${date(r.created_at)}`,
      badge(r.state),
    ) +
    `<div class="notice purple">This run keeps its original steps even if the source document changes. Runs are personal to your account.</div><p id="run-progress" class="muted">${done} of ${r.steps.length} steps saved as complete</p><progress class="progress" id="run-bar" max="${r.steps.length}" value="${done}" aria-label="Checklist progress"></progress><section class="panel">${r.steps.map((s, index) => `<form class="run-step" data-form="step" data-index="${index}"><label class="check"><input name="done" type="checkbox" ${s.done ? "checked" : ""} ${r.state !== "open" ? "disabled" : ""}><span>${h(s.label)}</span></label><label class="hint">Personal note<textarea name="note" maxlength="1000" ${r.state !== "open" ? "readonly" : ""}>${h(s.note)}</textarea></label>${r.state === "open" ? '<div class="actions"><p class="error" role="alert"></p><button type="submit" class="small">Save step</button></div>' : ""}</form>`).join("")}</section><div class="actions">${r.state === "open" ? `<button class="primary" data-action="complete-run" ${done !== r.steps.length ? "disabled" : ""}>Finish checklist</button><button class="danger" data-action="cancel-run">Cancel run</button>` : `<span class="muted">${r.state === "completed" ? "Completed" : "Cancelled"} ${date(r.finished_at)}</span>`}<button data-route="runs">Back to my checklists</button></div>`;
}
function importForm() {
  state.importData = null;
  openDialog(
    "Import a content bundle",
    "JSON only, up to 4 MiB. Preview the plan before importing.",
    `<form data-form="import"><label>Fieldnotes JSON file<input name="file" type="file" accept="application/json,.json" required></label><label>Existing document slugs<select name="conflict"><option value="skip">Skip existing documents</option><option value="rename">Create renamed copies</option></select></label><p class="hint">Names are assigned at import time; preview does not reserve them. Imported copies start new histories. Existing content is never overwritten.</p><div id="import-plan"></div><p class="error" role="alert"></p><div class="form-actions"><button type="submit">Preview import</button><button type="button" class="primary" data-action="commit-import" disabled>Import documents</button></div></form>`,
  );
}
async function act(button) {
  const { action, id } = button.dataset;
  if (action === "close") return dialog.close();
  if (action === "logout") {
    if (!confirmLeave()) return;
    await api("/auth/logout", { method: "POST" });
    state.dirty = false;
    resetView();
    return showLogin();
  }
  if (action === "refresh") {
    if (!confirmLeave()) return;
    if (state.page) return openPage(state.page.id);
    if (state.run) return openRun(state.run.id);
    resetView();
    await sidebar();
    return render();
  }
  if (action === "new-notebook") {
    if (!confirmLeave()) return;
    state.dirty = false;
    await navigate("library");
    return notebookForm();
  }
  if (action === "edit-notebook")
    return notebookForm(state.notebooks.find((n) => n.id === id));
  if (action === "new-page") return editorView();
  if (action === "page") return openPage(id);
  if (action === "edit-page") return editorView(state.page);
  if (action === "cancel-edit") {
    if (!confirmLeave()) return;
    const id = state.editing?.id;
    state.dirty = false;
    return id ? openPage(id) : navigate("library");
  }
  if (action === "preview-tab") {
    const form = $("#editor-form"),
      result = await api("/preview", {
        method: "POST",
        body: contentFrom(form),
      });
    $("#editor-preview").innerHTML = result.html;
    $("#editor-preview").hidden = false;
    $("#body-label").hidden = true;
    document
      .querySelector("[data-action=write-tab]")
      .classList.remove("active");
    button.classList.add("active");
    return;
  }
  if (action === "write-tab") {
    $("#editor-preview").hidden = true;
    $("#body-label").hidden = false;
    document
      .querySelector("[data-action=preview-tab]")
      .classList.remove("active");
    button.classList.add("active");
    return;
  }
  if (action === "bookmark") {
    await api(`/pages/${id}/bookmark`, {
      method: "PUT",
      body: { active: button.dataset.active === "true" },
    });
    return state.page ? openPage(id) : render();
  }
  if (action === "print") return window.print();
  if (["publish", "unpublish", "review", "archive"].includes(action)) {
    const p = state.page;
    let body = { base_version: p.version };
    if (action === "archive") {
      body.archived = button.dataset.active === "true";
      if (
        !confirm(
          body.archived
            ? "Archive this document? Readers will no longer see it."
            : "Restore this document? Its previously published copy becomes visible again.",
        )
      )
        return;
    }
    if (
      action === "unpublish" &&
      !confirm(
        "Hide the published copy from readers? Existing checklist runs retain their snapshots.",
      )
    )
      return;
    await api(`/pages/${p.id}/${action}`, { method: "POST", body });
    toast(
      action === "publish"
        ? "Published. Readers can now see this revision."
        : "Document updated.",
    );
    return openPage(p.id);
  }
  if (action === "history" || action === "history-page")
    return historyView(Number(button.dataset.offset || 0));
  if (action === "view-revision") {
    const r = await api(
      `/pages/${state.page.id}/revisions/${button.dataset.number}`,
    );
    return openDialog(
      "Revision " + r.number + " · " + r.title,
      r.author + " · " + date(r.created_at),
      `<article class="prose">${r.html}</article>${r.steps.length ? `<ol>${r.steps.map((s) => `<li>${h(s)}</li>`).join("")}</ol>` : ""}<button class="small" data-action="history">Back to history</button>`,
    );
  }
  if (action === "diff") {
    const result = await api(
      `/pages/${state.page.id}/diff?older=${button.dataset.number}&newer=${state.page.revision}`,
    );
    return openDialog(
      "Compare with current draft",
      "All content fields are compared as a structured snapshot.",
      `<pre class="diff">${h(result.diff || "No content differences.")}</pre><button class="small" data-action="history">Back to history</button>`,
    );
  }
  if (action === "restore-revision") {
    if (
      !confirm(
        "Create a new draft from revision " +
          button.dataset.number +
          "? This does not publish it.",
      )
    )
      return;
    const p = await api(`/pages/${state.page.id}/restore`, {
      method: "POST",
      body: {
        base_version: state.page.version,
        revision: Number(button.dataset.number),
      },
    });
    dialog.close();
    toast("Revision restored as a new draft.");
    return openPage(p.id);
  }
  if (action === "start-run") {
    const run = await api("/runs", {
      method: "POST",
      body: { page_id: state.page.id },
    });
    return openRun(run.id);
  }
  if (action === "run") return openRun(id);
  if (action === "complete-run" || action === "cancel-run") {
    if (!confirmLeave()) return;
    if (
      action === "cancel-run" &&
      !confirm(
        "Cancel this run? Its notes and progress remain in your history.",
      )
    )
      return;
    state.run = await api(
      `/runs/${state.run.id}/${action === "complete-run" ? "complete" : "cancel"}`,
      { method: "POST", body: { base_version: state.run.version } },
    );
    state.dirty = false;
    return renderRun();
  }
  if (action === "previous" || action === "next") {
    state.offset = Math.max(
      0,
      state.offset +
        (action === "next" ? 1 : -1) * Number(button.dataset.size || 50),
    );
    return render();
  }
  if (action === "clear-tag") {
    state.tag = "";
    state.offset = 0;
    return render();
  }
  if (action === "account")
    return openDialog(
      "Your account",
      state.user.username + " · " + state.user.role,
      `<form data-form="password"><label>Current password<input name="current_password" type="password" required maxlength="256" autocomplete="current-password"></label><label>New password<input name="new_password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><p class="hint">Changing your password signs out every session on your account.</p>${formActions("Change password")}</form>`,
    );
  if (action === "new-user")
    return openDialog(
      "Add a workspace account",
      "Use a unique initial password and share it securely.",
      `<form data-form="user"><label>Username<input name="username" pattern="[a-zA-Z0-9_.-]{3,64}" autocomplete="off" required></label><label>Password<input name="password" type="password" minlength="12" maxlength="256" autocomplete="new-password" required></label><label>Role<select name="role"><option value="reader">Reader · published documents and own checklists</option><option value="editor">Editor · documents, revisions, notebooks</option><option value="admin">Administrator · full workspace administration</option></select></label>${formActions("Create account")}</form>`,
    );
  if (action === "toggle-user") {
    await api("/users/" + id, {
      method: "PATCH",
      body: { active: button.dataset.active === "true" },
    });
    return render();
  }
  if (action === "delete-notebook") {
    if (!confirm("Delete this empty notebook?")) return;
    await api("/notebooks/" + id, { method: "DELETE" });
    dialog.close();
    await sidebar();
    return navigate("library");
  }
  if (action === "export")
    return openDialog(
      "Export a content batch",
      "For all history and accounts, use the server backup command instead.",
      `<form data-form="export"><div class="form-grid"><label>Start at document offset<input name="offset" type="number" min="0" value="0" required></label><label>Documents per batch<input name="limit" type="number" min="1" max="100" value="25" required></label></div><p class="hint">Export order is stable by document ID. Use the next offset shown after each download until there are no documents left.</p>${formActions("Download JSON")}</form>`,
    );
  if (action === "import") return importForm();
  if (action === "commit-import") {
    if (!state.importData) return;
    const result = await api(
      "/import?dry_run=false&conflict=" + state.importData.conflict,
      { method: "POST", body: state.importData.bundle },
    );
    state.importData = null;
    dialog.close();
    await sidebar();
    toast(`Imported ${result.created} documents; skipped ${result.skipped}.`);
    return render();
  }
}
document.addEventListener("click", async (event) => {
  try {
    const wiki = event.target.closest("[data-wiki]");
    if (wiki) {
      event.preventDefault();
      return await openPage(null, wiki.dataset.wiki);
    }
    const notebook = event.target.closest("[data-notebook]");
    if (notebook) return await navigate("library", notebook.dataset.notebook);
    const route = event.target.closest("[data-route]");
    if (route) return await navigate(route.dataset.route);
    const tag = event.target.closest("[data-tag]");
    if (tag) {
      if (!confirmLeave()) return;
      resetView();
      state.route = "library";
      state.notebook = null;
      state.tag = tag.dataset.tag;
      state.offset = 0;
      history.replaceState(null, "", "/");
      return await render();
    }
    const button = event.target.closest("[data-action]");
    if (button && !button.disabled) await act(button);
  } catch (error) {
    toast(error.message, true);
  }
});
document.addEventListener("input", (event) => {
  if (event.target.closest("#editor-form")) {
    state.dirty = true;
    if (event.target.name === "title" && !state.editing) {
      const slug = $("#editor-form [name=slug]");
      if (!slug.dataset.manual)
        slug.value = event.target.value
          .toLowerCase()
          .normalize("NFKD")
          .replace(/[\u0300-\u036f]/g, "")
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "")
          .slice(0, 100);
    }
    if (event.target.name === "slug") event.target.dataset.manual = "true";
  }
  const step = event.target.closest("[data-form=step]");
  if (step) {
    step.dataset.dirty = "true";
    state.dirty = true;
  }
});
document.addEventListener("change", (event) => {
  if (event.target.closest("[data-form=import]")) {
    state.importData = null;
    const button = document.querySelector("[data-action=commit-import]");
    if (button) button.disabled = true;
    $("#import-plan").textContent = "";
  }
  const step = event.target.closest("[data-form=step]");
  if (step) {
    step.dataset.dirty = "true";
    state.dirty = true;
  }
});
document.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target,
    submit = form.querySelector("[type=submit]"),
    error = form.querySelector(".error");
  if (submit) submit.disabled = true;
  if (error) error.textContent = "";
  try {
    const data = Object.fromEntries(new FormData(form)),
      type = form.dataset.form;
    if (form.id === "login-form") {
      const info = await api("/auth/login", { method: "POST", body: data });
      state.csrf = info.csrf_token;
      form.reset();
      await start();
      return;
    }
    if (form.id === "search-form") {
      state.q = data.q;
      state.offset = 0;
      return await render();
    }
    if (form.id === "editor-form") {
      const body = {
        ...contentFrom(form),
        notebook_id: data.notebook_id,
        review_interval_days: Number(data.review_interval_days),
      };
      if (state.editing) {
        body.base_version = state.editing.version;
        body.message = data.message || "";
      } else body.slug = data.slug;
      const page = await api(
        "/pages" + (state.editing ? "/" + state.editing.id : ""),
        { method: state.editing ? "PUT" : "POST", body },
      );
      state.dirty = false;
      toast("Draft saved. Publish it when it is ready.");
      return await openPage(page.id);
    }
    if (type === "notebook") {
      if (form.dataset.id) data.base_version = Number(form.dataset.version);
      const result = await api(
        "/notebooks" + (form.dataset.id ? "/" + form.dataset.id : ""),
        { method: form.dataset.id ? "PUT" : "POST", body: data },
      );
      dialog.close();
      await sidebar();
      if (form.dataset.next === "true") {
        state.notebook = result.id;
        return await editorView();
      }
      return await render();
    }
    if (type === "step") {
      const result = await api("/runs/" + state.run.id, {
        method: "PATCH",
        body: {
          base_version: state.run.version,
          index: Number(form.dataset.index),
          done: form.elements.done.checked,
          note: data.note,
        },
      });
      state.run = result;
      form.dataset.dirty = "false";
      state.dirty = Boolean(
        document.querySelector("[data-form=step][data-dirty=true]"),
      );
      const done = result.steps.filter((s) => s.done).length;
      $("#run-progress").textContent =
        `${done} of ${result.steps.length} steps saved as complete`;
      $("#run-bar").value = done;
      document.querySelector("[data-action=complete-run]").disabled =
        done !== result.steps.length;
      toast("Step saved.");
      return;
    }
    if (type === "user") {
      await api("/users", { method: "POST", body: data });
      dialog.close();
      return await render();
    }
    if (type === "password") {
      await api("/auth/password", { method: "POST", body: data });
      showLogin();
      toast("Password changed. Sign in again.");
      return;
    }
    if (type === "export") {
      const result = await api(
        `/export?offset=${Number(data.offset)}&limit=${Number(data.limit)}`,
      );
      download(
        "fieldnotes-content-" + data.offset + ".json",
        JSON.stringify(result, null, 2),
      );
      const count = result.documents.length;
      toast(
        count
          ? `Exported ${count} documents. Next offset: ${Number(data.offset) + count}.`
          : "No more documents at this offset.",
      );
      return;
    }
    if (type === "import") {
      const file = form.elements.file.files[0];
      if (!file) throw new Error("Choose a Fieldnotes JSON file.");
      if (file.size > 4 * 1024 * 1024)
        throw new Error("The import limit is 4 MiB. Export a smaller batch.");
      const bundle = JSON.parse(await file.text());
      const result = await api(
        "/import?dry_run=true&conflict=" + data.conflict,
        { method: "POST", body: bundle },
      );
      state.importData = { bundle, conflict: data.conflict };
      $("#import-plan").innerHTML =
        `<div class="notice purple">${result.plan.filter((p) => p.action === "create").length} documents will be created; ${result.skipped} will be skipped.</div><ul>${result.plan.map((p) => `<li>${h(p.action)} · ${h(p.source)}${p.source !== p.slug ? " → " + h(p.slug) : ""}</li>`).join("")}</ul>`;
      document.querySelector("[data-action=commit-import]").disabled = false;
      return;
    }
  } catch (exception) {
    if (error && error.isConnected) error.textContent = exception.message;
    else toast(exception.message, true);
  } finally {
    if (submit) submit.disabled = false;
  }
});
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
window.addEventListener("popstate", () => {
  if (!state.user) return;
  const slug = new URL(location.href).searchParams.get("page");
  (slug ? openPage(null, slug) : navigate("library")).catch((error) =>
    toast(error.message, true),
  );
});
start().catch((error) => {
  showLogin();
  if (error.message !== "Sign in to continue")
    $("#login-form .error").textContent = error.message;
});
