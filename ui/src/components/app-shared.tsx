import type { ReactNode } from "react";
import {
  LayoutDashboard,
  ClipboardList,
  Users,
  ChartNoAxesCombined,
  Sparkles,
  CalendarDays,
  CalendarRange,
  FolderHeart,
  Stethoscope,
  Settings,
  FileUp,
} from "lucide-react";
export type SidebarNavItem = { title: string; path: string; icon: ReactNode };
export const navGroups = [
  {
    label: "Workspace",
    items: [
      { title: "Dashboard", path: "#/overview", icon: <LayoutDashboard /> },
      { title: "Follow-ups", path: "#/followups", icon: <ClipboardList /> },
      { title: "Calendar", path: "#/calendar", icon: <CalendarRange /> },
      { title: "Patients", path: "#/patients", icon: <Users /> },
      { title: "Reports", path: "#/reports", icon: <ChartNoAxesCombined /> },
      { title: "AI Search", path: "#/ask", icon: <Sparkles /> },
    ],
  },
  {
    label: "Clinic records",
    items: [
      { title: "Visits", path: "#/visits", icon: <CalendarDays /> },
      { title: "Episodes", path: "#/episodes", icon: <FolderHeart /> },
      { title: "Staff", path: "#/staff", icon: <Stethoscope /> },
    ],
  },
  {
    label: "Administration",
    items: [
      { title: "Import data", path: "#/import", icon: <FileUp /> },
      { title: "Settings", path: "#/settings", icon: <Settings /> },
    ],
  },
];
export const navLinks = navGroups.flatMap((group) => group.items);
