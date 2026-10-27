"use strict";

// Single-page UI over the predefined search/change APIs and the read-only /api/ask.
// The browser only sends filter values, record fields, or a question; never SQL.

const PAGE_SIZE = 25;
const state = { options: null, type: "patients", offset: 0, total: 0, requestId: 0, drawer: [] };
const $ = (id) => document.getElementById(id);

// --- DOM and formatting helpers (text is always set as text, never as HTML) ---

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "class") node.className = value;
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : String(child));
  }
  return node;
}

const words = (name) => name.replace(/^-/, "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const show = (value) => (value === null || value === undefined || value === "" ? "—" : value);
const badge = (text, cls = text) => h("span", { class: `badge ${cls}` }, words(String(text)));
const flagBadges = (item) => (item.flags || []).map((flag) => badge(flag));
const asOf = () => $("as-of-date").value;

function countBadge(count, cls) {
  return count ? h("span", { class: `badge ${cls}` }, count) : "0";
}

function dueText(days) {
  if (days === 0) return "today";
  return days < 0 ? `${-days}d late` : `in ${days}d`;
}

// --- API -----------------------------------------------------------------------

class ApiError extends Error {
  constructor(status, data) {
    const detail = data && data.detail;
    let message = "Request failed.";
    if (Array.isArray(detail)) {
      message = detail.map((e) => `${e.loc.filter((p) => p !== "body" && p !== "query").join(".")}: ${e.msg}`).join("; ");
    } else if (detail && detail.message) {
      message = detail.message;
    }
    super(message);
    this.status = status;
    this.code = detail && detail.code;
  }
}

async function api(method, path, { params = {}, body } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, item));
    else if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const isJson = (response.headers.get("content-type") || "").includes("json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) throw new ApiError(response.status, data);
  return data;
}

let toastTimer;
function toast(message, isError = false) {
  const node = $("toast");
  node.textContent = message;
  node.className = isError ? "toast error" : "toast";
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, isError ? 6000 : 3000);
}
const showError = (error) => toast(error.message || String(error), true);

// --- Filter controls -----------------------------------------------------------

const staffOptions = () => state.options.staff.map((s) => [s.staff_id, `${s.name} (${s.role})`]);
const valuesOf = (list) => list.map((value) => [value, words(value)]);

const text = (name, label) => ({ kind: "text", name, label });
const select = (name, label, options) => ({ kind: "select", name, label, options });
const checks = (name, label, options) => ({ kind: "checks", name, label, options });
const yesNo = (name, label) => select(name, label, () => [["true", "Yes"], ["false", "No"]]);
const dates = (prefix, label) => ({ kind: "dates", name: prefix, label });
const slider = (name, label, max, unit = "") => ({ kind: "slider", name, label, max, unit });

function filterControl(spec) {
  const id = `filter-${spec.name}`;
  if (spec.kind === "text") {
    return h("div", { class: "field" }, h("label", { for: id }, spec.label), h("input", { id, name: spec.name, type: "text" }));
  }
  if (spec.kind === "select") {
    return h("div", { class: "field" }, h("label", { for: id }, spec.label),
      h("select", { id, name: spec.name }, h("option", { value: "" }, "Any"),
        spec.options().map(([value, label]) => h("option", { value }, label))));
  }
  if (spec.kind === "checks") {
    return h("div", { class: "field" }, h("span", { class: "label" }, spec.label),
      h("div", { class: "checks" }, spec.options().map(([value, label]) =>
        h("label", {}, h("input", { type: "checkbox", name: spec.name, value }), label))));
  }
  if (spec.kind === "dates") {
    return h("div", { class: "field" }, h("span", { class: "label" }, spec.label),
      h("div", { class: "range-pair" },
        h("input", { type: "date", name: `${spec.name}_from`, "aria-label": `${spec.label} from` }),
        h("input", { type: "date", name: `${spec.name}_to`, "aria-label": `${spec.label} to` })));
  }
  // Slider: off until its checkbox is ticked, so an untouched slider never filters.
  const range = h("input", { id, type: "range", name: spec.name, min: 0, max: spec.max, value: 0, disabled: true });
  const output = h("output", {}, "Any");
  const toggle = h("input", { type: "checkbox", "aria-label": `Use ${spec.label}`, "data-slider": spec.name });
  const sync = () => {
    range.disabled = !toggle.checked;
    output.textContent = toggle.checked ? `${range.value}${spec.unit}` : "Any";
  };
  toggle.addEventListener("change", sync);
  range.addEventListener("input", sync);
  return h("div", { class: "field" }, h("label", { for: id }, spec.label), h("div", { class: "slider" }, toggle, range, output));
}

function filterParams() {
  const params = {};
  for (const el of $("filter-form").elements) {
    if (!el.name || el.disabled) continue;
    if (el.type === "checkbox") {
      if (el.checked) (params[el.name] ||= []).push(el.value);
    } else if (el.value !== "") {
      params[el.name] = el.value;
    }
  }
  return params;
}

function setFilters(values) {
  const form = $("filter-form");
  for (const [name, value] of Object.entries(values)) {
    const wanted = Array.isArray(value) ? value.map(String) : [String(value)];
    for (const el of form.querySelectorAll(`[name="${name}"]`)) {
      if (el.type === "checkbox") el.checked = wanted.includes(el.value);
      else el.value = wanted[0];
      if (el.type === "range") {
        const toggle = form.querySelector(`[data-slider="${name}"]`);
        toggle.checked = true;
        toggle.dispatchEvent(new Event("change"));
      }
    }
  }
}

// --- Record forms --------------------------------------------------------------

function field(name, label, extra = {}) {
  return { name, label, type: "text", ...extra };
}

async function referenceOptions(type) {
  const page = await api("GET", `/api/${type}`, { params: { limit: 1000, as_of_date: asOf() } });
  return page.items.map((item) => [item[TYPES[type].id], TYPES[type].describe(item)]);
}

function formControl(spec, value) {
  const id = `form-${spec.name}`;
  const current = value === null || value === undefined ? "" : String(value);
  let control;
  if (spec.type === "textarea") {
    control = h("textarea", { id, name: spec.name, rows: 3 }, current);
  } else if (spec.options || spec.reference) {
    control = h("select", { id, name: spec.name, required: spec.required },
      spec.required ? h("option", { value: "" }, "Choose...") : h("option", { value: "" }, "None"));
    const fill = (pairs) => {
      for (const [optionValue, label] of pairs) control.append(h("option", { value: optionValue }, label));
      control.value = current;
    };
    if (spec.options) fill(spec.options());
    else referenceOptions(spec.reference).then(fill, showError);
  } else {
    control = h("input", { id, name: spec.name, type: spec.type, value: current, required: spec.required, placeholder: spec.placeholder });
  }
  return h("div", { class: "field" }, h("label", { for: id }, spec.label + (spec.required ? " *" : "")), control);
}

function recordForm(type, record, prefill = {}) {
  const config = TYPES[type];
  const fields = config.form.filter((spec) => (record ? !spec.createOnly : !spec.editOnly));
  const form = h("form", {},
    fields.map((spec) => formControl(spec, record ? record[spec.name] : prefill[spec.name])),
    h("div", { class: "form-actions" },
      h("button", { type: "submit", class: "primary" }, record ? "Save changes" : `Create ${config.singular.toLowerCase()}`)));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {};
    for (const spec of fields) {
      const raw = form.elements[spec.name].value.trim();
      const value = raw === "" ? null : raw;
      if (!record) {
        if (value !== null) body[spec.name] = value;
      } else {
        const before = record[spec.name] === null || record[spec.name] === undefined ? null : String(record[spec.name]);
        if (value !== before) body[spec.name] = value;  // PATCH sends only changed fields
      }
    }
    if (record && Object.keys(body).length === 0) return toast("Nothing changed.");
    try {
      const params = { as_of_date: asOf() };
      const saved = record
        ? await api("PATCH", `/api/${type}/${record[config.id]}`, { params, body })
        : await api("POST", `/api/${type}`, { params, body });
      toast(record ? `Saved ${saved[config.id]}.` : `Created ${saved[config.id]}.`);
      await afterChange();
      openDetail(type, saved[config.id], { replace: true });
    } catch (error) {
      showError(error);
    }
  });
  return form;
}

async function setFollowupStatus(followupId, status) {
  try {
    await api("PATCH", `/api/followups/${followupId}`, { params: { as_of_date: asOf() }, body: { status } });
    toast(status === "done" ? `${followupId} marked done.` : `${followupId} reopened.`);
    await afterChange();
    refreshDrawer();
  } catch (error) {
    showError(error);
  }
}

function statusButton(item) {
  const done = item.status === "done";
  return h("button", {
    type: "button",
    class: "small",
    onclick: (event) => { event.stopPropagation(); setFollowupStatus(item.followup_id, done ? "open" : "done"); },
  }, done ? "Reopen" : "Mark done");
}

// --- Record types: columns, filters, and form fields -----------------------------

const column = (key, label = words(key), extra = {}) => ({ key, label, ...extra });
const number = (key, label) => column(key, label, { num: true });

const TYPES = {
  patients: {
    title: "Patients",
    singular: "Patient",
    id: "patient_id",
    describe: (p) => `${p.patient_id} · ${p.name}`,
    columns: [
      column("patient_id", "ID"), column("name"), column("phone"), column("email"),
      number("visit_count", "Visits"), number("open_followups", "Open"),
      column("overdue_followups", "Overdue", { num: true, render: (r) => countBadge(r.overdue_followups, "overdue") }),
      column("next_due_date", "Next due"), column("last_visit_date", "Last visit"),
    ],
    filters: () => [
      select("staff_id", "Seen by or assigned to", staffOptions),
      checks("flag", "Has open follow-ups that are", () => valuesOf(state.options.followup_flags)),
      checks("open_action_type", "Has open follow-up type", () => valuesOf(state.options.action_types)),
      yesNo("has_open_episode", "Has an open episode"),
      slider("open_followups_min", "Open follow-ups, at least", 20),
      slider("overdue_followups_min", "Overdue follow-ups, at least", 20),
      slider("visit_count_min", "Visits, at least", 50),
      dates("last_visit", "Last visit between"),
      dates("next_due", "Next due between"),
    ],
    form: [
      field("patient_id", "ID (leave empty to generate)", { createOnly: true }),
      field("name", "Name", { required: true }),
      field("phone", "Phone"),
      field("email", "Email", { type: "email" }),
    ],
  },
  followups: {
    title: "Follow-ups",
    singular: "Follow-up",
    id: "followup_id",
    describe: (f) => `${f.followup_id} · ${f.action_type} · ${f.patient_name}`,
    columns: [
      column("followup_id", "ID"), column("patient_name", "Patient"),
      column("action_type", "Action", { render: (r) => badge(r.action_type, "") }),
      column("due_date", "Due"),
      column("days_until_due", "When", { render: (r) => (r.status === "open" ? dueText(r.days_until_due) : "—") }),
      column("status", "Status", { render: (r) => badge(r.status) }),
      column("flags", "Flags", { render: flagBadges }),
      column("assigned_staff_name", "Assigned to"), column("visit_staff_name", "Seen by"),
      column("action", "", { render: statusButton }),
    ],
    filters: () => [
      select("preset", "Quick filter", () => state.options.presets.map((p) => [p.name, p.label])),
      checks("action_type", "Action type", () => valuesOf(state.options.action_types)),
      checks("status", "Status", () => valuesOf(state.options.followup_statuses)),
      checks("flag", "Flags", () => valuesOf(state.options.followup_flags)),
      select("assigned_staff_id", "Assigned to", staffOptions),
      yesNo("unassigned", "Unassigned"),
      select("visit_staff_id", "Seen by", staffOptions),
      checks("assigned_staff_role", "Assigned staff role", () => valuesOf(state.options.staff_roles)),
      select("episode_status", "Episode", () => valuesOf(state.options.episode_statuses)),
      text("patient_name", "Patient name"),
      text("notes", "Visit notes contain"),
      slider("due_within_days", "Due within", 90, "d"),
      slider("days_overdue_min", "Overdue by at least", 180, "d"),
      slider("completed_within_days", "Completed within the last", 90, "d"),
      dates("due", "Due between"),
      dates("visit", "Visit between"),
      dates("completed", "Completed between"),
    ],
    form: [
      field("followup_id", "ID (leave empty to generate)", { createOnly: true }),
      field("visit_id", "Visit", { required: true, createOnly: true, reference: "visits" }),
      field("action_type", "Action type", { required: true, options: () => valuesOf(state.options.action_types) }),
      field("due_date", "Due date", { type: "date", required: true }),
      field("assigned_staff_id", "Assigned to", { options: staffOptions }),
      field("status", "Status", { editOnly: true, required: true, options: () => valuesOf(state.options.followup_statuses) }),
    ],
  },
  visits: {
    title: "Visits",
    singular: "Visit",
    id: "visit_id",
    describe: (v) => `${v.visit_id} · ${v.visit_date} · ${v.patient_name}`,
    columns: [
      column("visit_id", "ID"), column("visit_date", "Date"), column("patient_name", "Patient"),
      column("staff_name", "Seen by"), column("episode_description", "Episode", { wrap: true }),
      column("notes", "Notes", { wrap: true }), number("followup_count", "Follow-ups"), number("open_followups", "Open"),
    ],
    filters: () => [
      text("patient_name", "Patient name"),
      select("staff_id", "Seen by", staffOptions),
      checks("staff_role", "Staff role", () => valuesOf(state.options.staff_roles)),
      select("episode_status", "Episode", () => valuesOf(state.options.episode_statuses)),
      text("notes", "Notes contain"),
      checks("flag", "Has follow-ups that are", () => valuesOf(state.options.followup_flags)),
      checks("followup_action_type", "Has follow-up type", () => valuesOf(state.options.action_types)),
      slider("visit_within_days", "Within the last", 365, "d"),
      slider("followup_count_min", "Follow-ups, at least", 20),
      slider("open_followups_min", "Open follow-ups, at least", 20),
      dates("visit", "Visit between"),
    ],
    form: [
      field("visit_id", "ID (leave empty to generate)", { createOnly: true }),
      field("episode_id", "Episode", { required: true, createOnly: true, reference: "episodes" }),
      field("visit_date", "Visit date", { type: "date", required: true }),
      field("staff_id", "Seen by", { options: staffOptions }),
      field("notes", "Notes", { type: "textarea" }),
    ],
  },
  episodes: {
    title: "Episodes",
    singular: "Episode",
    id: "episode_id",
    describe: (e) => `${e.episode_id} · ${e.patient_name} · ${e.description}`,
    columns: [
      column("episode_id", "ID"), column("patient_name", "Patient"), column("description", "Description", { wrap: true }),
      column("status", "Status", { render: (r) => badge(r.status) }), column("opened_at", "Opened"),
      column("closed_at", "Closed"), number("days_open", "Days open"), number("visit_count", "Visits"),
      number("open_followups", "Open follow-ups"),
    ],
    filters: () => [
      select("status", "Status", () => valuesOf(state.options.episode_statuses)),
      text("patient_name", "Patient name"),
      text("description", "Description contains"),
      select("staff_id", "Staff involved", staffOptions),
      checks("flag", "Has follow-ups that are", () => valuesOf(state.options.followup_flags)),
      slider("days_open_min", "Open for at least", 365, "d"),
      slider("visit_count_min", "Visits, at least", 50),
      slider("open_followups_min", "Open follow-ups, at least", 20),
      dates("opened", "Opened between"),
      dates("closed", "Closed between"),
    ],
    form: [
      field("episode_id", "ID (leave empty to generate)", { createOnly: true }),
      field("patient_id", "Patient", { required: true, createOnly: true, reference: "patients" }),
      field("description", "Description", { required: true }),
      field("opened_at", "Opened", { type: "date", required: true }),
      field("closed_at", "Closed (empty while open)", { type: "date" }),
    ],
  },
  staff: {
    title: "Staff",
    singular: "Staff member",
    id: "staff_id",
    describe: (s) => `${s.staff_id} · ${s.name}`,
    columns: [
      column("staff_id", "ID"), column("name"), column("role"), number("visit_count", "Visits"),
      number("patient_count", "Patients"), number("open_followups", "Open follow-ups"),
      column("overdue_followups", "Overdue", { num: true, render: (r) => countBadge(r.overdue_followups, "overdue") }),
      column("next_due_date", "Next due"),
    ],
    filters: () => [
      checks("role", "Role", () => valuesOf(state.options.staff_roles)),
      checks("flag", "Assigned follow-ups that are", () => valuesOf(state.options.followup_flags)),
      slider("open_followups_min", "Open follow-ups, at least", 50),
      slider("overdue_followups_min", "Overdue follow-ups, at least", 50),
      slider("visit_count_min", "Visits, at least", 200),
    ],
    form: [
      field("staff_id", "ID (leave empty to generate)", { createOnly: true }),
      field("name", "Name", { required: true }),
      field("role", "Role", { required: true }),
    ],
  },
};

const TABS = [["ask", "Ask"], ["patients", "Patients"], ["followups", "Follow-ups"],
  ["visits", "Visits"], ["episodes", "Episodes"], ["staff", "Staff"]];

// --- Record list -------------------------------------------------------------------

function renderFilters() {
  const config = TYPES[state.type];
  $("filter-form").replaceChildren(...config.filters().map(filterControl));
  $("search-text").value = "";
  $("sort-select").replaceChildren(h("option", { value: "" }, "Default"),
    state.options.sorts[state.type].map((sort) =>
      h("option", { value: sort }, `${words(sort)}${sort.startsWith("-") ? ", descending" : ""}`)));
  $("new-record").textContent = `New ${config.singular.toLowerCase()}`;
}

async function loadResults() {
  const config = TYPES[state.type];
  const requestId = ++state.requestId;
  const params = {
    ...filterParams(), q: $("search-text").value.trim(), sort: $("sort-select").value,
    limit: PAGE_SIZE, offset: state.offset, as_of_date: asOf(),
  };
  try {
    const page = await api("GET", `/api/${state.type}`, { params });
    if (requestId !== state.requestId) return;  // a newer search already started
    state.total = page.total;
    renderTable($("results-table"), config.columns, page.items, (row) => openDetail(state.type, row[config.id]));
    const last = Math.min(page.offset + page.items.length, page.total);
    $("result-count").textContent = `${page.total} ${page.total === 1 ? "result" : "results"}`;
    $("page-info").textContent = page.total ? `${page.offset + 1}–${last} of ${page.total}` : "";
    $("prev-page").disabled = page.offset === 0;
    $("next-page").disabled = last >= page.total;
  } catch (error) {
    if (requestId === state.requestId) showError(error);
  }
}

function renderTable(table, columns, rows, onOpen) {
  const head = h("thead", {}, h("tr", {}, columns.map((c) => h("th", { class: c.num ? "num" : "" }, c.label))));
  const body = h("tbody", {});
  if (!rows.length) {
    body.append(h("tr", {}, h("td", { colspan: columns.length, class: "empty" }, "No matching records.")));
  }
  for (const row of rows) {
    body.append(h("tr", { class: onOpen ? "clickable" : "", onclick: onOpen ? () => onOpen(row) : null },
      columns.map((c) => h("td", { class: [c.num && "num", c.wrap && "wrap"].filter(Boolean).join(" ") },
        c.render ? c.render(row) : show(row[c.key])))));
  }
  table.replaceChildren(head, body);
}

let searchTimer;
function searchSoon() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { state.offset = 0; loadResults(); }, 250);
}

// --- Detail drawer -------------------------------------------------------------------

function facts(pairs) {
  return h("dl", { class: "facts" }, pairs.map(([label, value]) => [h("dt", {}, label), h("dd", {}, value === null || value === undefined ? "—" : value)]));
}

const openLink = (type, id, label = id) =>
  h("button", { type: "button", class: "link", onclick: () => openDetail(type, id) }, label);

const addButton = (type, label, prefill) =>
  h("button", { type: "button", class: "small", onclick: () => openCreate(type, prefill) }, label);

function editSection(type, record) {
  return h("details", {}, h("summary", {}, `Edit ${TYPES[type].singular.toLowerCase()}`), recordForm(type, record));
}

function followupLine(f) {
  return h("div", { class: "followup-line" },
    openLink("followups", f.followup_id), badge(f.action_type, ""), badge(f.status),
    h("span", {}, `Due ${f.due_date} · ${f.assigned_staff_name || "Unassigned"} `, flagBadges(f)),
    statusButton(f));
}

function visitBlock(v) {
  return h("div", { class: "history" },
    h("div", { class: "row-line" }, openLink("visits", v.visit_id), h("span", { class: "grow" },
      `${v.visit_date} · ${v.staff_name || "No staff"}${v.notes ? ` · ${v.notes}` : ""}`),
      addButton("followups", "Add follow-up", { visit_id: v.visit_id })),
    (v.followups || []).map(followupLine));
}

function episodeBlock(e) {
  return h("div", { class: "history" },
    h("div", { class: "row-line" }, openLink("episodes", e.episode_id), badge(e.status),
      h("span", { class: "grow" }, `${e.description} · opened ${e.opened_at}`),
      addButton("visits", "Add visit", { episode_id: e.episode_id })),
    e.visits.map(visitBlock));
}

const DETAIL = {
  patients: (d) => [
    facts([["ID", d.patient.patient_id], ["Name", d.patient.name], ["Phone", d.patient.phone], ["Email", d.patient.email],
      ["Visits", d.patient.visit_count], ["Open follow-ups", d.patient.open_followups], ["Overdue", d.patient.overdue_followups]]),
    editSection("patients", d.patient),
    h("div", { class: "section-head" }, h("h3", {}, "Episodes and visits"),
      addButton("episodes", "Add episode", { patient_id: d.patient.patient_id })),
    d.episodes.length ? d.episodes.map(episodeBlock) : h("p", { class: "muted" }, "No episodes yet."),
  ],
  staff: (d) => [
    facts([["ID", d.staff.staff_id], ["Name", d.staff.name], ["Role", d.staff.role], ["Visits", d.staff.visit_count],
      ["Open follow-ups", d.staff.open_followups], ["Overdue", d.staff.overdue_followups]]),
    editSection("staff", d.staff),
    h("h3", {}, "Open follow-ups assigned"),
    d.open_followups.length ? d.open_followups.map(followupLine) : h("p", { class: "muted" }, "None."),
    h("h3", {}, "Recent visits"),
    d.recent_visits.length ? d.recent_visits.map(visitBlock) : h("p", { class: "muted" }, "None."),
  ],
  episodes: (d) => [
    facts([["ID", d.episode.episode_id], ["Patient", openLink("patients", d.episode.patient_id, d.episode.patient_name)],
      ["Description", d.episode.description], ["Status", badge(d.episode.status)], ["Opened", d.episode.opened_at],
      ["Closed", d.episode.closed_at], ["Days open", d.episode.days_open]]),
    editSection("episodes", d.episode),
    h("div", { class: "section-head" }, h("h3", {}, "Visits"),
      addButton("visits", "Add visit", { episode_id: d.episode.episode_id })),
    d.episode.visits.length ? d.episode.visits.map(visitBlock) : h("p", { class: "muted" }, "No visits yet."),
  ],
  visits: (d) => [
    facts([["ID", d.visit.visit_id], ["Date", d.visit.visit_date],
      ["Patient", openLink("patients", d.visit.patient_id, d.visit.patient_name)],
      ["Episode", openLink("episodes", d.visit.episode_id, d.visit.episode_description)],
      ["Seen by", d.visit.staff_name], ["Notes", d.visit.notes]]),
    editSection("visits", d.visit),
    h("div", { class: "section-head" }, h("h3", {}, "Follow-ups"),
      addButton("followups", "Add follow-up", { visit_id: d.visit.visit_id })),
    d.visit.followups.length ? d.visit.followups.map(followupLine) : h("p", { class: "muted" }, "No follow-ups."),
  ],
  followups: (d) => [
    facts([["ID", d.followup.followup_id], ["Patient", openLink("patients", d.followup.patient_id, d.followup.patient_name)],
      ["Visit", openLink("visits", d.followup.visit_id, `${d.followup.visit_id} · ${d.followup.visit_date}`)],
      ["Episode", openLink("episodes", d.followup.episode_id, d.followup.episode_description)],
      ["Action", badge(d.followup.action_type, "")], ["Due", `${d.followup.due_date} (${dueText(d.followup.days_until_due)})`],
      ["Status", h("span", {}, badge(d.followup.status), " ", statusButton(d.followup))],
      ["Flags", flagBadges(d.followup)], ["Assigned to", d.followup.assigned_staff_name],
      ["Completed at", d.followup.completed_at]]),
    editSection("followups", d.followup),
    h("h3", {}, "Other follow-ups for this episode"),
    d.episode_followups.length ? d.episode_followups.map(followupLine) : h("p", { class: "muted" }, "None."),
  ],
};

async function renderDrawer() {
  const entry = state.drawer[state.drawer.length - 1];
  if (!entry) {
    $("drawer").hidden = true;
    return;
  }
  const config = TYPES[entry.type];
  $("drawer").hidden = false;
  $("drawer-back").hidden = state.drawer.length < 2;
  if (entry.create) {
    $("drawer-title").textContent = `New ${config.singular.toLowerCase()}`;
    $("drawer-body").replaceChildren(recordForm(entry.type, null, entry.prefill));
    return;
  }
  $("drawer-title").textContent = `${config.singular} ${entry.id}`;
  try {
    const detail = await api("GET", `/api/${entry.type}/${entry.id}`, { params: { as_of_date: asOf() } });
    if (state.drawer[state.drawer.length - 1] !== entry) return;
    $("drawer-body").replaceChildren(...DETAIL[entry.type](detail).flat());
  } catch (error) {
    $("drawer-body").replaceChildren(h("p", { class: "notice" }, error.message));
  }
}

function openDetail(type, id, { replace = false } = {}) {
  if (replace) state.drawer.pop();
  state.drawer.push({ type, id });
  renderDrawer();
}

function openCreate(type, prefill = {}) {
  state.drawer.push({ type, create: true, prefill });
  renderDrawer();
}

const refreshDrawer = () => { if (state.drawer.length) renderDrawer(); };

async function afterChange() {
  await Promise.all([loadOptions(), loadDashboard()]);
  if (state.type !== "ask") loadResults();
}

// --- Dashboard -------------------------------------------------------------------------

async function loadDashboard() {
  try {
    const d = await api("GET", "/api/dashboard", { params: { as_of_date: asOf() } });
    const card = (value, label, cls, type, filters) => h("button", {
      type: "button", class: `stat ${value ? cls : ""}`, onclick: () => switchTab(type, filters),
    }, h("strong", {}, value), h("span", {}, label));
    $("dashboard").replaceChildren(
      card(d.followups.overdue_followups, "Overdue follow-ups", "alert", "followups", { preset: "overdue" }),
      card(d.followups.due_soon_followups, `Due in ${state.options ? state.options.due_soon_days : 7} days`, "warn", "followups", { preset: "due_soon" }),
      card(d.followups.unassigned_followups, "Unassigned", "warn", "followups", { preset: "unassigned" }),
      card(d.followups.open_followups, "Open follow-ups", "", "followups", { status: ["open"] }),
      card(d.completed_last_7_days, "Completed, last 7 days", "", "followups", { preset: "completed_last_7_days" }),
      card(d.patients, "Patients", "", "patients", {}),
      card(d.patients_with_overdue, "Patients with overdue", "alert", "patients", { flag: ["overdue"] }),
      card(d.open_episodes, "Open episodes", "", "episodes", { status: "open" }),
      card(d.visits_last_30_days, "Visits, last 30 days", "", "visits", { visit_within_days: 30 }),
    );
  } catch (error) {
    $("dashboard").replaceChildren(h("p", { class: "notice" }, error.message));
  }
}

async function loadOptions() {
  state.options = await api("GET", "/api/options", { params: { as_of_date: asOf() } });
}

// --- Natural-language questions ------------------------------------------------------

const EXAMPLES = [
  "Which patients have overdue follow-ups, and who is assigned to them?",
  "How many visits did each staff member have in the last 30 days?",
  "List open referrals due in the next two weeks.",
  "Which episodes have been open for more than 30 days?",
  "Mark F001 as done",
];

async function ask(question) {
  const button = $("ask-form").querySelector("button[type=submit]");
  button.disabled = true;
  button.textContent = "Asking...";
  $("ask-result").replaceChildren(h("p", { class: "muted" }, "Checking the question and searching..."));
  try {
    const answer = await api("POST", "/api/ask", { body: { question, as_of_date: asOf() } });
    const table = h("table", {});
    renderTable(table, answer.result.columns.map((name, index) => ({ key: index, label: name })), answer.result.rows, null);
    $("ask-result").replaceChildren(h("div", { class: "answer" },
      h("div", { class: "row-line" }, badge(answer.decision.intent),
        h("span", { class: "muted" }, `confidence ${answer.decision.confidence.toFixed(2)} · change probability ${answer.decision.modify_probability.toFixed(2)}`)),
      h("p", { class: "explanation" }, answer.explanation),
      h("details", {}, h("summary", {}, "SQL that was run (read only)"),
        h("pre", {}, answer.sql), h("pre", {}, `parameters: ${JSON.stringify(answer.parameters)}`)),
      h("div", { class: "table-wrap" }, table),
      h("p", { class: "muted" }, `${answer.result.row_count} rows${answer.result.truncated ? " (truncated)" : ""}`)));
  } catch (error) {
    const hint = error.code === "modification_not_allowed"
      ? " Questions are read only. To change a record, open it from a list and use Edit."
      : "";
    $("ask-result").replaceChildren(h("p", { class: "notice" }, error.message + hint));
  } finally {
    button.disabled = false;
    button.textContent = "Ask";
  }
}

// --- Tabs and startup ------------------------------------------------------------------

function switchTab(type, filters = null) {
  state.drawer = [];
  renderDrawer();
  state.type = type;
  state.offset = 0;
  history.replaceState(null, "", `#${type}`);
  for (const button of $("tabs").children) button.setAttribute("aria-selected", String(button.dataset.tab === type));
  $("ask-view").hidden = type !== "ask";
  $("records-view").hidden = type === "ask";
  if (type === "ask") return;
  renderFilters();
  if (filters) setFilters(filters);
  loadResults();
}

async function start() {
  $("as-of-date").value = new Date().toLocaleDateString("en-CA");  // YYYY-MM-DD in local time
  $("tabs").replaceChildren(...TABS.map(([tab, label]) =>
    h("button", { type: "button", role: "tab", "data-tab": tab, onclick: () => switchTab(tab) }, label)));
  $("ask-examples").replaceChildren(...EXAMPLES.map((example) => h("button", {
    type: "button", onclick: () => { $("ask-question").value = example; ask(example); },
  }, example)));

  $("filter-form").addEventListener("input", searchSoon);
  $("filter-form").addEventListener("change", searchSoon);
  $("filter-form").addEventListener("submit", (event) => event.preventDefault());
  $("search-text").addEventListener("input", searchSoon);
  $("sort-select").addEventListener("change", searchSoon);
  $("clear-filters").addEventListener("click", () => { renderFilters(); searchSoon(); });
  $("prev-page").addEventListener("click", () => { state.offset = Math.max(0, state.offset - PAGE_SIZE); loadResults(); });
  $("next-page").addEventListener("click", () => { state.offset += PAGE_SIZE; loadResults(); });
  $("new-record").addEventListener("click", () => openCreate(state.type));
  $("drawer-close").addEventListener("click", () => { state.drawer = []; renderDrawer(); });
  $("drawer-back").addEventListener("click", () => { state.drawer.pop(); renderDrawer(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.drawer.length) { state.drawer = []; renderDrawer(); }
  });
  $("ask-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const question = $("ask-question").value.trim();
    if (question) ask(question);
  });
  $("as-of-date").addEventListener("change", async () => {
    await afterChange();
    refreshDrawer();
  });

  try {
    await loadOptions();
  } catch (error) {
    $("dashboard").replaceChildren(h("p", { class: "notice" }, error.message));
    return;
  }
  loadDashboard();
  const requested = window.location.hash.slice(1);
  switchTab(TABS.some(([tab]) => tab === requested) ? requested : "patients");
}

start();
