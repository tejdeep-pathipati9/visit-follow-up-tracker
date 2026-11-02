import { Check, Circle, Clock3, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Attention, FollowupStatus } from "@/lib/types";
export function StatusBadge({ status }: { status: FollowupStatus }) {
  return (
    <Badge
      variant="outline"
      className={
        status === "done"
          ? "gap-1 border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
          : "gap-1 bg-background font-normal text-muted-foreground"
      }
    >
      {status === "done" ? (
        <Check className="size-3" />
      ) : (
        <Circle className="size-3" />
      )}
      {status === "done" ? "Done" : status === "closed" ? "Closed" : "Open"}
    </Badge>
  );
}
const styles = {
  overdue: {
    label: "Overdue",
    Icon: TriangleAlert,
    className:
      "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-300",
  },
  due_soon: {
    label: "Due soon",
    Icon: Clock3,
    className:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300",
  },
  unassigned: {
    label: "No scheduled date",
    Icon: Clock3,
    className: "border-border bg-muted/50 text-muted-foreground",
  },
};
export function AttentionBadge({ flag }: { flag: Attention }) {
  const { label, Icon, className } = styles[flag];
  return (
    <Badge variant="outline" className={`gap-1 font-normal ${className}`}>
      <Icon className="size-3" />
      {label}
    </Badge>
  );
}
