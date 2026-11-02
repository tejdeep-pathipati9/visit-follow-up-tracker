import type { Params } from "./types";
import { ApiError } from "./api";
import { localDate } from "./types";
import type {
  Attention,
  CalendarEvent,
  Followup,
  RequestOptions,
  Counts,
  Staff,
} from "./types";

// Explicitly selected synthetic preview. All records remain in memory.
const staff: Staff[] = [
  { staff_id: "S001", name: "Dr. Maya Chen", role: "doctor" },
  { staff_id: "S002", name: "Dr. James Wilson", role: "doctor" },
  { staff_id: "S003", name: "Nurse Ana Rivera", role: "nurse" },
  { staff_id: "S004", name: "Nurse Liam Scott", role: "nurse" },
];
const names = [
  "Amelia Brooks",
  "Oliver Bennett",
  "Sofia Martinez",
  "Ethan Parker",
  "Mia Thompson",
  "Noah Williams",
  "Isabella Clark",
  "Lucas Anderson",
  "Ava Mitchell",
  "Benjamin Lee",
  "Charlotte Davis",
  "Henry Roberts",
  "Evelyn Turner",
  "Daniel Kim",
  "Olivia Morgan",
  "Liam Campbell",
];
const offsets = [-5, -3, -2, -1, -1, -2, 0, 1, 3, 5, 14, 21, -7, -9, -12, -4];
const relative = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const records: Followup[] = names.map((name, i) => {
  const owner = staff[i % 4];
  const type = (["lab", "referral", "recheck"] as const)[i % 3];
  const id = (p: string) => p + String(i + 1).padStart(3, "0");
  return {
    followup_id: id("F"),
    patient_id: id("P"),
    patient_name: name,
    visit_id: id("V"),
    episode_id: id("E"),
    episode_description: `${type === "lab" ? "Routine laboratory" : type === "referral" ? "Specialist referral" : "Scheduled recheck"} follow-up`,
    visit_date: relative(-18 - i),
    action_type: type,
    due_date: [2, 5, 8].includes(i) ? null : relative(offsets[i]),
    status: i === 15 ? "closed" : i > 11 ? "done" : "open",
    flags: [],
    assigned_staff_id: owner.staff_id,
    assigned_staff_name: owner.name,
    assigned_staff_role: owner.role,
    visit_staff_id: staff[i % 2].staff_id,
    visit_staff_name: staff[i % 2].name,
    visit_staff_role: "doctor",
    visit_notes:
      type === "lab"
        ? "Lab work requested during the last visit. Confirm the appointment and track receipt of results."
        : type === "referral"
          ? "Referral sent to the specialist office. Confirm the patient has received the scheduling details."
          : "A return visit was requested. Contact the patient to confirm their appointment.",
    notes:
      i === 15
        ? "Duplicate request; replacement follow-up is being tracked."
        : null,
    completed_at: i > 11 ? relative(-2) + "T14:30:00Z" : null,
    episode_closed_at: null,
    days_until_due: 0,
  };
});
// Important dates for the sample calendar, relative to today.
const event = (
  n: number,
  title: string,
  days: number,
  start_time: string | null,
  owner: Staff | null,
  notes: string | null = null,
): CalendarEvent => ({
  event_id: "C" + String(n).padStart(3, "0"),
  title,
  event_date: relative(days),
  start_time,
  staff_id: owner?.staff_id ?? null,
  staff_name: owner?.name ?? null,
  notes,
  created_by: staff[0].staff_id,
  created_by_name: staff[0].name,
});
const events: CalendarEvent[] = [
  event(1, "Team huddle", 0, "08:30", null, "Review overdue follow-ups."),
  event(2, "Lab courier pickup", 2, "14:00", staff[2]),
  event(3, "Referral desk training", 6, "12:00", null),
  event(4, "Clinic closed", 9, null, null, "Staff training day."),
  event(5, "Dr. Chen on leave", 13, null, staff[0]),
];
export function sampleCounts(rows: Followup[]): Counts {
  const open = rows.filter((r) => r.status === "open");
  return {
    followup_count: rows.length,
    open_followups: open.length,
    done_followups: rows.filter((r) => r.status === "done").length,
    closed_followups: rows.filter((r) => r.status === "closed").length,
    overdue_followups: open.filter((r) => r.flags.includes("overdue")).length,
    due_soon_followups: open.filter((r) => r.flags.includes("due_soon")).length,
    due_today_followups: open.filter((r) => r.days_until_due === 0).length,
    unassigned_followups: open.filter((r) => !r.due_date).length,
    next_due_date:
      open
        .map((r) => r.due_date)
        .filter((d): d is string => d !== null)
        .sort()[0] ?? null,
  };
}
function samplePage<T>(items: T[], asOf: string, params: Params) {
  const offset = Number(params.offset || 0),
    limit = Number(params.limit || 50);
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    offset,
    limit,
    as_of_date: asOf,
  };
}
export async function sampleRequest<T>(
  path: string,
  { method = "GET", params = {}, body }: RequestOptions = {},
): Promise<T> {
  const asof = String(params.as_of_date || localDate());
  const rows = records.map((r) => {
    const days = r.due_date
      ? Math.round((Date.parse(r.due_date) - Date.parse(asof)) / 86400000)
      : null;
    const flags: Attention[] =
      r.status !== "open"
        ? []
        : [
            ...(days === null
              ? ["unassigned" as const]
              : days < 0
                ? ["overdue" as const]
                : days <= (r.action_type === "lab" ? 3 : 14)
                  ? ["due_soon" as const]
                  : []),
          ];
    return { ...r, flags, days_until_due: days };
  });
  const [resource, id] = path.split("/");
  const one = (value: unknown) => [value].flat().map(String);
  const result = (() => {
    if (method === "PATCH" && resource === "followups" && id) {
      const item = records.find((r) => r.followup_id === id);
      const change = body as { status?: string };
      if (!item) throw new ApiError("Sample record not found.", 404);
      if (
        Object.keys(change).some((k) => k !== "status") ||
        !["open", "done"].includes(change.status ?? "")
      )
        throw new ApiError(
          "Switch to your connected workspace to edit records.",
          422,
        );
      item.status = change.status as "open" | "done";
      item.completed_at =
        item.status === "done" ? new Date().toISOString() : null;
      return { ...item };
    }
    if (method !== "GET")
      throw new ApiError(
        resource === "ask"
          ? "AI search requires a connected workspace and a configured model API key."
          : "Switch to your connected workspace to create records. Sample completion actions are available here.",
        503,
        "preview_only",
      );
    if (resource === "events")
      return events.filter(
        (e) =>
          e.event_date >= String(params.date_from) &&
          e.event_date <= String(params.date_to),
      );
    if (resource === "options")
      return {
        staff,
        action_types: ["lab", "referral", "recheck"],
        followup_statuses: ["open", "done", "closed"],
        due_soon_days_by_action: { lab: 3, referral: 14, recheck: 14 },
      };
    if (resource === "dashboard")
      return {
        as_of_date: asof,
        followups: sampleCounts(rows),
        completed_last_7_days: rows.filter((r) => r.status === "done").length,
        patients: names.length,
        patients_with_overdue: rows.filter((r) => r.flags.includes("overdue"))
          .length,
        open_episodes: names.length,
        visits_last_30_days: rows.filter((r) => r.visit_date >= relative(-30))
          .length,
      };
    if (resource === "followups" && id && id !== "stats") {
      const f = rows.find((r) => r.followup_id === id);
      if (!f) throw new ApiError("Sample record not found.", 404);
      return {
        followup: f,
        history: [],
        patient: {
          name: f.patient_name,
          phone: "555-0100",
          email:
            f.patient_name.toLowerCase().replace(" ", ".") + "@example.test",
        },
        episode_followups: rows.filter(
          (r) =>
            r.episode_id === f.episode_id && r.followup_id !== f.followup_id,
        ),
      };
    }
    if (resource === "followups") {
      let filtered = rows.filter((r) => {
        if (
          params.q &&
          !Object.values(r)
            .join(" ")
            .toLowerCase()
            .includes(String(params.q).toLowerCase())
        )
          return false;
        if (params.action_type && r.action_type !== params.action_type)
          return false;
        if (params.status && !one(params.status).includes(r.status))
          return false;
        if (params.due_from && (!r.due_date || r.due_date < String(params.due_from)))
          return false;
        if (params.due_to && (!r.due_date || r.due_date > String(params.due_to)))
          return false;
        const completed = r.completed_at?.slice(0, 10) ?? "";
        if (params.completed_from && completed < String(params.completed_from))
          return false;
        if (params.completed_to && (!completed || completed > String(params.completed_to)))
          return false;
        if (
          params.preset === "overdue_7_plus" &&
          !(r.flags.includes("overdue") && (r.days_until_due ?? 0) <= -7)
        )
          return false;
        if (
          params.preset === "due_this_week" &&
          !(
            r.status === "open" &&
            r.days_until_due !== null &&
            r.days_until_due >= 0 &&
            r.days_until_due <= 7
          )
        )
          return false;
        if (
          params.preset === "due_today" &&
          !(r.status === "open" && r.days_until_due === 0)
        )
          return false;
        if (
          params.preset === "completed_today" &&
          !(r.status === "done" && completed === asof)
        )
          return false;
        if (
          params.assigned_staff_id &&
          r.assigned_staff_id !== params.assigned_staff_id
        )
          return false;
        if (params.patient_id && r.patient_id !== params.patient_id)
          return false;
        if (params.preset === "overdue" && !r.flags.includes("overdue"))
          return false;
        if (params.preset === "due_soon" && !r.flags.includes("due_soon"))
          return false;
        if (params.preset === "unassigned" && !r.flags.includes("unassigned"))
          return false;
        if (
          params.flag &&
          !(
            Array.isArray(params.flag) ? params.flag : [String(params.flag)]
          ).some((flag) => r.flags.includes(flag as Attention))
        )
          return false;
        return true;
      });
      if (id === "stats") {
        const field =
          params.group_by === "assigned_staff"
            ? "assigned_staff_id"
            : "action_type";
        return {
          totals: sampleCounts(filtered),
          groups: [...new Set(filtered.map((r) => r[field]))].map((key) => ({
            key,
            label:
              field === "assigned_staff_id"
                ? staff.find((s) => s.staff_id === key)?.name || "Unassigned"
                : key,
            ...sampleCounts(filtered.filter((r) => r[field] === key)),
          })),
        };
      }
      const sort = String(params.sort || "status");
      filtered = filtered.sort((a, b) =>
        sort === "status"
          ? b.status.localeCompare(a.status) ||
            (a.due_date || "").localeCompare(b.due_date || "")
          : String(
              a[sort.replace(/^-/, "") as keyof Followup] ?? "",
            ).localeCompare(
              String(b[sort.replace(/^-/, "") as keyof Followup] ?? ""),
            ) * (sort.startsWith("-") ? -1 : 1),
      );
      const offset = Number(params.offset || 0),
        limit = Number(params.limit || 50);
      return {
        items: filtered.slice(offset, offset + limit),
        total: filtered.length,
        offset,
        limit,
        as_of_date: asof,
      };
    }
    if (resource === "staff") {
      const items = staff.map((s) => ({
        ...s,
        ...sampleCounts(rows.filter((r) => r.assigned_staff_id === s.staff_id)),
        visit_count: rows.filter((r) => r.visit_staff_id === s.staff_id).length,
        patient_count: rows.filter((r) => r.visit_staff_id === s.staff_id)
          .length,
        last_visit_date:
          rows
            .filter((r) => r.visit_staff_id === s.staff_id)
            .map((r) => r.visit_date)
            .sort()
            .at(-1) ?? null,
      }));
      if (id) {
        const item = items.find((s) => s.staff_id === id);
        if (!item) throw new ApiError("Staff member not found.", 404);
        return {
          staff: item,
          open_followups: rows.filter(
            (r) => r.assigned_staff_id === id && r.status === "open",
          ),
          recent_visits: rows.filter((r) => r.visit_staff_id === id),
        };
      }
      const filtered = items.filter(
        (r) =>
          !params.q ||
          Object.values(r)
            .join(" ")
            .toLowerCase()
            .includes(String(params.q).toLowerCase()),
      );
      return samplePage(filtered, asof, params);
    }
    if (resource === "patients") {
      const patients = rows.map((r) => ({
        patient_id: r.patient_id,
        name: r.patient_name,
        phone: "555-0100",
        email: r.patient_name.toLowerCase().replace(" ", ".") + "@example.test",
        visit_count: 1,
        last_visit_date: r.visit_date,
        ...sampleCounts([r]),
      }));
      if (id) {
        const r = rows.find((r) => r.patient_id === id);
        if (!r) throw new ApiError("Patient not found.", 404);
        return {
          patient: patients.find((p) => p.patient_id === id),
          episodes: [
            {
              episode_id: r.episode_id,
              description: r.episode_description,
              status: "open",
              opened_at: r.visit_date,
              visits: [
                {
                  visit_id: r.visit_id,
                  visit_date: r.visit_date,
                  staff_name: r.visit_staff_name,
                  notes: r.visit_notes,
                  followups: [r],
                },
              ],
            },
          ],
        };
      }
      const filtered = patients.filter(
        (p, i) =>
          (!params.q ||
            Object.values(p)
              .join(" ")
              .toLowerCase()
              .includes(String(params.q).toLowerCase())) &&
          (!params.flag ||
            one(params.flag).some((f) => rows[i].flags.includes(f as Attention))),
      );
      return samplePage(filtered, asof, params);
    }
    if (resource === "visits" || resource === "episodes") {
      const items = rows.map((r) =>
        resource === "visits"
          ? {
              visit_id: r.visit_id,
              visit_date: r.visit_date,
              patient_name: r.patient_name,
              staff_name: r.visit_staff_name,
              notes: r.visit_notes,
              ...sampleCounts([r]),
            }
          : {
              episode_id: r.episode_id,
              patient_name: r.patient_name,
              description: r.episode_description,
              status: "open",
              opened_at: r.visit_date,
              ...sampleCounts([r]),
            },
      );
      const filtered = items.filter(
        (r) =>
          !params.q ||
          Object.values(r)
            .join(" ")
            .toLowerCase()
            .includes(String(params.q).toLowerCase()),
      );
      if (id) {
        const key = resource === "visits" ? "visit_id" : "episode_id";
        const record = items.find(
          (item) => String((item as Record<string, unknown>)[key]) === id,
        );
        if (!record) throw new ApiError("Record not found.", 404);
        const source = rows.find(
          (r) => (resource === "visits" ? r.visit_id : r.episode_id) === id,
        )!;
        return resource === "visits"
          ? {
              visit: {
                ...record,
                patient_id: source.patient_id,
                episode_id: source.episode_id,
                staff_id: source.visit_staff_id,
                followups: [source],
              },
            }
          : {
              episode: {
                ...record,
                patient_id: source.patient_id,
                visits: [
                  {
                    visit_id: source.visit_id,
                    visit_date: source.visit_date,
                    staff_name: source.visit_staff_name,
                    notes: source.visit_notes,
                    followups: [source],
                  },
                ],
              },
            };
      }
      return samplePage(filtered, asof, params);
    }
    throw new ApiError(
      "This view is available in the connected workspace.",
      404,
    );
  })();
  return result as T;
}
