import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { JSDOM, VirtualConsole } from "jsdom";

const base = process.env.SMOKE_BASE_URL,
  password = process.env.SMOKE_PASSWORD;
assert(base && password, "Launch with python scripts/ui_smoke.py");
const errors = [],
  virtualConsole = new VirtualConsole();
virtualConsole.on("jsdomError", (error) => errors.push(error.message));
const dom = new JSDOM(
  await fs.readFile("fieldnotes/static/index.html", "utf8"),
  {
    url: base,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  },
);
const w = dom.window;
w.HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
w.HTMLDialogElement.prototype.close = function () {
  this.open = false;
};
w.confirm = () => true;
let cookie = "";
w.fetch = async (path, options = {}) => {
  const response = await fetch(new URL(path, base), {
    ...options,
    headers: { ...options.headers, ...(cookie ? { Cookie: cookie } : {}) },
  });
  const set = response.headers.get("set-cookie");
  if (set) cookie = set.split(";")[0];
  return response;
};
const common = (
  await fs.readFile("fieldnotes/static/common.js", "utf8")
).replaceAll("export const ", "const ");
const app = (await fs.readFile("fieldnotes/static/app.js", "utf8")).replace(
  /^import .*?;\n/,
  "",
);
w.eval(common + "\n" + app);
const find = (s) => {
  const node = w.document.querySelector(s);
  assert(node, "Missing " + s);
  return node;
};
const exists = (s) => Boolean(w.document.querySelector(s));
const main = () => find("#main").textContent;
async function waitFor(predicate, label) {
  for (let i = 0; i < 150; i++) {
    if (predicate()) return;
    await new Promise((r) => setTimeout(r, 40));
  }
  throw new Error(
    `Timed out: ${label}; ${[...w.document.querySelectorAll(".error")].map((e) => e.textContent).join("; ")}`,
  );
}
function fill(s, value) {
  find(s).value = value;
  find(s).dispatchEvent(new w.Event("input", { bubbles: true }));
}
function click(s) {
  find(s).click();
}
function submit(s) {
  find(s).dispatchEvent(
    new w.Event("submit", { bubbles: true, cancelable: true }),
  );
}
try {
  await waitFor(() => !find("#login-screen").hidden, "login");
  fill("[name=username]", "demo-admin");
  fill("[name=password]", password);
  submit("#login-form");
  await waitFor(() => main().includes("weekly workshop reset"), "library");
  click("[data-action=new-notebook]");
  await waitFor(() => exists("[data-form=notebook]"), "notebook form");
  fill("#dialog [name=name]", "UI notebook");
  submit("[data-form=notebook]");
  await waitFor(
    () =>
      find("#notebook-nav").textContent.includes("UI notebook") &&
      !find("#dialog").open,
    "notebook",
  );
  click("[data-action=new-page]");
  fill("#editor-form [name=title]", "Interface test guide");
  fill(
    "#editor-form [name=body]",
    "# Useful guide\n\n<script>alert(1)</script>\n\n[[welcome-to-fieldnotes]]",
  );
  fill("#editor-form [name=steps]", "Sort the notes\nLabel the folder");
  fill("#editor-form [name=tags]", "test, guide");
  click("[data-action=preview-tab]");
  await waitFor(() => !find("#editor-preview").hidden, "preview");
  assert.equal(find("#editor-preview").querySelector("script"), null);
  submit("#editor-form");
  await waitFor(() => exists("[data-action=publish]"), "draft saved");
  click("[data-action=publish]");
  await waitFor(() => exists("[data-action=unpublish]"), "publication");
  click("[data-action=bookmark]");
  await waitFor(
    () => find("[data-action=bookmark]").dataset.active === "false",
    "bookmark",
  );
  click("[data-action=edit-page]");
  fill("#editor-form [name=title]", "New draft title");
  submit("#editor-form");
  await waitFor(
    () => main().includes("Readers still see published revision 1"),
    "draft separation",
  );
  click("#main [data-action=history]");
  await waitFor(() => exists("[data-action=restore-revision]"), "history");
  click('[data-action=diff][data-number="1"]');
  await waitFor(() => exists(".diff"), "diff");
  assert(find(".diff").textContent.includes("New draft title"));
  click("[data-action=close]");
  click("[data-action=start-run]");
  await waitFor(() => exists("[data-form=step]"), "checklist run");
  assert(
    main().includes("Interface test guide"),
    "Run should use published title",
  );
  for (let index = 0; index < 2; index++) {
    const form = `[data-form=step][data-index="${index}"]`;
    find(form + " [name=done]").checked = true;
    fill(form + " [name=note]", "<img src=x onerror=alert(1)> saved text");
    submit(form);
    await waitFor(
      () => find("#run-progress").textContent.startsWith(String(index + 1)),
      "saved step",
    );
  }
  click("[data-action=complete-run]");
  await waitFor(
    () => main().includes("Completed") && !exists("[data-action=complete-run]"),
    "finish run",
  );
  assert.equal(find("#main").querySelector("img"), null);
  click("nav [data-route=bookmarks]");
  await waitFor(() => main().includes("New draft title"), "bookmark list");
  click("[data-action=page]");
  await waitFor(() => exists("#main [data-action=history]"), "reopen");
  click("#main [data-action=history]");
  await waitFor(
    () => exists("[data-action=restore-revision]"),
    "history again",
  );
  click('[data-action=restore-revision][data-number="1"]');
  await waitFor(() => main().includes("draft revision 3"), "restored draft");
  click("[data-route=workspace]");
  await waitFor(() => exists("[data-action=import]"), "admin workspace");
  click("[data-action=new-user]");
  fill("#dialog [name=username]", "ui-reader");
  fill("#dialog [name=password]", password);
  submit("[data-form=user]");
  await waitFor(() => main().includes("ui-reader"), "new account");
  click("[data-route=audit]");
  await waitFor(() => main().includes("page.revision_restored"), "audit");
  click("[data-action=logout]");
  await waitFor(() => !find("#login-screen").hidden, "logout");
  assert.deepEqual(errors, []);
  console.log(
    "UI integration passed: login, notebook, draft, preview, publish, bookmark, edit, history/diff/restore, published checklist snapshot, notes, completion, account creation, audit, logout.",
  );
} finally {
  w.close();
}
