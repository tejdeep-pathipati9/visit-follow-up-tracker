// Month calendar of scheduled follow-ups and the clinic's important dates (release 1.1.0).
// Drag a follow-up or an event onto another day to move it; drag a follow-up with no
// date onto a day to schedule it. Every follow-up move is kept in its history.
import { useEffect, useMemo, useState, type DragEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  CalendarPlus,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Trash2,
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
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AttentionBadge, StatusBadge } from "@/components/followup-badges";
import { FollowupDetailPanel } from "@/components/followup-detail";
import {
  WorkspaceError,
  WorkspaceLoading,
} from "@/components/workspace-state";
import { useRecordPermissions } from "@/lib/session";
import { useApi, useWorkspace } from "@/lib/workspace";
import { addDays, formatDate, isoDate, titleCase } from "@/lib/types";
import type { CalendarEvent, Followup, Options, Page } from "@/lib/types";
import { cn } from "@/lib/utils";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const CLINIC = "__clinic";
const monthStart = (day: string) => day.slice(0, 8) + "01";
const noon = (day: string) => new Date(`${day}T12:00:00`);
// Six weeks from the Sunday on or before the first of the month.
const monthDays = (start: string) => {
  const from = addDays(start, -noon(start).getDay());
  return Array.from({ length: 42 }, (_, i) => addDays(from, i));
};
const TONES = {
  overdue:
    "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300",
  soon: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  scheduled: "border-border bg-background text-foreground",
  finished: "border-transparent bg-muted text-muted-foreground line-through",
  event:
    "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950 dark:text-sky-300",
};
const tone = (f: Followup) =>
  f.status !== "open"
    ? "finished"
    : f.flags.includes("overdue")
      ? "overdue"
      : f.flags.includes("due_soon")
        ? "soon"
        : "scheduled";
type Item =
  | { kind: "event"; event: CalendarEvent }
  | { kind: "followup"; followup: Followup };

export function CalendarPage() {
  const { asOf, api, sample } = useWorkspace();
  const { manage, user, canEditFollowup } = useRecordPermissions();
  const cache = useQueryClient();
  const [month, setMonth] = useState(() => monthStart(asOf));
  const [day, setDay] = useState(asOf);
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<{
    event?: CalendarEvent;
    date: string;
  } | null>(null);
  const days = useMemo(() => monthDays(month), [month]);
  const followups = useApi<Page<Followup>>("followups", {
    due_from: days[0],
    due_to: days[days.length - 1],
    limit: 1000,
    sort: "due_date",
  });
  const unscheduled = useApi<Page<Followup>>("followups", {
    preset: "unassigned",
    limit: 50,
    sort: "visit_date",
  });
  const events = useApi<CalendarEvent[]>("events", {
    date_from: days[0],
    date_to: days[days.length - 1],
  });
  const canEditEvent = (e: CalendarEvent) =>
    manage || e.staff_id === user?.staff_id;
  const move = useMutation({
    mutationFn: ({ kind, id, date }: { kind: string; id: string; date: string }) =>
      api(
        `${kind === "event" ? "events" : "followups"}/${encodeURIComponent(id)}`,
        {
          method: "PATCH",
          body: kind === "event" ? { event_date: date } : { due_date: date },
        },
      ),
    onSuccess: async (_, v) => {
      await cache.invalidateQueries();
      toast.success(
        `${v.kind === "event" ? "Event" : `Follow-up ${v.id}`} moved to ${formatDate(v.date)}.`,
      );
    },
    onError: (error) => toast.error(error.message),
  });
  const byDay = useMemo(() => {
    const map = new Map<string, Item[]>();
    const add = (date: string, item: Item) =>
      map.set(date, [...(map.get(date) ?? []), item]);
    events.data?.forEach((event) => add(event.event_date, { kind: "event", event }));
    followups.data?.items.forEach((followup) =>
      add(followup.due_date!, { kind: "followup", followup }),
    );
    return map;
  }, [events.data, followups.data]);

  const failure = followups.error || unscheduled.error || events.error;
  if (failure)
    return (
      <WorkspaceError
        error={failure}
        retry={() => {
          void Promise.all([
            followups.refetch(),
            unscheduled.refetch(),
            events.refetch(),
          ]);
        }}
      />
    );
  if (!followups.data || !unscheduled.data || !events.data)
    return <WorkspaceLoading />;

  // Moving needs the connected workspace and permission for that record.
  const movable = (item: Item) =>
    !sample &&
    (item.kind === "event"
      ? canEditEvent(item.event)
      : item.followup.status === "open" && canEditFollowup(item.followup));
  const drag = (kind: string, id: string) => (e: DragEvent) => {
    e.dataTransfer.setData("text/plain", `${kind}:${id}`);
    e.dataTransfer.effectAllowed = "move";
  };
  const drop = (date: string) => (e: DragEvent) => {
    e.preventDefault();
    const [kind, id] = e.dataTransfer.getData("text/plain").split(":");
    if (kind && id) move.mutate({ kind, id, date });
  };
  const open = (item: Item) =>
    item.kind === "event"
      ? setEditing({ event: item.event, date: item.event.event_date })
      : setSelected(item.followup.followup_id);
  const chip = (item: Item) => {
    const isEvent = item.kind === "event";
    const id = isEvent ? item.event.event_id : item.followup.followup_id;
    return (
      <button
        key={id}
        type="button"
        draggable={movable(item)}
        onDragStart={drag(item.kind, id)}
        onClick={(e) => {
          e.stopPropagation();
          open(item);
        }}
        className={cn(
          "block w-full truncate rounded border px-1.5 py-0.5 text-left text-[11px] leading-4",
          movable(item) && "cursor-grab",
          TONES[isEvent ? "event" : tone(item.followup)],
        )}
      >
        {isEvent ? (
          <>
            {item.event.start_time && (
              <span className="font-mono">{item.event.start_time} </span>
            )}
            {item.event.title}
          </>
        ) : (
          `${item.followup.patient_name} · ${titleCase(item.followup.action_type)}`
        )}
      </button>
    );
  };
  const dayItems = byDay.get(day) ?? [];
  const dayEvents = dayItems.flatMap((i) => (i.kind === "event" ? [i.event] : []));
  const dayFollowups = dayItems.flatMap((i) =>
    i.kind === "followup" ? [i.followup] : [],
  );
  const shift = (months: number) => {
    const d = noon(month);
    d.setMonth(d.getMonth() + months);
    setMonth(monthStart(isoDate(d)));
  };

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Calendar</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Scheduled follow-ups and the clinic’s important dates.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Previous month"
            onClick={() => shift(-1)}
          >
            <ChevronLeft />
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setMonth(monthStart(asOf));
              setDay(asOf);
            }}
          >
            Today
          </Button>
          <Button
            size="icon-sm"
            variant="outline"
            aria-label="Next month"
            onClick={() => shift(1)}
          >
            <ChevronRight />
          </Button>
          <h2 className="min-w-36 text-center text-sm font-medium" aria-live="polite">
            {noon(month).toLocaleDateString("en-US", {
              month: "long",
              year: "numeric",
            })}
          </h2>
          <Button size="sm" onClick={() => setEditing({ date: day })}>
            <CalendarPlus />
            New event
          </Button>
        </div>
      </div>
      <div className="grid items-start gap-4 xl:grid-cols-[1fr_320px]">
        <Card className="gap-0 overflow-hidden py-0 dark:bg-transparent">
          <div className="grid grid-cols-7 border-b bg-muted/40 text-xs font-medium text-muted-foreground">
            {WEEKDAYS.map((name) => (
              <div key={name} className="px-2 py-2">
                {name}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7" aria-label="Month">
            {days.map((date) => {
              const items = byDay.get(date) ?? [];
              const inMonth = date.slice(0, 7) === month.slice(0, 7);
              const count = (kind: string) =>
                items.filter((i) => i.kind === kind).length;
              return (
                <div
                  key={date}
                  data-date={date}
                  onClick={() => setDay(date)}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={drop(date)}
                  className={cn(
                    "min-h-28 cursor-pointer border-r border-b p-1.5 transition-colors hover:bg-muted/40 [&:nth-child(7n)]:border-r-0",
                    !inMonth && "bg-muted/20 text-muted-foreground",
                    date === day && "bg-accent/60 hover:bg-accent/60",
                  )}
                >
                  <button
                    type="button"
                    aria-label={`${formatDate(date)}: ${count("followup")} follow-ups, ${count("event")} events`}
                    aria-pressed={date === day}
                    onClick={() => setDay(date)}
                    className={cn(
                      "mb-1 flex size-6 items-center justify-center rounded-full text-xs tabular-nums",
                      date === asOf &&
                        "bg-primary font-semibold text-primary-foreground",
                    )}
                  >
                    {noon(date).getDate()}
                  </button>
                  <div className="space-y-1">
                    {items.slice(0, 3).map(chip)}
                    {items.length > 3 && (
                      <p className="px-1 text-[11px] text-muted-foreground">
                        +{items.length - 3} more
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 border-t px-4 py-2.5 text-[11px] text-muted-foreground">
            {(
              [
                ["overdue", "Overdue"],
                ["soon", "Due soon"],
                ["scheduled", "Scheduled"],
                ["finished", "Done or closed"],
                ["event", "Important date"],
              ] as const
            ).map(([key, label]) => (
              <span key={key} className="flex items-center gap-1.5">
                <span className={cn("size-2.5 rounded-sm border", TONES[key])} />
                {label}
              </span>
            ))}
            {followups.data.total > followups.data.items.length && (
              <span className="ml-auto">
                Showing the first {followups.data.items.length} follow-ups.
              </span>
            )}
          </div>
        </Card>
        <div className="space-y-4">
          <Card className="gap-4 dark:bg-transparent">
            <CardHeader>
              <CardTitle>{formatDate(day)}</CardTitle>
              <CardDescription>
                {noon(day).toLocaleDateString("en-US", { weekday: "long" })}
              </CardDescription>
              <CardAction>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setEditing({ date: day })}
                >
                  <CalendarPlus />
                  Add
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-5">
              <section>
                <h3 className="mb-2 text-xs font-medium text-muted-foreground">
                  Important dates
                </h3>
                <div className="space-y-1.5">
                  {dayEvents.map((e) => (
                    <button
                      key={e.event_id}
                      type="button"
                      onClick={() => setEditing({ event: e, date: e.event_date })}
                      className="w-full rounded-md border px-3 py-2 text-left hover:bg-muted/50"
                    >
                      <span className="block text-sm font-medium">{e.title}</span>
                      <span className="text-xs text-muted-foreground">
                        {e.start_time ?? "All day"} · {e.staff_name ?? "Whole clinic"}
                      </span>
                    </button>
                  ))}
                  {!dayEvents.length && (
                    <p className="text-sm text-muted-foreground">
                      Nothing scheduled.
                    </p>
                  )}
                </div>
              </section>
              <section>
                <h3 className="mb-2 text-xs font-medium text-muted-foreground">
                  Follow-ups scheduled
                </h3>
                <div className="space-y-1.5">
                  {dayFollowups.map((f) => (
                    <button
                      key={f.followup_id}
                      type="button"
                      onClick={() => setSelected(f.followup_id)}
                      className="flex w-full items-start justify-between gap-2 rounded-md border px-3 py-2 text-left hover:bg-muted/50"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium">
                          {f.patient_name}
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {titleCase(f.action_type)} · {f.assigned_staff_name}
                        </span>
                      </span>
                      {f.status !== "open" ? (
                        <StatusBadge status={f.status} />
                      ) : (
                        f.flags[0] && <AttentionBadge flag={f.flags[0]} />
                      )}
                    </button>
                  ))}
                  {!dayFollowups.length && (
                    <p className="text-sm text-muted-foreground">
                      No follow-ups on this day.
                    </p>
                  )}
                </div>
              </section>
            </CardContent>
          </Card>
          <Card className="gap-4 dark:bg-transparent">
            <CardHeader>
              <CardTitle>No scheduled date</CardTitle>
              <CardDescription>
                {sample
                  ? "Open follow-ups waiting for a date."
                  : "Drag one onto a day to schedule it."}
              </CardDescription>
            </CardHeader>
            <CardContent className="max-h-[26rem] space-y-1.5 overflow-y-auto">
              {unscheduled.data.items.map((f) => {
                const item: Item = { kind: "followup", followup: f };
                return (
                  <button
                    key={f.followup_id}
                    type="button"
                    draggable={movable(item)}
                    onDragStart={drag("followup", f.followup_id)}
                    onClick={() => setSelected(f.followup_id)}
                    className={cn(
                      "w-full rounded-md border px-3 py-2 text-left hover:bg-muted/50",
                      movable(item) && "cursor-grab",
                    )}
                  >
                    <span className="block truncate text-sm font-medium">
                      {f.patient_name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {titleCase(f.action_type)} · {f.assigned_staff_name}
                    </span>
                  </button>
                );
              })}
              {!unscheduled.data.total && (
                <p className="text-sm text-muted-foreground">
                  Every open follow-up has a date.
                </p>
              )}
              {unscheduled.data.total > unscheduled.data.items.length && (
                <p className="pt-1 text-xs text-muted-foreground">
                  Showing {unscheduled.data.items.length} of{" "}
                  {unscheduled.data.total}.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <EventEditor
        open={editing !== null}
        event={editing?.event}
        date={editing?.date ?? day}
        onClose={() => setEditing(null)}
      />
      <FollowupDetailPanel id={selected} onClose={() => setSelected(null)} />
    </>
  );
}

function EventEditor({
  open,
  event,
  date,
  onClose,
}: {
  open: boolean;
  event?: CalendarEvent;
  date: string;
  onClose: () => void;
}) {
  const { api, sample } = useWorkspace();
  const { manage, user } = useRecordPermissions();
  const cache = useQueryClient();
  const options = useApi<Options>("options", {}, open && manage);
  const [values, setValues] = useState({
    title: "",
    event_date: date,
    start_time: "",
    staff_id: CLINIC,
    notes: "",
  });
  useEffect(() => {
    if (open)
      setValues({
        title: event?.title ?? "",
        event_date: event?.event_date ?? date,
        start_time: event?.start_time ?? "",
        staff_id: event?.staff_id ?? CLINIC,
        notes: event?.notes ?? "",
      });
  }, [open, event, date]);
  const canEdit = !event || manage || event.staff_id === user?.staff_id;
  const done = async (message: string) => {
    await cache.invalidateQueries();
    toast.success(message);
    onClose();
  };
  const save = useMutation({
    mutationFn: () => {
      const title = values.title.trim();
      if (!title) throw new Error("Add a title.");
      if (!values.event_date) throw new Error("Choose a date.");
      const body = {
        title,
        event_date: values.event_date,
        start_time: values.start_time || null,
        notes: values.notes.trim() || null,
        // Other staff add and keep their own events; the server fills them in.
        ...(manage
          ? { staff_id: values.staff_id === CLINIC ? null : values.staff_id }
          : {}),
      };
      return api(
        event ? `events/${encodeURIComponent(event.event_id)}` : "events",
        { method: event ? "PATCH" : "POST", body },
      );
    },
    onSuccess: () => done(event ? "Event updated." : "Event added."),
    onError: (error) => toast.error(error.message),
  });
  const remove = useMutation({
    mutationFn: () =>
      api(`events/${encodeURIComponent(event!.event_id)}`, {
        method: "DELETE",
      }),
    onSuccess: () => done("Event deleted."),
    onError: (error) => toast.error(error.message),
  });
  const busy = save.isPending || remove.isPending;
  const locked = sample || !canEdit;
  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v && !busy) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{event ? "Important date" : "New important date"}</DialogTitle>
          <DialogDescription>
            {sample
              ? "Connect your workspace to add or change events."
              : canEdit
                ? "For the whole clinic or one person. Use synthetic records only."
                : "Only a manager changes events for the whole clinic or for others."}
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="space-y-2">
            <label htmlFor="event-title" className="text-sm font-medium">
              Title <span className="text-muted-foreground">*</span>
            </label>
            <Input
              id="event-title"
              value={values.title}
              disabled={locked}
              maxLength={200}
              onChange={(e) => setValues({ ...values, title: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <label htmlFor="event-date" className="text-sm font-medium">
                Date <span className="text-muted-foreground">*</span>
              </label>
              <Input
                id="event-date"
                type="date"
                value={values.event_date}
                disabled={locked}
                onChange={(e) =>
                  setValues({ ...values, event_date: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="event-time" className="text-sm font-medium">
                Time (optional)
              </label>
              <Input
                id="event-time"
                type="time"
                value={values.start_time}
                disabled={locked}
                onChange={(e) =>
                  setValues({ ...values, start_time: e.target.value })
                }
              />
            </div>
          </div>
          <div className="space-y-2">
            <label htmlFor="event-staff" className="text-sm font-medium">
              For
            </label>
            {manage ? (
              <Select
                disabled={locked}
                value={values.staff_id}
                onValueChange={(v) => setValues({ ...values, staff_id: v })}
              >
                <SelectTrigger id="event-staff" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={CLINIC}>Whole clinic</SelectItem>
                  {options.data?.staff.map((s) => (
                    <SelectItem key={s.staff_id} value={s.staff_id}>
                      {s.staff_id} · {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <p id="event-staff" className="text-sm text-muted-foreground">
                {event && !event.staff_id
                  ? "Whole clinic"
                  : `You (${event?.staff_name ?? user?.name ?? "signed-in staff"})`}
              </p>
            )}
          </div>
          <div className="space-y-2">
            <label htmlFor="event-notes" className="text-sm font-medium">
              Notes
            </label>
            <Textarea
              id="event-notes"
              value={values.notes}
              disabled={locked}
              onChange={(e) => setValues({ ...values, notes: e.target.value })}
            />
          </div>
          <div className="flex items-center justify-between gap-2 border-t pt-4">
            {event && !locked ? (
              <Button
                type="button"
                variant="ghost"
                className="text-destructive"
                disabled={busy}
                onClick={() => remove.mutate()}
              >
                <Trash2 />
                Delete
              </Button>
            ) : (
              <span />
            )}
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={busy}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={locked || busy}>
                {save.isPending && <Loader2 className="animate-spin" />}
                {event ? "Save changes" : "Add event"}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
