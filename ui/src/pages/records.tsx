import { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Pencil,
  Plus,
  Search,
  Download,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import {
  RecordEditor,
  RESOURCE_CONFIG,
  type Resource,
} from "@/components/record-editor";
import { EmptyState, WorkspaceError } from "@/components/workspace-state";
import { useRecordPermissions } from "@/lib/session";
import { useApi, useWorkspace } from "@/lib/workspace";
import { downloadCsv } from "@/lib/api";
import { toast } from "sonner";
import { navigate, useRoute } from "@/lib/router";
import { formatDate, titleCase } from "@/lib/types";
import type { Page } from "@/lib/types";
type Row = Record<string, unknown>;
const columns: Record<string, [string, string][]> = {
  patients: [
    ["patient_id", "ID"],
    ["name", "Patient"],
    ["phone", "Phone"],
    ["email", "Email"],
    ["visit_count", "Visits"],
    ["open_followups", "Open"],
    ["overdue_followups", "Overdue"],
    ["next_due_date", "Next due"],
  ],
  staff: [
    ["staff_id", "ID"],
    ["name", "Name"],
    ["role", "Role"],
    ["visit_count", "Visits"],
    ["open_followups", "Open follow-ups"],
    ["overdue_followups", "Overdue"],
  ],
  visits: [
    ["visit_id", "ID"],
    ["visit_date", "Visit date"],
    ["patient_name", "Patient"],
    ["staff_name", "Seen by"],
    ["episode_description", "Episode"],
    ["open_followups", "Open follow-ups"],
  ],
  episodes: [
    ["episode_id", "ID"],
    ["patient_name", "Patient"],
    ["description", "Description"],
    ["status", "Status"],
    ["opened_at", "Opened"],
    ["visit_count", "Visits"],
    ["open_followups", "Open follow-ups"],
  ],
};
const singular: Record<string, string> = {
  patients: "patient",
  staff: "staff",
  visits: "visit",
  episodes: "episode",
};
export function RecordsPage({
  resource,
}: {
  resource: Exclude<Resource, "followups">;
}) {
  const config = RESOURCE_CONFIG[resource];
  const { manage } = useRecordPermissions();
  const { sample, asOf } = useWorkspace();
  const route = useRoute();
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<string | null>(
    route.params.get("selected"),
  );
  const [editor, setEditor] = useState<{
    open: boolean;
    record?: Row;
    resource: Resource;
    prefill?: Record<string, string>;
  }>({ open: false, resource });
  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(search);
      setOffset(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);
  const requested = route.params.get("selected");
  useEffect(() => {
    setSelected(requested);
  }, [requested]);
  const query = useApi<Page<Row>>(resource, { q, offset, limit: 15 });
  const detail = useApi<Row>(
    `${resource}/${encodeURIComponent(selected || "")}`,
    {},
    Boolean(selected),
  );
  const record = detail.data?.[singular[resource]] as Row | undefined;
  const episodes = (detail.data?.episodes || []) as Row[];
  const fields = columns[resource];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            {config.title}
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Connected clinic records, with the context to act.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={sample}
            onClick={() =>
              void downloadCsv(resource, { q, as_of_date: asOf }).catch(
                (error: Error) => toast.error(error.message),
              )
            }
          >
            <Download />
            Export CSV
          </Button>
          <Button
            size="sm"
            disabled={!manage}
            onClick={() => setEditor({ open: true, resource })}
          >
            <Plus />
            New {config.singular}
          </Button>
        </div>
      </div>
      <Card className="gap-0 overflow-hidden py-0 dark:bg-transparent">
        <div className="border-b p-4">
          <div className="relative max-w-sm">
            <Search className="absolute top-2 left-2.5 size-4 text-muted-foreground" />
            <Input
              value={search}
              aria-label={`Search ${config.title.toLowerCase()}`}
              placeholder={`Search ${config.title.toLowerCase()}...`}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 bg-background pl-9"
            />
          </div>
        </div>
        <CardContent className="p-0">
          {query.error ? (
            <div className="p-5">
              <WorkspaceError
                error={query.error}
                retry={() => query.refetch()}
              />
            </div>
          ) : query.isPending ? (
            <p
              role="status"
              className="p-16 text-center text-sm text-muted-foreground"
            >
              Loading records…
            </p>
          ) : !query.data?.items.length ? (
            <EmptyState
              title="No matching records"
              action={() => setSearch("")}
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  {fields.map(([key, label], i) => (
                    <TableHead key={key} className={i === 0 ? "pl-5" : ""}>
                      {label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.items.map((row) => (
                  <TableRow
                    key={String(row[config.id])}
                    className="cursor-pointer"
                    onClick={() => setSelected(String(row[config.id]))}
                  >
                    {fields.map(([key], i) => (
                      <TableCell
                        key={key}
                        className={`py-4 ${i === 0 ? "pl-5 font-mono text-xs" : ""}`}
                      >
                        {i === 0 ? (
                          <Button
                            variant="link"
                            className="h-auto p-0 font-mono text-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelected(String(row[config.id]));
                            }}
                          >
                            {String(row[key])}
                          </Button>
                        ) : key === "status" ? (
                          <Badge variant="outline" className="font-normal">
                            {titleCase(String(row[key]))}
                          </Badge>
                        ) : key.includes("date") || key.endsWith("_at") ? (
                          formatDate(row[key] as string | null)
                        ) : (
                          String(row[key] ?? "—")
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
        <div className="flex items-center justify-between border-t px-5 py-3 text-xs text-muted-foreground">
          <span>
            {query.data?.total || 0} {config.title.toLowerCase()}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Previous page"
              disabled={!offset || query.isPending || query.isError}
              onClick={() => setOffset(Math.max(0, offset - 15))}
            >
              <ChevronLeft />
            </Button>
            <Button
              variant="outline"
              size="icon-sm"
              aria-label="Next page"
              disabled={
                !query.data ||
                offset + 15 >= query.data.total ||
                query.isPending ||
                query.isError
              }
              onClick={() => setOffset(offset + 15)}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      </Card>
      <Sheet
        open={Boolean(selected)}
        onOpenChange={(v) => {
          if (!v) setSelected(null);
        }}
      >
        <SheetContent className="gap-0 overflow-y-auto p-0 sm:max-w-lg">
          <SheetHeader className="border-b p-6">
            <SheetTitle>
              {record?.name
                ? String(record.name)
                : `${titleCase(config.singular)} details`}
            </SheetTitle>
            <SheetDescription>{selected}</SheetDescription>
          </SheetHeader>
          <div className="space-y-6 p-6">
            {detail.error ? (
              <p role="alert" className="text-sm text-destructive">
                {detail.error.message}
              </p>
            ) : !record ? (
              <p role="status" className="text-sm text-muted-foreground">
                Loading record…
              </p>
            ) : (
              <>
                <dl className="grid grid-cols-[120px_1fr] gap-4 text-sm">
                  {Object.entries(record)
                    .filter(
                      ([, v]) => !Array.isArray(v) && typeof v !== "object",
                    )
                    .map(([key, value]) => (
                      <div key={key} className="contents">
                        <dt className="text-muted-foreground">
                          {titleCase(key)}
                        </dt>
                        <dd className="min-w-0 break-words">
                          {String(value ?? "—")}
                        </dd>
                      </div>
                    ))}
                </dl>
                <Button
                  variant="outline"
                  disabled={!manage}
                  onClick={() => setEditor({ open: true, resource, record })}
                >
                  <Pencil />
                  Edit {config.singular}
                </Button>
                {resource === "patients" && (
                  <>
                    <div className="flex items-center justify-between border-t pt-5">
                      <h3 className="text-sm font-medium">
                        Episodes & visit history
                      </h3>
                      <Button
                        disabled={!manage}
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          setEditor({
                            open: true,
                            resource: "episodes",
                            prefill: { patient_id: selected! },
                          })
                        }
                      >
                        <Plus />
                        Episode
                      </Button>
                    </div>
                    {episodes.map((e) => (
                      <section
                        key={String(e.episode_id)}
                        className="rounded-lg border p-4"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <h4 className="text-sm font-medium">
                            {String(e.description)}
                          </h4>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() =>
                              setEditor({
                                open: true,
                                resource: "visits",
                                prefill: { episode_id: String(e.episode_id) },
                              })
                            }
                          >
                            <Plus />
                            Visit
                          </Button>
                        </div>
                        <p className="my-2 text-xs text-muted-foreground">
                          {String(e.episode_id)} ·{" "}
                          {formatDate(String(e.opened_at))}
                        </p>
                        {((e.visits || []) as Row[]).map((v) => (
                          <div
                            key={String(v.visit_id)}
                            className="mt-3 space-y-2 border-t pt-3"
                          >
                            <p className="text-xs font-medium">
                              {formatDate(String(v.visit_date))} ·{" "}
                              {String(v.staff_name || "Not assigned")}
                            </p>
                            <p className="text-xs leading-relaxed text-muted-foreground">
                              {String(v.notes || "No visit notes.")}
                            </p>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                setEditor({
                                  open: true,
                                  resource: "followups",
                                  prefill: { visit_id: String(v.visit_id) },
                                })
                              }
                            >
                              Add follow-up
                            </Button>
                          </div>
                        ))}
                      </section>
                    ))}
                    <Button
                      className="w-full"
                      variant="outline"
                      onClick={() => {
                        setSelected(null);
                        navigate("followups", { patient_id: selected! });
                      }}
                    >
                      View patient follow-ups
                      <ExternalLink />
                    </Button>
                  </>
                )}
              </>
            )}
          </div>
        </SheetContent>
      </Sheet>
      <RecordEditor
        resource={editor.resource}
        open={editor.open}
        record={editor.record}
        prefill={editor.prefill}
        onClose={() => setEditor({ ...editor, open: false })}
      />
    </div>
  );
}
