export type FollowupStatus = "open" | "done" | "closed";
export type ActionType = "lab" | "referral" | "recheck";
export type Attention = "overdue" | "due_soon" | "unassigned";
export interface Staff {
  staff_id: string;
  name: string;
  role: string;
}
export interface Followup {
  followup_id: string;
  patient_id: string;
  patient_name: string;
  visit_id: string;
  episode_id: string;
  episode_description: string;
  visit_date: string;
  action_type: ActionType;
  due_date: string | null;
  status: FollowupStatus;
  flags: Attention[];
  assigned_staff_id: string;
  assigned_staff_name: string;
  assigned_staff_role: string;
  visit_staff_id: string;
  visit_staff_name: string;
  visit_staff_role: string;
  visit_notes: string | null;
  completed_at: string | null;
  episode_closed_at: string | null;
  days_until_due: number | null;
  notes: string | null;
}
export interface Counts {
  followup_count: number;
  open_followups: number;
  done_followups: number;
  closed_followups: number;
  overdue_followups: number;
  due_soon_followups: number;
  due_today_followups: number;
  unassigned_followups: number;
  next_due_date: string | null;
}
export interface Summary {
  as_of_date: string;
  followups: Counts;
  completed_last_7_days: number;
  patients: number;
  patients_with_open_followups?: number;
  patients_with_overdue: number;
  open_episodes: number;
  visits_last_30_days: number;
  staff_with_overdue?: number;
}
// An important date on the calendar; no staff member means the whole clinic.
export interface CalendarEvent {
  event_id: string;
  title: string;
  event_date: string;
  start_time: string | null;
  staff_id: string | null;
  staff_name: string | null;
  notes: string | null;
  created_by: string | null;
  created_by_name: string | null;
}
export interface Page<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
  as_of_date: string;
}
export interface Options {
  staff: Staff[];
  action_types: ActionType[];
  followup_statuses: FollowupStatus[];
  due_soon_days_by_action: Record<ActionType, number>;
}
export interface FollowupChange {
  change_id: number;
  field: "status" | "due_date" | "assigned_staff_id";
  old_value: string | null;
  new_value: string | null;
  changed_at: string;
  changed_by: string | null;
  changed_by_name: string | null;
  note: string | null;
}
export interface FollowupDetail {
  history: FollowupChange[];
  followup: Followup;
  patient: { name: string; phone: string | null; email: string | null };
  episode_followups: Followup[];
}
export interface Stats {
  totals: Counts;
  groups: (Counts & { key: string | null; label: string | null })[];
}
export type Params = Record<
  string,
  string | number | boolean | string[] | undefined
>;
export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  params?: Params;
  body?: unknown;
  signal?: AbortSignal;
}
export const titleCase = (s: string) =>
  s.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
export const isoDate = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const localDate = () => isoDate(new Date());
// Calendar arithmetic on YYYY-MM-DD strings, at local noon so DST never shifts the day.
export const addDays = (s: string, days: number) => {
  const d = new Date(`${s}T12:00:00`);
  d.setDate(d.getDate() + days);
  return isoDate(d);
};
export const formatDate = (s: string | null) =>
  s
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      }).format(new Date(`${s.slice(0, 10)}T12:00:00`))
    : "—";
export const initials = (s: string) =>
  s
    .replace(/^(Dr\.|Nurse)\s+/, "")
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((x) => x[0])
    .join("");
