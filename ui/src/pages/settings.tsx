import { useTheme } from "next-themes";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useWorkspace } from "@/lib/workspace";
export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const { sample, setSample, asOf, setAsOf } = useWorkspace();
  return (
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 className="text-lg font-semibold tracking-tight">
          Workspace settings
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Preferences for your clinic workspace.
        </p>
      </div>
      <Card className="dark:bg-transparent">
        <CardHeader>
          <CardTitle>General</CardTitle>
          <CardDescription>
            Personalize your view without changing clinic records.
          </CardDescription>
        </CardHeader>
        <CardContent className="divide-y">
          <div className="flex flex-wrap items-center justify-between gap-4 py-5">
            <label htmlFor="theme" className="text-sm">
              Appearance
              <p className="mt-1 text-xs text-muted-foreground">
                Choose light, dark, or your system’s preference.
              </p>
            </label>
            <Select value={theme || "light"} onValueChange={setTheme}>
              <SelectTrigger id="theme" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="light">Light</SelectItem>
                <SelectItem value="dark">Dark</SelectItem>
                <SelectItem value="system">System</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 py-5">
            <div className="text-sm">
              Data source
              <p className="mt-1 text-xs text-muted-foreground">
                {sample
                  ? "Synthetic sample data. Changes reset on reload."
                  : "Connected SQLite database."}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSample(!sample)}
            >
              {sample ? "Connect workspace" : "Explore sample data"}
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 py-5">
            <label htmlFor="assessment-date" className="text-sm">
              Assessment date
              <p className="mt-1 text-xs text-muted-foreground">
                Evaluate urgency relative to this date.
              </p>
            </label>
            <Input
              id="assessment-date"
              type="date"
              value={asOf}
              onChange={(e) => {
                if (e.target.value) setAsOf(e.target.value);
              }}
              className="w-40"
            />
          </div>
        </CardContent>
      </Card>
      <p className="text-xs text-muted-foreground">
        Synthetic data only. Do not enter real patient records.
      </p>
    </div>
  );
}
