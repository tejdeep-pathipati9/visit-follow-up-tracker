import { lazy, Suspense, useEffect } from "react";
import { WorkspaceLoading } from "@/components/workspace-state";
import { AppShell } from "@/components/app-shell";
import { navLinks } from "@/components/app-shared";
const DashboardPage = lazy(() =>
  import("@/pages/dashboard").then((module) => ({
    default: module.DashboardPage,
  })),
);
const FollowupsPage = lazy(() =>
  import("@/pages/followups").then((module) => ({
    default: module.FollowupsPage,
  })),
);
const CalendarPage = lazy(() =>
  import("@/pages/calendar").then((module) => ({
    default: module.CalendarPage,
  })),
);
const RecordsPage = lazy(() =>
  import("@/pages/records").then((module) => ({ default: module.RecordsPage })),
);
const AskPage = lazy(() =>
  import("@/pages/ask").then((module) => ({ default: module.AskPage })),
);
const ReportsPage = lazy(() =>
  import("@/pages/reports").then((module) => ({ default: module.ReportsPage })),
);
const SettingsPage = lazy(() =>
  import("@/pages/settings").then((module) => ({
    default: module.SettingsPage,
  })),
);
const ImportPage = lazy(() =>
  import("@/pages/import").then((module) => ({ default: module.ImportPage })),
);
import { useRoute } from "@/lib/router";
import { useWorkspace } from "@/lib/workspace";
export default function App() {
  const { page } = useRoute();
  const { sample } = useWorkspace();
  useEffect(() => {
    document.title = `${navLinks.find((i) => i.path === `#/${page}`)?.title || "Dashboard"} · Visit Follow-Up Tracker`;
  }, [page]);
  const content =
    page === "followups" ? (
      <FollowupsPage />
    ) : page === "calendar" ? (
      <CalendarPage />
    ) : page === "patients" ||
      page === "staff" ||
      page === "visits" ||
      page === "episodes" ? (
      <RecordsPage key={page} resource={page} />
    ) : page === "ask" ? (
      <AskPage />
    ) : page === "reports" ? (
      <ReportsPage />
    ) : page === "import" ? (
      <ImportPage />
    ) : page === "settings" ? (
      <SettingsPage />
    ) : (
      <DashboardPage />
    );
  return (
    <>
      <a
        href="#main-content"
        onClick={(event) => {
          event.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
        className="sr-only fixed top-2 left-2 z-[100] rounded-md bg-background p-3 focus:not-sr-only"
      >
        Skip to content
      </a>
      <AppShell pathname={`#/${page === "dashboard" ? "overview" : page}`}>
        {sample && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-md border border-dashed bg-background/60 px-3 py-2 text-xs text-muted-foreground">
            <span>
              <span className="mr-2 inline-block size-1.5 rounded-full bg-amber-500" />
              Sample workspace · Synthetic records. Changes reset on reload.
            </span>
            <span className="font-mono">PREVIEW</span>
          </div>
        )}
        <Suspense fallback={<WorkspaceLoading />}>{content}</Suspense>
        <footer className="mt-8 flex justify-between gap-3 border-t pt-4 text-[11px] text-muted-foreground">
          <span>Visit Follow-Up Tracker</span>
          <span>Synthetic data only</span>
        </footer>
      </AppShell>
    </>
  );
}
