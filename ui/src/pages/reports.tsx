import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import { WorkspaceError, WorkspaceLoading } from "@/components/workspace-state";
import { Button } from "@/components/ui/button";
import { Printer } from "lucide-react";
import { useApi, useWorkspace } from "@/lib/workspace";
import { titleCase } from "@/lib/types";
import type { Stats } from "@/lib/types";
export function ReportsPage() {
  const { asOf, sample } = useWorkspace();
  const owners = useApi<Stats>("followups/stats", {
    group_by: "assigned_staff",
  });
  const types = useApi<Stats>("followups/stats", { group_by: "action_type" });
  if (owners.error || types.error)
    return (
      <WorkspaceError
        error={(owners.error || types.error)!}
        retry={() => {
          void owners.refetch();
          void types.refetch();
        }}
      />
    );
  if (!owners.data || !types.data) return <WorkspaceLoading />;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">
            Follow-up reports
          </h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            A clear view of workload, urgency, and completion.
          </p>
        </div>
        {sample ? (
          <Button variant="outline" onClick={() => window.print()}>
            <Printer />
            Print report
          </Button>
        ) : (
          <Button asChild variant="outline">
            <a
              href={`/report?as_of_date=${encodeURIComponent(asOf)}`}
              target="_blank"
              rel="noreferrer"
            >
              <Printer />
              Print report
            </a>
          </Button>
        )}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {[owners.data, types.data].map((report, i) => (
          <Card className="dark:bg-transparent" key={i}>
            <CardHeader>
              <CardTitle>
                {i === 0
                  ? "Workload by assigned staff"
                  : "Workload by follow-up type"}
              </CardTitle>
              <CardDescription>
                {report.totals.followup_count} follow-ups in your workspace.
              </CardDescription>
            </CardHeader>
            <CardContent className="px-0">
              <Table className="border-t">
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-6">
                      {i === 0 ? "Staff" : "Type"}
                    </TableHead>
                    <TableHead className="text-right">Open</TableHead>
                    <TableHead className="text-right">Overdue</TableHead>
                    <TableHead className="text-right">No date</TableHead>
                    <TableHead className="text-right">Done</TableHead>
                    <TableHead className="pr-6 text-right">Closed</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {report.groups.map((g) => (
                    <TableRow key={g.key ?? "unassigned"}>
                      <TableCell className="pl-6 font-medium">
                        {i === 0
                          ? g.label || "Unassigned"
                          : titleCase(g.label || "Other")}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {g.open_followups}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {g.overdue_followups}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {g.unassigned_followups}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {g.done_followups}
                      </TableCell>
                      <TableCell className="pr-6 text-right font-mono">
                        {g.closed_followups}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {!report.groups.length && (
                <p className="p-10 text-center text-sm text-muted-foreground">
                  No follow-up data to report yet.
                </p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
