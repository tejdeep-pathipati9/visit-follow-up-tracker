import { useEffect, useState } from "react";
import {
  ArrowDownWideNarrow,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  FlaskConical,
  Plus,
  Search,
  Undo2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { downloadCsv } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AttentionBadge, StatusBadge } from "@/components/followup-badges";
import { useRecordPermissions } from "@/lib/session";
import { FollowupDetailPanel } from "@/components/followup-detail";
import { RecordEditor } from "@/components/record-editor";
import { EmptyState, WorkspaceError } from "@/components/workspace-state";
import { useApi, useComplete, useWorkspace } from "@/lib/workspace";
import { useRoute } from "@/lib/router";
import { formatDate, initials, titleCase } from "@/lib/types";
import type { Followup, Options, Page, Params, Summary } from "@/lib/types";
const SIZE = 15;
function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <Select
      value={value || "all"}
      onValueChange={(v) => onChange(v === "all" ? "" : v)}
    >
      <SelectTrigger
        aria-label={label}
        size="sm"
        className="w-auto min-w-28 bg-background"
      >
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">{label}</SelectItem>
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
export function FollowupsPage() {
  const route = useRoute();
  const { canEditFollowup, manage } = useRecordPermissions();
  const { asOf, setAsOf, api, sample } = useWorkspace();
  const [search, setSearch] = useState(route.params.get("q") || "");
  const [q, setQ] = useState(search);
  const [type, setType] = useState("");
  const [status, setStatus] = useState(route.params.get("status") || "");
  const [owner, setOwner] = useState(
    route.params.get("assigned_staff_id") || "",
  );
  const [preset, setPreset] = useState(route.params.get("preset") || "");
  const [tab, setTab] = useState("all");
  const [sort, setSort] = useState("status");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(search);
      setOffset(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);
  const routeQ = route.params.get("q") || "",
    routeOwner = route.params.get("assigned_staff_id") || "",
    routePreset = route.params.get("preset") || "",
    routeStatus = route.params.get("status") || "";
  useEffect(() => {
    setSearch(routeQ);
    setOwner(routeOwner);
    setPreset(routePreset);
    setStatus(routeStatus);
    setType("");
    setTab("all");
    setOffset(0);
  }, [routeQ, routeOwner, routePreset, routeStatus]);
  const params: Params = {
    q,
    action_type: type,
    status: tab === "done" || tab === "closed" ? tab : status,
    assigned_staff_id: owner,
    preset,
    sort,
    offset,
    limit: SIZE,
    ...(tab === "attention"
      ? { flag: ["overdue", "due_soon", "unassigned"] }
      : {}),
    patient_id: route.params.get("patient_id") || undefined,
  };
  const rows = useApi<Page<Followup>>("followups", params);
  const options = useApi<Options>("options");
  const summary = useApi<Summary>("dashboard");
  const mutation = useComplete();
  useEffect(() => {
    if (rows.data && offset >= rows.data.total && offset > 0)
      setOffset(
        rows.data.total ? Math.floor((rows.data.total - 1) / SIZE) * SIZE : 0,
      );
  }, [rows.data, offset]);
  const reset = () => {
    setSearch("");
    setQ("");
    setType("");
    setStatus("");
    setOwner("");
    setPreset("");
    setTab("all");
    setOffset(0);
  };
  const change = (setter: (v: string) => void) => (v: string) => {
    setter(v);
    setOffset(0);
  };
  const d = summary.data?.followups;
  async function exportCsv() {
    try {
      if (!sample) {
        await downloadCsv("followups", {
          ...params,
          as_of_date: asOf,
          offset: undefined,
          limit: undefined,
        });
        return;
      }
      const all = await api<Page<Followup>>("followups", {
        params: { ...params, offset: 0, limit: 1000 },
      });
      const escape = (v: unknown) =>
        `"${String(v ?? "")
          .replace(/^[=+@\-]/, "'$&")
          .replaceAll('"', '""')}"`;
      const csv = [
        [
          "ID",
          "Patient",
          "Type",
          "Scheduled",
          "Assigned staff",
          "Status",
          "Attention",
        ],
        ...all.items.map((r) => [
          r.followup_id,
          r.patient_name,
          r.action_type,
          r.due_date,
          r.assigned_staff_name,
          r.status,
          r.flags.join(", "),
        ]),
      ]
        .map((row) => row.map(escape).join(","))
        .join("\r\n");
      const url = URL.createObjectURL(
        new Blob([csv], { type: "text/csv;charset=utf-8;" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "clinic-followups.csv";
      a.click();
      URL.revokeObjectURL(url);
      if (all.total > 1000)
        toast.info(
          "Export includes the first 1,000 matches. Narrow your filters to export a smaller set.",
        );
    } catch (error) {
      toast.error((error as Error).message);
    }
  }
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Follow-ups</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Manage every next step, from requested to resolved.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download />
            Export
          </Button>
          <Button
            size="sm"
            disabled={!manage}
            onClick={() => setCreating(true)}
          >
            <Plus />
            New follow-up
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[
          {
            label: "Overdue",
            value: d?.overdue_followups,
            preset: "overdue",
            color: "text-rose-600 dark:text-rose-400",
          },
          {
            label: "Due soon",
            value: d?.due_soon_followups,
            preset: "due_soon",
            color: "text-amber-600 dark:text-amber-400",
          },
          {
            label: "No scheduled date",
            value: d?.unassigned_followups,
            preset: "unassigned",
            color: "",
          },
          {
            label: "Open follow-ups",
            value: d?.open_followups,
            preset: "",
            color: "",
          },
        ].map((metric) => (
          <Card key={metric.label} className="gap-2 py-4 dark:bg-transparent">
            <button
              className="px-5 text-left"
              onClick={() => {
                reset();
                setPreset(metric.preset);
                if (!metric.preset) setStatus("open");
              }}
            >
              <span className="text-xs text-muted-foreground">
                {metric.label}
              </span>
              <p
                className={`mt-2 font-mono text-2xl tabular-nums ${metric.color}`}
              >
                {metric.value ?? "—"}
              </p>
            </button>
          </Card>
        ))}
      </div>
      <Card className="gap-0 overflow-hidden py-0 dark:bg-transparent">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
          <Tabs
            value={tab}
            onValueChange={(v) => {
              setTab(v);
              setStatus("");
              setPreset("");
              setOffset(0);
            }}
          >
            <TabsList variant="line">
              <TabsTrigger value="all">
                All follow-ups
                <Badge
                  variant="secondary"
                  className="ml-1 font-mono text-[10px]"
                >
                  {d?.followup_count ?? "—"}
                </Badge>
              </TabsTrigger>
              <TabsTrigger value="attention">Needs attention</TabsTrigger>
              <TabsTrigger value="done">Done</TabsTrigger>
              <TabsTrigger value="closed">Closed</TabsTrigger>
            </TabsList>
          </Tabs>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            As of
            <Input
              type="date"
              aria-label="As of date"
              value={asOf}
              onChange={(e) => {
                if (e.target.value) setAsOf(e.target.value);
              }}
              className="h-7 w-32 bg-background text-xs"
            />
          </label>
        </div>
        <div className="space-y-3 border-b p-4 sm:px-5">
          <div className="flex flex-wrap gap-3">
            <div className="relative min-w-52 flex-1 sm:max-w-sm">
              <Search className="absolute top-2 left-2.5 size-4 text-muted-foreground" />
              <Input
                aria-label="Search follow-ups"
                placeholder="Search patients, IDs, or notes..."
                className="h-8 bg-background pl-9 text-sm"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="ml-auto flex items-center gap-2">
              <ArrowDownWideNarrow className="size-3.5 text-muted-foreground" />
              <FilterSelect
                label="Sort"
                value={sort}
                onChange={change(setSort)}
                options={[
                  { value: "status", label: "Open first" },
                  { value: "due_date", label: "Due date: earliest" },
                  { value: "-due_date", label: "Due date: latest" },
                  { value: "patient_name", label: "Patient name" },
                  { value: "assigned_staff_name", label: "Assigned staff" },
                ]}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Filter className="mr-1 size-3.5 text-muted-foreground" />
            <FilterSelect
              label="All types"
              value={type}
              onChange={change(setType)}
              options={["lab", "referral", "recheck"].map((v) => ({
                value: v,
                label: titleCase(v),
              }))}
            />
            <FilterSelect
              label="All statuses"
              value={status}
              onChange={(v) => {
                setStatus(v);
                setTab("all");
                setOffset(0);
              }}
              options={[
                { value: "open", label: "Open" },
                { value: "done", label: "Done" },
                { value: "closed", label: "Closed" },
              ]}
            />
            <FilterSelect
              label="All staff"
              value={owner}
              onChange={change(setOwner)}
              options={
                options.data?.staff.map((s) => ({
                  value: s.staff_id,
                  label: s.name,
                })) || []
              }
            />
            <FilterSelect
              label="Any attention"
              value={preset}
              onChange={change(setPreset)}
              options={[
                { value: "overdue", label: "Overdue" },
                { value: "due_soon", label: "Due soon" },
                { value: "unassigned", label: "No scheduled date" },
              ]}
            />
            {Boolean(
              q || type || status || owner || preset || tab !== "all",
            ) && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-muted-foreground"
                onClick={reset}
              >
                <X />
                Reset
              </Button>
            )}
          </div>
        </div>
        <CardContent className="p-0">
          {rows.error ? (
            <div className="p-5">
              <WorkspaceError error={rows.error} retry={() => rows.refetch()} />
            </div>
          ) : rows.isPending ? (
            <div
              className="flex h-72 items-center justify-center text-sm text-muted-foreground"
              role="status"
            >
              Loading follow-ups…
            </div>
          ) : !rows.data?.items.length ? (
            <EmptyState action={reset} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30">
                  <TableHead className="pl-5">Patient</TableHead>
                  <TableHead>Follow-up type</TableHead>
                  <TableHead>Scheduled</TableHead>
                  <TableHead>Assigned staff</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Attention</TableHead>
                  <TableHead className="pr-5 text-right">Action</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.data.items.map((row) => (
                  <TableRow
                    key={row.followup_id}
                    data-state={
                      selected === row.followup_id ? "selected" : undefined
                    }
                    className="cursor-pointer"
                    onClick={() => setSelected(row.followup_id)}
                  >
                    <TableCell className="py-4 pl-5">
                      <button
                        className="flex items-center gap-2.5 text-left"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelected(row.followup_id);
                        }}
                      >
                        <Avatar className="size-8">
                          <AvatarFallback className="bg-muted text-[10px]">
                            {initials(row.patient_name)}
                          </AvatarFallback>
                        </Avatar>
                        <span className="whitespace-nowrap">
                          <span className="block font-medium">
                            {row.patient_name}
                          </span>
                          <span className="mt-0.5 block font-mono text-[11px] text-muted-foreground">
                            {row.patient_id} · {row.followup_id}
                          </span>
                        </span>
                      </button>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1.5 rounded-md border bg-muted/30 px-1.5 py-1 text-xs">
                        <FlaskConical className="size-3.5 text-muted-foreground" />
                        {titleCase(row.action_type)}
                      </span>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs">
                      <span>
                        {row.due_date
                          ? formatDate(row.due_date)
                          : "Not scheduled"}
                      </span>
                      {row.status === "open" && row.days_until_due !== null && (
                        <span
                          className={`mt-1 block text-[11px] ${row.days_until_due !== null && row.days_until_due < 0 ? "text-rose-600 dark:text-rose-400" : "text-muted-foreground"}`}
                        >
                          {row.days_until_due !== null && row.days_until_due < 0
                            ? `${-row.days_until_due} days overdue`
                            : row.days_until_due === 0
                              ? "Due today"
                              : `In ${row.days_until_due} days`}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                      {row.assigned_staff_name}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={row.status} />
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {row.flags.length ? (
                          row.flags.map((flag) => (
                            <AttentionBadge key={flag} flag={flag} />
                          ))
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            {row.status === "closed"
                              ? "Closed"
                              : row.status === "done"
                                ? "Completed"
                                : "On track"}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="pr-5 text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs"
                        aria-label={`${row.status !== "open" ? "Reopen" : "Mark done"} ${row.followup_id}`}
                        disabled={
                          !canEditFollowup(row) ||
                          (mutation.isPending &&
                            mutation.variables?.id === row.followup_id)
                        }
                        onClick={(e) => {
                          e.stopPropagation();
                          mutation.mutate({
                            id: row.followup_id,
                            status: row.status !== "open" ? "open" : "done",
                          });
                        }}
                      >
                        {row.status !== "open" ? (
                          <Undo2 className="size-3" />
                        ) : (
                          <Check className="size-3" />
                        )}
                        {row.status !== "open" ? "Reopen" : "Mark done"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
        <div className="flex items-center justify-between gap-3 border-t px-5 py-3 text-xs text-muted-foreground">
          <span>
            {rows.data?.total
              ? `${offset + 1}–${Math.min(offset + SIZE, rows.data.total)} of ${rows.data.total} follow-ups`
              : "0 follow-ups"}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Previous page"
              disabled={offset === 0 || rows.isPending || rows.isError}
              onClick={() => setOffset(Math.max(0, offset - SIZE))}
            >
              <ChevronLeft />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Next page"
              disabled={
                !rows.data ||
                offset + SIZE >= rows.data.total ||
                rows.isPending ||
                rows.isError
              }
              onClick={() => setOffset(offset + SIZE)}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      </Card>
      <FollowupDetailPanel id={selected} onClose={() => setSelected(null)} />
      <RecordEditor
        resource="followups"
        open={creating}
        onClose={() => setCreating(false)}
      />
    </div>
  );
}
