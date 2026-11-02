import { SettingsIcon, CircleHelpIcon, UserIcon, LogOut } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { navigate } from "@/lib/router";
import { useSession } from "@/lib/session";
import { initials, titleCase } from "@/lib/types";
export function NavUser() {
  const { user, logout } = useSession();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="size-8 rounded-full p-0"
          aria-label="Account menu"
        >
          <Avatar className="size-8">
            <AvatarFallback className="bg-muted text-xs">
              {user ? initials(user.name) : "OM"}
            </AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex items-center gap-2">
          <Avatar className="size-8">
            <AvatarFallback>{user ? initials(user.name) : "OM"}</AvatarFallback>
          </Avatar>
          <div>
            {user?.name || "Office manager"}
            <p className="text-xs font-normal text-muted-foreground">
              {user
                ? `${user.email} · ${titleCase(user.role)}`
                : "Clinic workspace"}
            </p>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem onSelect={() => navigate("settings")}>
            <SettingsIcon />
            Preferences
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => navigate("staff")}>
            <UserIcon />
            Clinic team
          </DropdownMenuItem>
          <DropdownMenuItem asChild>
            <a href="/docs" target="_blank" rel="noreferrer">
              <CircleHelpIcon />
              API documentation
            </a>
          </DropdownMenuItem>
          {user && (
            <DropdownMenuItem onSelect={() => void logout()}>
              <LogOut /> Sign out
            </DropdownMenuItem>
          )}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
