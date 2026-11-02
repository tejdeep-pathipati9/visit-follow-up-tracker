import { BellIcon, CircleHelpIcon, Database, FlaskConical } from "lucide-react";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { navLinks } from "@/components/app-shared";
import { CustomTrigger } from "@/components/custom-trigger";
import { NavUser } from "@/components/nav-user";
import { useApi, useWorkspace } from "@/lib/workspace";
import { navigate } from "@/lib/router";
import type { Summary } from "@/lib/types";
export function AppHeader({ pathname }: { pathname?: string }) {
  const item = navLinks.find((i) => i.path === pathname);
  const { sample, setSample } = useWorkspace();
  const { data } = useApi<Summary>("dashboard");
  return (
    <header className="sticky top-0 z-40 flex h-(--app-header-height) w-full shrink-0 items-center justify-between gap-2 border-b bg-background px-4 md:px-6">
      <div className="flex items-center gap-3">
        <CustomTrigger place="navbar" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              size="sm"
              variant="ghost"
              className="gap-1.5 text-xs text-muted-foreground"
            >
              {sample ? (
                <FlaskConical className="size-3.5" />
              ) : (
                <Database className="size-3.5" />
              )}
              <span className="hidden sm:inline">
                {sample ? "Sample workspace" : "Clinic workspace"}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-64">
            <DropdownMenuLabel>Data source</DropdownMenuLabel>
            <p className="px-2 pb-2 text-xs leading-relaxed text-muted-foreground">
              {sample
                ? "In-memory synthetic preview. Changes reset on reload."
                : "Connected to your clinic’s SQLite database."}
            </p>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => setSample(!sample)}>
              {sample
                ? "Switch to connected workspace"
                : "Explore sample workspace"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbPage className="text-sm">
              {item?.title || "Dashboard"}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
      <div className="flex items-center gap-2 sm:gap-3">
        <Button size="icon-sm" variant="outline" asChild>
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            aria-label="API documentation"
          >
            <CircleHelpIcon />
          </a>
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              aria-label="Notifications"
              size="icon-sm"
              variant="outline"
              className="relative"
            >
              <BellIcon />
              {Boolean(data?.followups.overdue_followups) && (
                <span className="absolute -top-0.5 -right-0.5 size-1.5 rounded-full bg-amber-500" />
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72">
            <DropdownMenuLabel>Needs your attention</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onSelect={() => navigate("followups", { preset: "overdue" })}
            >
              {data?.followups.overdue_followups ?? "—"} overdue follow-ups
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => navigate("followups", { preset: "unassigned" })}
            >
              {data?.followups.unassigned_followups ?? "—"} follow-ups need a
              scheduled date
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <Separator
          orientation="vertical"
          className="h-4 data-[orientation=vertical]:self-center"
        />
        <NavUser />
      </div>
    </header>
  );
}
