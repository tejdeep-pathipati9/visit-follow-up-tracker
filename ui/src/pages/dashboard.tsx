// Home screen for follow-up and patient management: what needs action today, where work
// is piling up, what is coming this week, and how the last 30 days went. One chart only,
// the mix of open follow-ups; the rest are counts that open the matching list.
import type { ReactNode } from "react";
import { Cell, Pie, PieChart } from "recharts";
import {
  ArrowRight,
  CalendarRange,
  ChevronRight,
  Printer,
} from "lucide-react";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { AttentionBadge } from "@/components/followup-badges";
import {
  WorkspaceError,
  WorkspaceLoading,
} from "@/components/workspace-state";
import { useRecordPermissions } from "@/lib/session";
import { useApi, useWorkspace } from "@/lib/workspace";
import { navigate } from "@/lib/router";
import { addDays, formatDate, titleCase } from "@/lib/types";
import type {
  CalendarEvent,
  Followup,
  Page,
  Stats,
  Summary,
} from "@/lib/types";

const mixConfig = {
  overdue: { label: "Overdue", color: "#e11d48" },
  due_soon: { label: "Due soon", color: "#d97706" },
  unassigned: { label: "No date", color: "#94a3b8" },
  on_track: { label: "On track", color: "#10b981" },
} satisfies ChartConfig;

function Metric({
  label,
  value,
  note,
  onClick,
}: {
  label: string;
  value: ReactNode;
  note: string;
  onClick?: () => void;
}) {
  const body = (
    <>
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="mt-2 block font-mono text-3xl tabular-nums">{value}</span>
      <span className="mt-1 block text-xs text-muted-foreground">{note}</span>
    </>
  );
  return onClick ? (
    <button
      type="button"
      onClick={onClick}
      className="rounded-md px-4 py-3 text-left transition-colors hover:bg-muted/50"
    >
      {body}
    </button>
  ) : (
    <div className="px-4 py-3">{body}</div>
  );
}

function ActionRow({
  label,
  detail,
  count,
  tone,
  onClick,
}: {
  label: string;
  detail: string;
  count: number;
  tone: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 border-t px-6 py-4 text-left transition-colors hover:bg-muted/40"
    >
      <span className={`size-2.5 shrink-0 rounded-full ${tone}`} />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium">{label}</span>
        <span className="text-xs text-muted-foreground">{detail}</span>
      </span>
      <span className="font-mono text-lg tabular-nums">{count}</span>
      <ChevronRight className="size-4 text-muted-foreground" />
    </button>
  );
}

export function DashboardPage() {
  const { asOf, setAsOf, sample } = useWorkspace();
  // Managers see the whole clinic; other staff see their own follow-ups only.
  const { manage } = useRecordPermissions();
  const summary = useApi<Summary>("dashboard");
  const overdueWeek = useApi<Page<Followup>>("followups", {
    preset: "overdue_7_plus",
    limit: 1,
  });
  const doneToday = useApi<Page<Followup>>("followups", {
    preset: "completed_today",
    limit: 1,
  });
  const owners = useApi<Stats>("followups/stats", {
    group_by: "assigned_staff",
  });
  const types = useApi<Stats>("followups/stats", { group_by: "action_type" });
  // "Coming up" uses one range for follow-ups and events: today and the next six days.
  const weekEnd = addDays(asOf, 6);
  const dueThisWeek = useApi<Page<Followup>>("followups", {
    status: "open",
    due_from: asOf,
    due_to: weekEnd,
    limit: 8,
    sort: "due_date",
  });
  const events = useApi<CalendarEvent[]>("events", {
    date_from: asOf,
    date_to: weekEnd,
  });
  const queries = [summary, overdueWeek, doneToday, owners, types, dueThisWeek, events];
  const failure = queries.find((q) => q.error)?.error;
  if (failure)
    return (
      <WorkspaceError
        error={failure}
        retry={() => void Promise.all(queries.map((q) => q.refetch()))}
      />
    );
  if (
    !summary.data ||
    !overdueWeek.data ||
    !doneToday.data ||
    !owners.data ||
    !types.data ||
    !dueThisWeek.data ||
    !events.data
  )
    return <WorkspaceLoading />;

  const d = summary.data;
  const counts = d.followups;
  const onTrack = Math.max(
    0,
    counts.open_followups -
      counts.overdue_followups -
      counts.due_soon_followups -
      counts.unassigned_followups,
  );
  const mix = [
    { key: "overdue", value: counts.overdue_followups },
    { key: "due_soon", value: counts.due_soon_followups },
    { key: "unassigned", value: counts.unassigned_followups },
    { key: "on_track", value: onTrack },
  ] as const;
  const mostOverdue = (stats: Stats) =>
    [...stats.groups].sort((a, b) => b.overdue_followups - a.overdue_followups)[0];
  const staffBehind = mostOverdue(owners.data);
  const typeBehind = mostOverdue(types.data);
  const staffWithOverdue = owners.data.groups.filter((g) => g.overdue_followups > 0).length;
  const coming = [
    ...events.data.map((e) => ({ date: e.event_date, key: e.event_id, event: e })),
    ...dueThisWeek.data.items.flatMap((f) =>
      f.due_date ? [{ date: f.due_date, key: f.followup_id, followup: f }] : [],
    ),
  ]
    .sort((a, b) => a.date.localeCompare(b.date))
    .slice(0, 8);
  const comingTotal = events.data.length + dueThisWeek.data.total;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Follow-up operations
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {manage
              ? `What needs attention across the clinic as of ${formatDate(asOf)}.`
              : `Your follow-ups and what needs attention as of ${formatDate(asOf)}.`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            As of
            <Input
              type="date"
              aria-label="As of date"
              className="h-8 w-36"
              value={asOf}
              onChange={(e) => e.target.value && setAsOf(e.target.value)}
            />
          </label>
          <Button size="sm" variant="outline" onClick={() => navigate("calendar")}>
            <CalendarRange />
            Calendar
          </Button>
          {sample ? (
            <Button size="sm" variant="outline" onClick={() => window.print()}>
              <Printer />
              Report
            </Button>
          ) : (
            <Button asChild size="sm" variant="outline">
              <a
                href={`/report?as_of_date=${encodeURIComponent(asOf)}`}
                target="_blank"
                rel="noreferrer"
              >
                <Printer />
                Report
              </a>
            </Button>
          )}
        </div>
      </div>

      <Card className="mb-4 gap-0 py-2 dark:bg-transparent">
        <div className="grid grid-cols-2 lg:grid-cols-4">
          <Metric
            label="Due today"
            value={counts.due_today_followups}
            note="Needs action"
            onClick={() => navigate("followups", { preset: "due_today" })}
          />
          <Metric
            label="Overdue"
            value={counts.overdue_followups}
            note="Past the scheduled date"
            onClick={() => navigate("followups", { preset: "overdue" })}
          />
          <Metric
            label="Done today"
            value={doneToday.data.total}
            note="Completed today"
            onClick={() => navigate("followups", { preset: "completed_today" })}
          />
          <Metric
            label="Open follow-ups"
            value={counts.open_followups}
            note={`For ${d.patients_with_open_followups ?? d.patients} patients`}
            onClick={() => navigate("followups", { status: "open" })}
          />
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="gap-0 pb-0 lg:col-span-2 dark:bg-transparent">
          <CardHeader className="pb-4">
            <CardTitle>Action center</CardTitle>
            <CardDescription>
              Follow-ups and patients that need a decision.
            </CardDescription>
            <CardAction>
              <Button size="sm" variant="ghost" onClick={() => navigate("followups")}>
                View all
                <ArrowRight />
              </Button>
            </CardAction>
          </CardHeader>
          <ActionRow
            label="Overdue 7+ days"
            detail="Open a week or more past the scheduled date"
            count={overdueWeek.data.total}
            tone="bg-rose-600"
            onClick={() => navigate("followups", { preset: "overdue_7_plus" })}
          />
          <ActionRow
            label="Due soon"
            detail="Inside the clinic’s window: lab 3 days, referral and recheck 14"
            count={counts.due_soon_followups}
            tone="bg-amber-500"
            onClick={() => navigate("followups", { preset: "due_soon" })}
          />
          <ActionRow
            label="No scheduled date"
            detail="Open the calendar to give them a date"
            count={counts.unassigned_followups}
            tone="bg-slate-400"
            onClick={() => navigate("calendar")}
          />
          <ActionRow
            label="Patients with overdue follow-ups"
            detail="Patients to contact"
            count={d.patients_with_overdue}
            tone="bg-sky-600"
            onClick={() => navigate("patients", { flag: "overdue" })}
          />
        </Card>

        <Card className="gap-4 dark:bg-transparent">
          <CardHeader>
            <CardTitle>{manage ? "Team and workload" : "My workload"}</CardTitle>
            <CardDescription>
              {manage
                ? "Where open work is piling up."
                : "Your open follow-ups by what they need."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <ChartContainer
                config={mixConfig}
                className="aspect-square h-32 shrink-0"
              >
                <PieChart>
                  <ChartTooltip
                    content={<ChartTooltipContent nameKey="key" hideLabel />}
                  />
                  <Pie
                    data={mix.filter((m) => m.value > 0)}
                    dataKey="value"
                    nameKey="key"
                    innerRadius={38}
                    outerRadius={60}
                    strokeWidth={2}
                    isAnimationActive={false}
                  >
                    {mix
                      .filter((m) => m.value > 0)
                      .map((m) => (
                        <Cell key={m.key} fill={mixConfig[m.key].color} />
                      ))}
                  </Pie>
                </PieChart>
              </ChartContainer>
              <ul className="space-y-1.5 text-xs" aria-label="Open follow-ups">
                {mix.map((m) => (
                  <li key={m.key} className="flex items-center gap-2">
                    <span
                      className="size-2.5 rounded-sm"
                      style={{ background: mixConfig[m.key].color }}
                    />
                    <span className="text-muted-foreground">
                      {mixConfig[m.key].label}
                    </span>
                    <span className="ml-auto font-mono tabular-nums">{m.value}</span>
                  </li>
                ))}
              </ul>
            </div>
            <dl className="divide-y border-y text-sm">
              {manage && (
                <div className="flex justify-between gap-3 py-2.5">
                  <dt className="text-muted-foreground">Most overdue</dt>
                  <dd className="text-right">
                    {staffBehind?.overdue_followups
                      ? `${staffBehind.label} · ${staffBehind.overdue_followups}`
                      : "—"}
                  </dd>
                </div>
              )}
              <div className="flex justify-between gap-3 py-2.5">
                <dt className="text-muted-foreground">Slowest follow-up type</dt>
                <dd className="text-right">
                  {typeBehind?.overdue_followups
                    ? `${titleCase(typeBehind.label || "")} · ${typeBehind.overdue_followups} overdue`
                    : "—"}
                </dd>
              </div>
              {manage && (
                <div className="flex justify-between gap-3 py-2.5">
                  <dt className="text-muted-foreground">Staff with overdue work</dt>
                  <dd className="font-mono tabular-nums">
                    {staffWithOverdue} of {owners.data.groups.length}
                  </dd>
                </div>
              )}
            </dl>
            <Button
              size="sm"
              variant="ghost"
              className="w-full justify-between"
              onClick={() => navigate("reports")}
            >
              {manage ? "View team workload" : "View my workload"}
              <ArrowRight />
            </Button>
          </CardContent>
        </Card>

        <Card className="gap-0 pb-0 lg:col-span-2 dark:bg-transparent">
          <CardHeader className="pb-4">
            <CardTitle>Coming up this week</CardTitle>
            <CardDescription>
              Important dates and follow-ups due in the next 7 days.
            </CardDescription>
            <CardAction>
              <Button size="sm" variant="ghost" onClick={() => navigate("calendar")}>
                Open calendar
                <ArrowRight />
              </Button>
            </CardAction>
          </CardHeader>
          {coming.map((item) => (
            <div
              key={item.key}
              className="flex items-center gap-4 border-t px-6 py-3 text-sm"
            >
              <span className="w-24 shrink-0 text-xs text-muted-foreground">
                {formatDate(item.date)}
              </span>
              {"event" in item && item.event ? (
                <>
                  <span className="min-w-0 flex-1 truncate">
                    <span className="font-medium">{item.event.title}</span>
                    <span className="text-muted-foreground">
                      {" "}
                      · {item.event.start_time ?? "All day"} ·{" "}
                      {item.event.staff_name ?? "Whole clinic"}
                    </span>
                  </span>
                  <span className="rounded border border-sky-200 bg-sky-50 px-1.5 py-px text-xs text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300">
                    Important date
                  </span>
                </>
              ) : (
                "followup" in item &&
                item.followup && (
                  <>
                    <span className="min-w-0 flex-1 truncate">
                      <span className="font-medium">{item.followup.patient_name}</span>
                      <span className="text-muted-foreground">
                        {" "}
                        · {titleCase(item.followup.action_type)} ·{" "}
                        {item.followup.assigned_staff_name}
                      </span>
                    </span>
                    {item.followup.flags[0] && (
                      <AttentionBadge flag={item.followup.flags[0]} />
                    )}
                  </>
                )
              )}
            </div>
          ))}
          {!coming.length && (
            <p className="border-t px-6 py-8 text-center text-sm text-muted-foreground">
              Nothing scheduled in the next 7 days.
            </p>
          )}
          {comingTotal > coming.length && (
            <p className="border-t px-6 py-3 text-xs text-muted-foreground">
              Showing {coming.length} of {comingTotal}; the calendar has the rest.
            </p>
          )}
        </Card>

        <Card className="gap-4 dark:bg-transparent">
          <CardHeader>
            <CardTitle>Last 30 days</CardTitle>
            <CardDescription>How follow-ups were resolved.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <span className="text-sm text-muted-foreground">On-time completion</span>
              <span className="mt-1 block font-mono text-2xl tabular-nums">
                {d.done_with_date_last_30_days
                  ? `${Math.round((d.done_on_time_last_30_days / d.done_with_date_last_30_days) * 100)}%`
                  : "—"}
              </span>
              <span className="text-xs text-muted-foreground">
                Done on or before the scheduled date
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3 border-t pt-4">
              <div>
                <span className="text-sm text-muted-foreground">Done / closed</span>
                <span className="mt-1 block font-mono text-xl tabular-nums">
                  {d.done_last_30_days} / {d.closed_last_30_days}
                </span>
              </div>
              <div>
                <span className="text-sm text-muted-foreground">Patient visits</span>
                <span className="mt-1 block font-mono text-xl tabular-nums">
                  {d.visits_last_30_days}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
