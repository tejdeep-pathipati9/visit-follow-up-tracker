import { Database, RefreshCw, SearchX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspace } from "@/lib/workspace";
export function WorkspaceError({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  const { sample, setSample } = useWorkspace();
  return (
    <Card>
      <CardContent className="flex min-h-72 flex-col items-center justify-center gap-4 py-12 text-center">
        <div className="rounded-xl border p-3">
          <Database className="size-6 text-muted-foreground" />
        </div>
        <div className="max-w-lg space-y-2">
          <h2 className="font-medium">We couldn’t load your workspace</h2>
          <p className="text-sm text-muted-foreground">{error.message}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={retry}>
            <RefreshCw />
            Try again
          </Button>
          {!sample && (
            <Button onClick={() => setSample(true)}>
              Explore sample workspace
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
export function WorkspaceLoading() {
  return (
    <div
      className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4"
      aria-label="Loading workspace"
      role="status"
    >
      <Skeleton className="h-80 md:col-span-2 lg:col-span-3" />
      <Skeleton className="h-80" />
      <Skeleton className="h-72 md:col-span-2" />
      <Skeleton className="h-72 md:col-span-2" />
      <span className="sr-only">Loading workspace…</span>
    </div>
  );
}
export function EmptyState({
  title = "No matching follow-ups",
  description = "Try a different search or reset your filters.",
  action,
}: {
  title?: string;
  description?: string;
  action?: () => void;
}) {
  return (
    <div className="flex min-h-64 flex-col items-center justify-center gap-3 px-6 text-center">
      <div className="mb-1 rounded-xl border p-3">
        <SearchX className="size-5 text-muted-foreground" />
      </div>
      <h3 className="text-sm font-medium">{title}</h3>
      <p className="max-w-sm text-sm text-muted-foreground">{description}</p>
      {action && (
        <Button variant="outline" size="sm" onClick={action}>
          Reset filters
        </Button>
      )}
    </div>
  );
}
