import { cn } from "@/lib/utils";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppHeader } from "@/components/app-header";
import { ClinicAgent } from "@/components/clinic-agent";
import { AppSidebar } from "@/components/app-sidebar";

export function AppShell({
  children,
  pathname = "#/overview",
}: {
  children: React.ReactNode;
  pathname?: string;
}) {
  return (
    <SidebarProvider
      className={cn(
        "[--app-wrapper-max-width:80rem]",
        "[--app-header-height:3rem]",
      )}
    >
      <AppSidebar pathname={pathname} />
      <SidebarInset className="bg-muted dark:bg-background">
        <AppHeader pathname={pathname} />
        <div
          id="main-content"
          tabIndex={-1}
          className={cn(
            "flex flex-1 flex-col p-4 pb-20 md:p-6 md:pb-24",
            "mx-auto w-full max-w-(--app-wrapper-max-width)",
          )}
        >
          {children}
        </div>
      </SidebarInset>
      <ClinicAgent />
    </SidebarProvider>
  );
}
