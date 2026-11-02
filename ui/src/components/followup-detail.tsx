import { useEffect, useState } from "react";
import {
  CalendarDays,
  Check,
  ExternalLink,
  FileText,
  FlaskConical,
  Loader2,
  Pencil,
  Stethoscope,
  Undo2,
  UserRound,
} from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, AttentionBadge } from "@/components/followup-badges";
import { useRecordPermissions } from "@/lib/session";
import { RecordEditor } from "@/components/record-editor";
import { useApi, useComplete } from "@/lib/workspace";
import { formatDate, titleCase, initials } from "@/lib/types";
import { navigate } from "@/lib/router";
import type { FollowupDetail } from "@/lib/types";
export function FollowupDetailPanel({
  id,
  onClose,
}: {
  id: string | null;
  onClose: () => void;
}) {
  const query = useApi<FollowupDetail>(
    `followups/${encodeURIComponent(id || "")}`,
    {},
    Boolean(id),
  );
  const mutation = useComplete();
  const { canEditFollowup } = useRecordPermissions();
  const [editing, setEditing] = useState(false);
  const [closing, setClosing] = useState(false);
  useEffect(() => setEditing(false), [id]);
  const f = query.data?.followup;
  return (
    <>
      <Sheet
        open={Boolean(id)}
        onOpenChange={(v) => {
          if (!v) onClose();
        }}
      >
        <SheetContent className="flex w-full flex-col gap-0 p-0 sm:max-w-[440px]">
          <SheetHeader className="border-b px-6 py-5">
            <SheetTitle className="text-sm font-medium">
              Follow-up details
            </SheetTitle>
            <SheetDescription className="font-mono text-xs">
              {id}
            </SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto p-6">
            {query.isPending ? (
              <div className="space-y-4">
                <Skeleton className="size-12 rounded-xl" />
                <Skeleton className="h-7 w-2/3" />
                <Skeleton className="h-60 w-full" />
              </div>
            ) : query.error ? (
              <div role="alert" className="space-y-4 text-sm">
                <p>{query.error.message}</p>
                <Button variant="outline" onClick={() => query.refetch()}>
                  Try again
                </Button>
              </div>
            ) : (
              f && (
                <>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <Avatar className="mb-4 size-12 rounded-xl">
                        <AvatarFallback className="rounded-xl bg-muted text-base">
                          {initials(f.patient_name)}
                        </AvatarFallback>
                      </Avatar>
                      <h2 className="text-xl font-semibold tracking-tight">
                        {f.patient_name}
                      </h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {f.patient_id} · {titleCase(f.action_type)} follow-up
                      </p>
                    </div>
                    <Button
                      size="icon-sm"
                      variant="outline"
                      aria-label="Edit follow-up"
                      disabled={!canEditFollowup(f)}
                      onClick={() => {
                        setClosing(false);
                        setEditing(true);
                      }}
                    >
                      <Pencil />
                    </Button>
                  </div>
                  <div className="my-5 flex flex-wrap gap-2">
                    <StatusBadge status={f.status} />
                    {f.flags.map((flag) => (
                      <AttentionBadge key={flag} flag={flag} />
                    ))}
                  </div>
                  <Separator />
                  <dl className="grid grid-cols-[135px_1fr] gap-y-5 py-6 text-sm">
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <FlaskConical className="size-4" />
                      Type
                    </dt>
                    <dd>{titleCase(f.action_type)}</dd>
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <CalendarDays className="size-4" />
                      Scheduled
                    </dt>
                    <dd
                      className={
                        f.flags.includes("overdue")
                          ? "text-rose-600 dark:text-rose-400"
                          : ""
                      }
                    >
                      {f.due_date ? formatDate(f.due_date) : "Not scheduled"}
                    </dd>
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <UserRound className="size-4" />
                      Assigned staff
                    </dt>
                    <dd>{f.assigned_staff_name}</dd>
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <Stethoscope className="size-4" />
                      Visit staff
                    </dt>
                    <dd>{f.visit_staff_name || "Not assigned"}</dd>
                    <dt className="flex items-center gap-2 text-muted-foreground">
                      <FileText className="size-4" />
                      Episode
                    </dt>
                    <dd>{f.episode_description}</dd>
                  </dl>
                  <Separator />
                  <section className="py-6">
                    <h3 className="mb-3 text-sm font-medium">
                      Follow-up notes / closure reason
                    </h3>
                    <p className="whitespace-pre-wrap rounded-lg border p-4 text-sm leading-relaxed">
                      {f.notes || "No follow-up notes recorded."}
                    </p>
                  </section>
                  <section className="py-6">
                    <h3 className="mb-3 text-sm font-medium">Visit summary</h3>
                    <p className="rounded-lg border bg-muted/40 p-4 text-sm leading-relaxed text-muted-foreground">
                      {f.visit_notes ||
                        "No notes were recorded for this visit."}
                    </p>
                  </section>
                  <section>
                    <h3 className="mb-5 text-sm font-medium">
                      Visit & follow-up context
                    </h3>
                    <ol className="ml-2 space-y-5 border-l pl-5">
                      <li className="relative">
                        <span className="absolute top-1 -left-[25px] size-2 rounded-full border bg-background" />
                        <p className="text-sm">Clinic visit</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {formatDate(f.visit_date)} ·{" "}
                          {f.visit_staff_name || "Staff not assigned"}
                        </p>
                      </li>
                      <li className="relative">
                        <span className="absolute top-1 -left-[25px] size-2 rounded-full border bg-background" />
                        <p className="text-sm">
                          {titleCase(f.action_type)} follow-up due
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {f.due_date
                            ? formatDate(f.due_date)
                            : "Not scheduled"}
                        </p>
                      </li>
                      {f.completed_at && (
                        <li className="relative">
                          <span className="absolute top-1 -left-[25px] size-2 rounded-full border bg-emerald-500" />
                          <p className="text-sm">Follow-up completed</p>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {new Date(f.completed_at).toLocaleString()}
                          </p>
                        </li>
                      )}
                    </ol>
                  </section>
                  <section className="mt-6 border-t pt-5">
                    <h3 className="mb-4 text-sm font-medium">
                      Follow-up history
                    </h3>
                    <ol className="space-y-4">
                      {query.data?.history
                        .slice()
                        .reverse()
                        .map((h) => (
                          <li
                            key={h.change_id}
                            className="rounded-lg border p-3 text-xs"
                          >
                            <p className="font-medium">
                              {h.field === "status"
                                ? "Status"
                                : h.field === "due_date"
                                  ? "Scheduled date"
                                  : "Assigned staff"}
                            </p>
                            <p className="mt-2">
                              {h.field === "due_date"
                                ? formatDate(h.old_value)
                                : titleCase(h.old_value || "Not set")}{" "}
                              →{" "}
                              {h.field === "due_date"
                                ? formatDate(h.new_value)
                                : titleCase(h.new_value || "Not set")}
                            </p>
                            <p className="mt-1 text-muted-foreground">
                              {new Date(h.changed_at).toLocaleString()} ·{" "}
                              {h.changed_by_name || h.changed_by || "System"}
                            </p>
                            {h.note && (
                              <p className="mt-2 whitespace-pre-wrap text-muted-foreground">
                                {h.note}
                              </p>
                            )}
                          </li>
                        ))}
                      {!query.data?.history.length && (
                        <li className="text-xs text-muted-foreground">
                          No recorded changes yet.
                        </li>
                      )}
                    </ol>
                  </section>
                  <Button
                    variant="outline"
                    className="mt-6 w-full"
                    onClick={() => {
                      onClose();
                      navigate("patients", { selected: f.patient_id });
                    }}
                  >
                    View patient history
                    <ExternalLink />
                  </Button>
                  {Boolean(query.data?.episode_followups.length) && (
                    <section className="mt-6 border-t pt-5">
                      <h3 className="mb-3 text-sm font-medium">
                        Related follow-ups
                      </h3>
                      {query.data?.episode_followups.map((r) => (
                        <p
                          key={r.followup_id}
                          className="flex justify-between py-2 text-sm"
                        >
                          <span>
                            {r.followup_id} · {titleCase(r.action_type)}
                          </span>
                          <StatusBadge status={r.status} />
                        </p>
                      ))}
                    </section>
                  )}
                </>
              )
            )}
          </div>
          {f && (
            <div className="space-y-2 border-t bg-background p-5">
              <Button
                className="w-full"
                disabled={mutation.isPending || !canEditFollowup(f)}
                onClick={() =>
                  mutation.mutate({
                    id: f.followup_id,
                    status: f.status !== "open" ? "open" : "done",
                  })
                }
              >
                {mutation.isPending ? (
                  <Loader2 className="animate-spin" />
                ) : f.status !== "open" ? (
                  <Undo2 />
                ) : (
                  <Check />
                )}
                {f.status !== "open"
                  ? "Reopen follow-up"
                  : "Mark follow-up done"}
              </Button>
              {f.status !== "closed" && (
                <Button
                  variant="outline"
                  disabled={!canEditFollowup(f)}
                  className="w-full"
                  onClick={() => {
                    setClosing(true);
                    setEditing(true);
                  }}
                >
                  Close follow-up
                </Button>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
      {f && (
        <RecordEditor
          resource="followups"
          open={editing}
          onClose={() => setEditing(false)}
          record={f as unknown as Record<string, unknown>}
          prefill={
            closing
              ? {
                  status: "closed",
                  ...(f.status === "open" || !f.completed_at
                    ? { notes: "" }
                    : {}),
                }
              : {}
          }
        />
      )}
    </>
  );
}
