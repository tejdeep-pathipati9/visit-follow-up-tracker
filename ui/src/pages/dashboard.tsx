// Layout and visual primitives adapted from Efferd dashboard-5 (see THIRD_PARTY_NOTICES.md).
import { useId, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts";
import {
  ArrowRight,
  CalendarDays,
  Check,
  Circle,
  UserRound,
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  ShareBarList,
  ShareBarListItem,
  ShareBarListContent,
  ShareBarListLabel,
  ShareBarListValue,
  ShareBarListFill,
} from "@/components/share-bar-list";
import { AttentionBadge } from "@/components/followup-badges";
import { FollowupDetailPanel } from "@/components/followup-detail";
import {
  WorkspaceError,
  WorkspaceLoading,
  EmptyState,
} from "@/components/workspace-state";
import { useApi, useWorkspace } from "@/lib/workspace";
import { navigate } from "@/lib/router";
import { formatDate, titleCase } from "@/lib/types";
import type { Followup, Page, Summary, Stats } from "@/lib/types";

const chartConfig = {
  open: { label: "Open", color: "var(--chart-2)" },
  done: { label: "Completed", color: "var(--chart-4)" },
} satisfies ChartConfig;
function Breakdown({
  title,
  description,
  rows,
}: {
  title: string;
  description: string;
  rows: { label: string; value: number }[];
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <Card className="dark:bg-transparent">
      <CardHeader className="border-b">
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="p-0 py-1">
        <ShareBarList>
          {rows.map((row) => (
            <ShareBarListItem key={row.label} value={(row.value / max) * 75}>
              <ShareBarListContent>
                <ShareBarListLabel>{row.label}</ShareBarListLabel>
                <ShareBarListValue>
                  {row.value.toLocaleString()}
                </ShareBarListValue>
              </ShareBarListContent>
              <ShareBarListFill />
            </ShareBarListItem>
          ))}
        </ShareBarList>
      </CardContent>
    </Card>
  );
}
export function DashboardPage() {
  const { asOf } = useWorkspace();
  const id = useId().replaceAll(":", "");
  const [selected, setSelected] = useState<string | null>(null);
  const summary = useApi<Summary>("dashboard");
  const all = useApi<Page<Followup>>("followups", {
    limit: 1000,
    sort: "due_date",
  });
  const priority = useApi<Page<Followup>>("followups", {
    preset: "overdue",
    limit: 5,
    sort: "due_date",
  });
  const recent = useApi<Page<Followup>>("followups", {
    status: "done",
    limit: 5,
    sort: "-completed_at",
  });
  const owners = useApi<Stats>("followups/stats", {
    group_by: "assigned_staff",
  });
  const types = useApi<Stats>("followups/stats", { group_by: "action_type" });
  const chartData = useMemo(() => {
    const buckets = new Map<
      string,
      { date: string; open: number; done: number }
    >();
    for (let offset = -23; offset <= 7; offset++) {
      const d = new Date(asOf + "T12:00:00");
      d.setDate(d.getDate() + offset);
      const date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
      buckets.set(date, { date, open: 0, done: 0 });
    }
    all.data?.items.forEach((row) => {
      const bucket = buckets.get(row.due_date || "");
      if (bucket && row.status !== "closed") bucket[row.status]++;
    });
    return [...buckets.values()];
  }, [all.data, asOf]);
  const failure =
    summary.error ||
    all.error ||
    priority.error ||
    owners.error ||
    types.error ||
    recent.error;
  if (failure)
    return (
      <WorkspaceError
        error={failure}
        retry={() => {
          void Promise.all([
            summary.refetch(),
            all.refetch(),
            priority.refetch(),
            recent.refetch(),
            owners.refetch(),
            types.refetch(),
          ]);
        }}
      />
    );
  if (
    !summary.data ||
    !all.data ||
    !priority.data ||
    !recent.data ||
    !owners.data ||
    !types.data
  )
    return <WorkspaceLoading />;
  const d = summary.data;
  const counts = d.followups;
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Clinic overview
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            The next steps that keep care connected.
          </p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate("followups")}
        >
          <CalendarDays />
          View follow-ups
          <ArrowRight />
        </Button>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card className="md:col-span-2 lg:col-span-3 dark:bg-transparent">
          <CardHeader className="flex flex-row items-start justify-between">
            <div className="flex flex-col gap-1.5">
              <CardTitle className="font-mono text-2xl tabular-nums">
                {counts.followup_count.toLocaleString()}
              </CardTitle>
              <CardDescription>
                Follow-ups across your clinic workspace.
              </CardDescription>
            </div>
            <Badge variant="outline" className="gap-1.5 font-normal">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {d.completed_last_7_days} completed this week
            </Badge>
          </CardHeader>
          <CardContent>
            <ChartContainer
              config={chartConfig}
              className="aspect-auto h-60 w-full"
            >
              <AreaChart
                accessibilityLayer
                data={chartData}
                margin={{ left: 12, right: 12 }}
              >
                <defs>
                  <linearGradient
                    id={`schedule-${id}`}
                    x1="0"
                    y1="0"
                    x2="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor="var(--color-open)"
                      stopOpacity={0.35}
                    />
                    <stop
                      offset="100%"
                      stopColor="var(--color-open)"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid vertical={false} />
                <XAxis
                  dataKey="date"
                  axisLine={false}
                  tickLine={false}
                  minTickGap={25}
                  tickMargin={8}
                  tickFormatter={(value) =>
                    new Date(value + "T12:00:00").toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })
                  }
                />
                <ChartTooltip
                  content={<ChartTooltipContent indicator="dashed" />}
                  cursor={{
                    stroke: "var(--color-open)",
                    strokeDasharray: "3 3",
                  }}
                />
                <Area
                  type="linear"
                  dataKey="open"
                  name="Open"
                  stroke="var(--color-open)"
                  strokeWidth={2}
                  fill={`url(#schedule-${id})`}
                  dot={false}
                  isAnimationActive={false}
                />
                <Area
                  type="linear"
                  dataKey="done"
                  name="Completed"
                  stroke="var(--color-done)"
                  strokeWidth={1.5}
                  fill="transparent"
                  strokeDasharray="3 3"
                  isAnimationActive={false}
                />
              </AreaChart>
            </ChartContainer>
            <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
              <span>Scheduled by due date · through the next 7 days</span>
              <span>
                {all.data.total > 1000
                  ? "Timeline includes the first 1,000 records."
                  : "Open and completed follow-ups"}
              </span>
            </div>
          </CardContent>
        </Card>
        <Card className="gap-0 pb-0 md:col-span-2 lg:col-span-1 dark:bg-transparent">
          <CardHeader className="flex flex-row items-start justify-between gap-3 border-b">
            <div className="flex flex-col gap-1.5">
              <CardTitle className="font-mono text-2xl tabular-nums">
                {counts.open_followups}
              </CardTitle>
              <CardDescription className="flex items-center gap-1.5">
                <span className="size-1.5 rounded-full bg-emerald-500" />
                open follow-ups
              </CardDescription>
            </div>
            <Badge variant="outline" className="font-normal">
              As of{" "}
              {new Date(asOf + "T12:00:00").toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </Badge>
          </CardHeader>
          <CardContent className="relative flex h-full items-center px-0 py-2">
            <ShareBarList aria-label="Open follow-ups by type">
              {types.data.groups.map((group) => (
                <ShareBarListItem
                  key={group.key}
                  value={
                    (group.open_followups /
                      Math.max(1, counts.open_followups)) *
                    100
                  }
                >
                  <ShareBarListContent>
                    <ShareBarListLabel>
                      {titleCase(group.label || "Other")}
                    </ShareBarListLabel>
                    <ShareBarListValue>
                      {group.open_followups}
                    </ShareBarListValue>
                  </ShareBarListContent>
                  <ShareBarListFill />
                </ShareBarListItem>
              ))}
            </ShareBarList>
          </CardContent>
        </Card>
        <Card className="relative md:col-span-2 dark:bg-transparent">
          <CardHeader className="flex-row items-start justify-between">
            <div className="space-y-1.5">
              <CardTitle>Priority follow-ups</CardTitle>
              <CardDescription>
                Overdue next steps, earliest due first.
              </CardDescription>
            </div>
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="View all overdue follow-ups"
              onClick={() => navigate("followups", { preset: "overdue" })}
            >
              <ArrowRight />
            </Button>
          </CardHeader>
          <CardContent className="p-0 pb-2">
            <Table className="border-t">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Patient</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="pr-6 text-right">Due date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {priority.data.items.map((row) => (
                  <TableRow
                    key={row.followup_id}
                    className="cursor-pointer"
                    onClick={() => setSelected(row.followup_id)}
                  >
                    <TableCell className="pl-6">
                      <button
                        className="text-left font-medium underline-offset-4 hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelected(row.followup_id);
                        }}
                      >
                        {row.patient_name}
                      </button>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {row.followup_id}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="rounded border border-border bg-muted/50 px-1 py-px text-xs">
                        {titleCase(row.action_type)}
                      </span>
                    </TableCell>
                    <TableCell className="pr-6 text-right text-xs text-muted-foreground">
                      {formatDate(row.due_date)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            {!priority.data.total && (
              <EmptyState
                title="Nothing overdue"
                description="Your clinic has no overdue follow-ups as of this date."
              />
            )}
          </CardContent>
        </Card>
        <Card className="relative md:col-span-2 dark:bg-transparent">
          <CardHeader>
            <CardTitle>Staff workload</CardTitle>
            <CardDescription>
              Open next steps and where attention is needed.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 pb-2">
            <Table className="border-t">
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">Assigned staff</TableHead>
                  <TableHead className="text-right">Open</TableHead>
                  <TableHead className="pr-6 text-right">Overdue</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...owners.data.groups]
                  .sort((a, b) => b.open_followups - a.open_followups)
                  .slice(0, 5)
                  .map((group) => (
                    <TableRow key={group.key ?? "unassigned"}>
                      <TableCell className="pl-6">
                        <Button
                          variant="link"
                          className="h-auto justify-start p-0 text-xs font-normal"
                          onClick={() =>
                            navigate(
                              "followups",
                              group.key
                                ? { assigned_staff_id: group.key }
                                : { preset: "unassigned" },
                            )
                          }
                        >
                          <UserRound className="size-3.5 text-muted-foreground" />
                          {group.label || "Unassigned"}
                        </Button>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">
                        {group.open_followups}
                      </TableCell>
                      <TableCell className="pr-6 text-right">
                        <Badge
                          variant="outline"
                          className="font-mono font-normal"
                        >
                          {group.overdue_followups}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
            {!owners.data.groups.length && (
              <EmptyState
                title="No assigned workload yet"
                description="Follow-ups will appear here when records are added."
              />
            )}
          </CardContent>
        </Card>
        <Breakdown
          title="Follow-up types"
          description="All records by requested next step."
          rows={types.data.groups.map((g) => ({
            label: titleCase(g.label || "Other"),
            value: g.followup_count,
          }))}
        />
        <Breakdown
          title="Needs attention"
          description="Open records. Attention flags may overlap."
          rows={[
            { label: "Overdue", value: counts.overdue_followups },
            { label: "Due soon", value: counts.due_soon_followups },
            { label: "Unassigned", value: counts.unassigned_followups },
          ]}
        />
        <Breakdown
          title="Completion"
          description="Current status across the workspace."
          rows={[
            { label: "Open", value: counts.open_followups },
            { label: "Completed", value: counts.done_followups },
          ]}
        />
        <Card className="dark:bg-transparent">
          <CardHeader>
            <CardTitle>Recently completed</CardTitle>
            <CardDescription>The latest next steps resolved.</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <div className="divide-y border-t">
              {recent.data.items.map((row) => (
                <button
                  key={row.followup_id}
                  className="flex w-full items-center justify-between gap-2 px-6 py-3 text-left text-xs hover:bg-muted/50"
                  onClick={() => setSelected(row.followup_id)}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Check className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{row.patient_name}</span>
                  </span>
                  <span className="shrink-0 text-muted-foreground">
                    {new Date(
                      (row.completed_at || row.due_date || "").slice(0, 10) +
                        "T12:00:00",
                    ).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                </button>
              ))}
            </div>
            {!recent.data.total && (
              <p className="px-6 py-8 text-center text-sm text-muted-foreground">
                No completed follow-ups yet.
              </p>
            )}
          </CardContent>
        </Card>
        <Card className="md:col-span-2 lg:col-span-4 dark:bg-transparent">
          <CardHeader>
            <CardTitle>Today’s follow-through</CardTitle>
            <CardDescription>
              Operational priorities for {formatDate(asOf)}.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-6 sm:grid-cols-3">
            <button
              className="flex items-center justify-between rounded-md border px-4 py-3 text-left hover:bg-muted/50"
              onClick={() => navigate("followups", { preset: "overdue" })}
            >
              <div>
                <span className="text-xs text-muted-foreground">Past due</span>
                <p className="mt-1 font-mono text-xl">
                  {counts.overdue_followups}
                </p>
              </div>
              <AttentionBadge flag="overdue" />
            </button>
            <button
              className="flex items-center justify-between rounded-md border px-4 py-3 text-left hover:bg-muted/50"
              onClick={() => navigate("followups", { preset: "due_soon" })}
            >
              <div>
                <span className="text-xs text-muted-foreground">Due soon</span>
                <p className="mt-1 font-mono text-xl">
                  {counts.due_soon_followups}
                </p>
              </div>
              <AttentionBadge flag="due_soon" />
            </button>
            <button
              className="flex items-center justify-between rounded-md border px-4 py-3 text-left hover:bg-muted/50"
              onClick={() => navigate("followups", { preset: "unassigned" })}
            >
              <div>
                <span className="text-xs text-muted-foreground">
                  Needs scheduling
                </span>
                <p className="mt-1 font-mono text-xl">
                  {counts.unassigned_followups}
                </p>
              </div>
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <Circle className="size-3" />
                Unassigned
              </span>
            </button>
          </CardContent>
        </Card>
      </div>
      <FollowupDetailPanel id={selected} onClose={() => setSelected(null)} />
    </>
  );
}
