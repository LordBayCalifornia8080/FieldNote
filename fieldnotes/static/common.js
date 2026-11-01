export const h = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const date = (value) =>
  value
    ? new Date(value * 1000).toLocaleDateString([], {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "Not yet";
export const badge = (value) =>
  `<span class="badge ${h(value)}">${h(value)}</span>`;
export const empty = (title, copy, action = "") =>
  `<div class="empty"><span aria-hidden="true">⌑</span><h3>${h(title)}</h3><p>${h(copy)}</p>${action}</div>`;
