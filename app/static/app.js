"use strict";

// Single-page UI over the predefined search/change APIs and the read-only /api/ask.
// The browser only sends filter values, record fields, or a question; never SQL.

const PAGE_SIZES = [25, 100, 500];
const state = { session: null, options: null, type: "patients", offset: 0, total: 0, pageSize: PAGE_SIZES[0], requestId: 0, drawer: [] };
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
  if (days === null || days === undefined) return "not scheduled";
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

function apiUrl(path, params = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((item) => url.searchParams.append(key, item));
    else if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  return url;
}

async function api(method, path, { params = {}, body } = {}) {
  const url = apiUrl(path, params);
  const response = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 204) return null;  // no content, e.g. after signing out
  const isJson = (response.headers.get("content-type") || "").includes("json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const error = new ApiError(response.status, data);
    if (error.code === "not_signed_in" && state.session) showSignIn();  // session ended, e.g. after a restart
    throw error;
  }
  return data;
}

// --- Sign-in: staff email only in this release -------------------------------------

const isManager = () => Boolean(state.session && state.session.is_manager);

function showSignIn() {
  state.session = null;
  for (const id of ["dashboard", "tabs", "records-view", "ask-view", "report-link", "session"]) $(id).hidden = true;
  document.querySelector("main").hidden = true;
  $("sign-in").hidden = false;
  $("sign-in-email").focus();
}

async function signIn(event) {
  event.preventDefault();
  try {
    await api("POST", "/api/session", { body: { email: $("sign-in-email").value.trim() } });
    window.location.reload();
  } catch (error) {
    $("sign-in-error").textContent = error.message;
    $("sign-in-error").hidden = false;
  }
}

async function signOut() {
  await api("DELETE", "/api/session");
  window.location.reload();
}

// --- Importing a file (managers): all of it, or nothing --------------------------------

async function importFile(file) {
  const show = (...content) => { $("import-result").replaceChildren(...content); $("import-dialog").showModal(); };
  let data;
  try {
    data = JSON.parse(await file.text());
  } catch {
    return show(h("h2", {}, "File rejected"), h("p", {}, `${file.name} is not valid JSON. Nothing was saved.`));
  }
  const response = await fetch("/api/import", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  const body = await response.json();
  if (response.ok) {
    show(h("h2", {}, `Imported ${file.name}`),
      h("p", {}, Object.entries(body.counts).map(([table, count]) => `${count} ${table}`).join(", ")));
    return afterChange();
  }
  if (body.rejections) {
    const rows = body.rejections.map((r) => ({ kind: words(r.kind), record_id: r.record_id, reason: r.reason }));
    const table = h("table", { class: "sheet" });
    renderTable(table, [column("kind", "Record"), column("record_id", "ID"), column("reason", "Reason", { wrap: true })], rows, null);
    return show(h("h2", {}, `${file.name} was rejected: nothing was saved`),
      h("p", { class: "muted" }, `Fix these ${rows.length} problem(s) and import the whole file again.`),
      h("div", { class: "table-wrap" }, table));
  }
  show(h("h2", {}, "File rejected"), h("p", {}, new ApiError(response.status, body).message));
}

function updateReportLink() {
  $("report-link").href = `/report?as_of_date=${encodeURIComponent(asOf())}`;
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

const STATUS_MESSAGES = { done: "marked done", closed: "closed", open: "reopened" };

async function setFollowupStatus(followupId, status, notes) {
  try {
    const body = notes ? { status, notes } : { status };
    await api("PATCH", `/api/followups/${followupId}`, { params: { as_of_date: asOf() }, body });
    toast(`${followupId} ${STATUS_MESSAGES[status]}.`);
    await afterChange();
    refreshDrawer();
  } catch (error) {
    showError(error);
  }
}

function statusButton(item) {
  const finished = item.status !== "open";
  return h("button", {
    type: "button",
    class: "small",
    onclick: (event) => { event.stopPropagation(); setFollowupStatus(item.followup_id, finished ? "open" : "done"); },
  }, finished ? "Reopen" : "Mark done");
}

// Closing means the follow-up could not be completed, so the clinic records why.
function askClosingReason(followupId) {
  const reason = window.prompt(`Why is ${followupId} being closed? (for example: patient unreachable, did not return)`);
  return reason && reason.trim() ? reason.trim() : null;
}

function statusSelect(item) {
  return h("select", {
    class: `status-select ${item.status}`,
    "aria-label": `Status of ${item.followup_id}`,
    onclick: (event) => event.stopPropagation(),
    onchange: (event) => {
      const status = event.target.value;
      if (status !== "closed") return setFollowupStatus(item.followup_id, status);
      const reason = askClosingReason(item.followup_id);
      if (reason) return setFollowupStatus(item.followup_id, status, reason);
      event.target.value = item.status;  // no reason given: nothing changes
    },
  }, state.options.followup_statuses.map((status) => h("option", { value: status, selected: status === item.status }, words(status))));
}

// Row tint for at-a-glance checking: the most urgent state wins.
function followupRowClass(item) {
  if (item.status !== "open") return "row-closed";
  for (const flag of ["overdue", "due_soon", "unassigned"]) if (item.flags.includes(flag)) return `row-${flag}`;
  return "";
}
const summaryRowClass = (row) => (row.overdue_followups ? "row-overdue" : row.due_soon_followups ? "row-due_soon" : "");

// --- Record types: columns, filters, and form fields -----------------------------

const column = (key, label = words(key), extra = {}) => ({ key, label, ...extra });
const number = (key, label) => column(key, label, { num: true });

const TYPES = {
  patients: {
    title: "Patients",
    singular: "Patient",
    id: "patient_id",
    rowClass: summaryRowClass,
    describe: (p) => `${p.patient_id} · ${p.name}`,
    columns: [
      column("patient_id", "ID"), column("name"), column("phone"), column("email"),
      number("visit_count", "Visits"), number("open_followups", "Open"),
      column("overdue_followups", "Overdue", { num: true, render: (r) => countBadge(r.overdue_followups, "overdue") }),
      column("next_due_date", "Next scheduled"), column("last_visit_date", "Last visit"),
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
      dates("next_due", "Next scheduled between"),
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
      column("due_date", "Scheduled"),
      column("days_until_due", "When", { render: (r) => (r.status === "open" ? dueText(r.days_until_due) : "—") }),
      column("status", "Status", { render: statusSelect }),
      column("flags", "Flags", { render: flagBadges }),
      column("assigned_staff_name", "Assigned to"), column("visit_staff_name", "Seen by"),
    ],
    rowClass: followupRowClass,
    filters: () => [
      select("preset", "Quick filter", () => state.options.presets.map((p) => [p.name, p.label])),
      checks("action_type", "Action type", () => valuesOf(state.options.action_types)),
      checks("status", "Status", () => valuesOf(state.options.followup_statuses)),
      checks("flag", "Flags", () => valuesOf(state.options.followup_flags)),
      select("assigned_staff_id", "Assigned to", staffOptions),
      select("visit_staff_id", "Seen by", staffOptions),
      checks("assigned_staff_role", "Assigned staff role", () => valuesOf(state.options.staff_roles)),
      select("episode_status", "Episode", () => valuesOf(state.options.episode_statuses)),
      text("patient_name", "Patient name"),
      text("notes", "Visit notes contain"),
      slider("due_within_days", "Scheduled within", 90, "d"),
      slider("days_overdue_min", "Overdue by at least", 180, "d"),
      slider("completed_within_days", "Completed within the last", 90, "d"),
      dates("due", "Scheduled between"),
      dates("visit", "Visit between"),
      dates("completed", "Completed between"),
    ],
    form: [
      field("followup_id", "ID (leave empty to generate)", { createOnly: true }),
      field("visit_id", "Visit", { required: true, createOnly: true, reference: "visits" }),
      field("action_type", "Action type", { required: true, options: () => valuesOf(state.options.action_types) }),
      field("due_date", "Scheduled date (leave empty while unassigned)", { type: "date" }),
      field("assigned_staff_id", "Assigned to", { required: true, options: staffOptions }),
      field("status", "Status", { editOnly: true, required: true, options: () => valuesOf(state.options.followup_statuses) }),
      field("notes", "Notes (required reason when closed)", { type: "textarea" }),
    ],
  },
  visits: {
    title: "Visits",
    singular: "Visit",
    id: "visit_id",
    rowClass: summaryRowClass,
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
      field("staff_id", "Seen by", { required: true, options: staffOptions }),
      field("notes", "Notes", { type: "textarea" }),
    ],
  },
  episodes: {
    title: "Episodes",
    singular: "Episode",
    id: "episode_id",
    rowClass: summaryRowClass,
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
    rowClass: summaryRowClass,
    describe: (s) => `${s.staff_id} · ${s.name}`,
    columns: [
      column("staff_id", "ID"), column("name"), column("role"), column("email"), number("visit_count", "Visits"),
      number("patient_count", "Patients"), number("open_followups", "Open follow-ups"),
      column("overdue_followups", "Overdue", { num: true, render: (r) => countBadge(r.overdue_followups, "overdue") }),
      column("next_due_date", "Next scheduled"),
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
      field("role", "Role (manager sees every follow-up)", { required: true }),
      field("email", "Email (used to sign in)", { type: "email" }),
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
    ...state.options.sorts[state.type].map((sort) =>
      h("option", { value: sort }, `${words(sort)}${sort.startsWith("-") ? ", descending" : ""}`)));
  $("new-record").textContent = `New ${config.singular.toLowerCase()}`;
}

// The list and its CSV download use the same filters, search text, sort, and date.
const listParams = () => ({
  ...filterParams(), q: $("search-text").value.trim(), sort: $("sort-select").value, as_of_date: asOf(),
});

async function loadResults() {
  const config = TYPES[state.type];
  const requestId = ++state.requestId;
  const params = { ...listParams(), limit: state.pageSize, offset: state.offset };
  try {
    const page = await api("GET", `/api/${state.type}`, { params });
    if (requestId !== state.requestId) return;  // a newer search already started
    state.total = page.total;
    renderTable($("results-table"), config.columns, page.items, (row) => openDetail(state.type, row[config.id]), {
      rowClass: config.rowClass, sorts: state.options.sorts[state.type], sort: $("sort-select").value, onSort: sortBy,
    });
    const last = Math.min(page.offset + page.items.length, page.total);
    $("result-count").textContent = `${page.total} ${page.total === 1 ? "result" : "results"}`;
    $("page-info").textContent = page.total ? `${page.offset + 1}–${last} of ${page.total}` : "";
    $("prev-page").disabled = page.offset === 0;
    $("next-page").disabled = last >= page.total;
  } catch (error) {
    if (requestId === state.requestId) showError(error);
  }
}

function headerCell(c, { sorts = [], sort = "", onSort } = {}) {
  const sortable = onSort && (sorts.includes(c.key) || sorts.includes(`-${c.key}`));
  if (!sortable) return h("th", { class: c.num ? "num" : "" }, c.label);
  const arrow = sort === c.key ? " ▲" : sort === `-${c.key}` ? " ▼" : "";
  return h("th", { class: `sortable ${c.num ? "num" : ""}`, "aria-sort": arrow ? (arrow === " ▲" ? "ascending" : "descending") : null },
    h("button", { type: "button", class: "sort", onclick: () => onSort(c.key) }, c.label, arrow));
}

function renderTable(table, columns, rows, onOpen, options = {}) {
  const head = h("thead", {}, h("tr", {}, columns.map((c) => headerCell(c, options))));
  const body = h("tbody", {});
  if (!rows.length) {
    body.append(h("tr", {}, h("td", { colspan: columns.length, class: "empty" }, "No matching records.")));
  }
  for (const row of rows) {
    const tint = options.rowClass ? options.rowClass(row) : "";
    body.append(h("tr", { class: [onOpen && "clickable", tint].filter(Boolean).join(" "), onclick: onOpen ? () => onOpen(row) : null },
      columns.map((c) => h("td", { class: [c.num && "num", c.wrap && "wrap"].filter(Boolean).join(" ") },
        c.render ? c.render(row) : show(row[c.key])))));
  }
  table.replaceChildren(head, body);
}

// Click a header to sort by it; click again for the reverse order when it exists.
function sortBy(key) {
  const sorts = state.options.sorts[state.type];
  const current = $("sort-select").value;
  let next = current === key ? `-${key}` : key;
  if (!sorts.includes(next)) next = sorts.includes(key) ? key : `-${key}`;
  $("sort-select").value = next;
  state.offset = 0;
  loadResults();
}

async function downloadCsv() {
  try {
    const response = await fetch(apiUrl(`/api/${state.type}/export`, listParams()));
    if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => null));
    const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") || "");
    const link = h("a", { href: URL.createObjectURL(await response.blob()), download: name ? name[1] : `${state.type}.csv` });
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    toast(`Downloaded ${state.total} ${state.total === 1 ? "row" : "rows"}.`);
  } catch (error) {
    showError(error);
  }
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

// Only a manager adds or edits records; other staff edit the follow-ups assigned to them.
const addButton = (type, label, prefill) => isManager()
  ? h("button", { type: "button", class: "small", onclick: () => openCreate(type, prefill) }, label)
  : null;

function editSection(type, record) {
  if (!isManager() && type !== "followups") return null;
  return h("details", {}, h("summary", {}, `Edit ${TYPES[type].singular.toLowerCase()}`), recordForm(type, record));
}

const HISTORY_FIELDS = { status: "Status", due_date: "Scheduled date", assigned_staff_id: "Staff" };

function historyValue(field, value) {
  if (value === null) return field === "due_date" ? "not scheduled" : "—";
  if (field === "status") return words(value);
  if (field === "assigned_staff_id") {
    const member = state.options.staff.find((s) => s.staff_id === value);
    return member ? member.name : value;
  }
  return value;
}

function historyLine(change) {
  const when = change.changed_at.replace("T", " ").replace("Z", " UTC");
  const by = change.changed_by_name ? ` · by ${change.changed_by_name}` : "";
  return h("li", {},
    `${when} · ${HISTORY_FIELDS[change.field]}: ${historyValue(change.field, change.old_value)} → ${historyValue(change.field, change.new_value)}${by}`,
    change.note ? h("span", { class: "muted" }, ` · ${change.note}`) : null);
}

function followupLine(f) {
  return h("div", { class: "followup-line" },
    openLink("followups", f.followup_id), badge(f.action_type, ""), badge(f.status),
    h("span", {}, `${f.due_date ? `Scheduled ${f.due_date}` : "Not scheduled"} · ${f.assigned_staff_name} `, flagBadges(f)),
    statusButton(f));
}

function visitBlock(v) {
  return h("div", { class: "history" },
    h("div", { class: "row-line" }, openLink("visits", v.visit_id), h("span", { class: "grow" },
      `${v.visit_date} · ${v.staff_name}${v.notes ? ` · ${v.notes}` : ""}`),
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
      ["Action", badge(d.followup.action_type, "")], ["Scheduled", d.followup.due_date ? `${d.followup.due_date} (${dueText(d.followup.days_until_due)})` : "Not scheduled"],
      ["Status", h("span", {}, badge(d.followup.status), " ", statusButton(d.followup))],
      ["Flags", flagBadges(d.followup)], ["Assigned to", d.followup.assigned_staff_name],
      ["Done or closed at", d.followup.completed_at], ["Notes", d.followup.notes]]),
    h("h3", {}, "History"),
    d.history.length
      ? h("ol", { class: "status-history" }, d.history.map(historyLine))
      : h("p", { class: "muted" }, "No changes yet."),
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
      card(d.followups.due_soon_followups, "Due soon", "warn", "followups", { preset: "due_soon" }),
      card(d.followups.unassigned_followups, "Unassigned (no date)", "warn", "followups", { preset: "unassigned" }),
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
  $("records-view").dataset.type = type;
  if (type === "ask") return;
  renderFilters();
  if (filters) setFilters(filters);
  loadResults();
}

async function start() {
  $("as-of-date").value = new Date().toLocaleDateString("en-CA");  // YYYY-MM-DD in local time
  $("sign-in-form").addEventListener("submit", signIn);
  try {
    state.session = await api("GET", "/api/session");
  } catch (error) {
    if (error.status === 401) return showSignIn();
    $("dashboard").replaceChildren(h("p", { class: "notice" }, error.message));
    return;
  }
  const { name, role } = state.session;
  $("session-name").textContent = `${name} (${role})`;
  $("session").hidden = false;
  $("report-link").hidden = false;
  updateReportLink();
  $("sign-out").addEventListener("click", signOut);
  $("new-record").hidden = !isManager();
  $("import-button").hidden = !isManager();
  $("import-button").addEventListener("click", () => $("import-input").click());
  $("import-input").addEventListener("change", async () => {
    const [file] = $("import-input").files;
    $("import-input").value = "";
    if (file) await importFile(file);
  });

  const tabs = TABS;
  if (!isManager()) $("ask-scope").hidden = false;
  $("tabs").replaceChildren(...tabs.map(([tab, label]) =>
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
  $("prev-page").addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.pageSize); loadResults(); });
  $("next-page").addEventListener("click", () => { state.offset += state.pageSize; loadResults(); });
  $("page-size").replaceChildren(...PAGE_SIZES.map((size) => h("option", { value: size }, size)));
  $("page-size").addEventListener("change", () => { state.pageSize = Number($("page-size").value); state.offset = 0; loadResults(); });
  $("download-csv").addEventListener("click", downloadCsv);
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
    updateReportLink();
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
  switchTab(tabs.some(([tab]) => tab === requested) ? requested : isManager() ? "patients" : "followups");
}

start();
