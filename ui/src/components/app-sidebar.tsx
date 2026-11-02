"use client";

import { cn } from "@/lib/utils";
import { CirclePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { AppSearch } from "@/components/app-search";
import { navGroups } from "@/components/app-shared";
import { CustomTrigger } from "@/components/custom-trigger";
import { LatestChange } from "@/components/latest-change";
import { ThemeSwitcher } from "@/components/theme-switcher";
import { SettingsIcon } from "lucide-react";
import { useRecordPermissions } from "@/lib/session";

export function AppSidebar({ pathname }: { pathname?: string }) {
  const { manage } = useRecordPermissions();
  return (
    <Sidebar
      className={cn(
        "*:data-[slot=sidebar-inner]:bg-background",
        "transition-[left,right,top,width] group-data-[collapsible=offcanvas]:top-[calc(var(--app-header-height)*0.5)]",
      )}
      collapsible="offcanvas"
      variant="sidebar"
    >
      <SidebarHeader className="h-(--app-header-height,3rem) flex-row items-center justify-between">
        <Button asChild variant="ghost">
          <a href="#/overview">
            <CirclePlus className="size-5" />
            <span className="font-medium">Visit Tracker</span>
          </a>
        </Button>
        <CustomTrigger place="sidebar" />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <AppSearch />
        </SidebarGroup>
        {navGroups.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel className="group-data-[collapsible=icon]:pointer-events-none">
              {group.label}
            </SidebarGroupLabel>
            <SidebarMenu>
              {group.items
                .filter((item) => manage || item.path !== "#/import")
                .map((item) => (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton
                      asChild
                      isActive={item.path === pathname}
                      tooltip={item.title}
                    >
                      <a href={item.path}>
                        {item.icon}
                        <span>{item.title}</span>
                      </a>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="px-4">
        <LatestChange />
        <div className="flex items-center pt-4 pb-2">
          <ThemeSwitcher />
          <Button
            asChild
            className="text-muted-foreground"
            size="icon-sm"
            variant="ghost"
          >
            <a aria-label="Settings" href="#/settings">
              <SettingsIcon />
            </a>
          </Button>
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
