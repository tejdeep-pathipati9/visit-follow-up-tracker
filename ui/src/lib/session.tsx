import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowRight, Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { request } from "./api";
import { useWorkspace } from "./workspace";
import type { Followup } from "./types";
import { navigate } from "./router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";

export interface SessionUser {
  staff_id: string;
  name: string;
  role: string;
  email: string;
  is_manager: boolean;
}
const Context = createContext<{
  user: SessionUser | null;
  logout: () => Promise<void>;
}>({ user: null, logout: async () => {} });
export const useSession = () => useContext(Context);

export function SessionProvider({ children }: { children: ReactNode }) {
  const { sample, setSample } = useWorkspace();
  const cache = useQueryClient();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [checked, setChecked] = useState(false);
  const [pending, setPending] = useState(false);
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (sample) return;
    const controller = new AbortController();
    setChecked(false);
    request<SessionUser>("session", { signal: controller.signal })
      .then((next) => {
        if (!controller.signal.aborted) setUser(next);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) {
          setUser(null);
          if (failure.status !== 401) setError(failure.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setChecked(true);
      });
    return () => controller.abort();
  }, [sample]);
  useEffect(() => {
    const expired = () => {
      setUser(null);
      setChecked(true);
      setError("Your session ended. Sign in again to continue.");
      cache.clear();
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, [cache]);
  async function login() {
    setPending(true);
    setError("");
    try {
      const next = await request<SessionUser>("session", {
        method: "POST",
        body: { email: email.trim() },
      });
      await cache.cancelQueries();
      cache.clear();
      setUser(next);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setPending(false);
    }
  }
  async function logout() {
    try {
      await request("session", { method: "DELETE" });
      await cache.cancelQueries();
      cache.clear();
      setUser(null);
      setError("");
    } catch (failure) {
      toast.error((failure as Error).message);
    }
  }
  if (sample || (checked && user))
    return (
      <Context.Provider value={{ user: sample ? null : user, logout }}>
        {children}
      </Context.Provider>
    );
  return (
    <main className="flex min-h-dvh items-center justify-center bg-muted/40 p-6">
      <Card className="w-full max-w-lg shadow-sm">
        <CardHeader className="space-y-3 p-7 pb-4">
          <div className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Activity className="size-5" />
          </div>
          <div>
            <CardTitle className="text-xl tracking-tight">
              Visit Follow-Up Tracker
            </CardTitle>
            <CardDescription className="mt-2">
              Sign in with your staff email to enter your clinic workspace.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 px-7 pb-7">
          {!checked ? (
            <p
              role="status"
              className="flex items-center gap-2 text-sm text-muted-foreground"
            >
              <Loader2 className="size-4 animate-spin" />
              Checking your session…
            </p>
          ) : (
            <form
              className="space-y-4"
              onSubmit={(event) => {
                event.preventDefault();
                void login();
              }}
            >
              <div className="space-y-2">
                <label htmlFor="staff-email" className="text-sm font-medium">
                  Staff email
                </label>
                <Input
                  id="staff-email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@clinic.example"
                  disabled={pending}
                />
              </div>
              <Button type="submit" className="w-full" disabled={pending}>
                {pending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <ArrowRight className="size-4" />
                )}
                Sign in
              </Button>
            </form>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <Button
            variant="outline"
            className="w-full"
            disabled={pending}
            onClick={() => {
              setSample(true);
              navigate("overview");
            }}
          >
            View sample dashboard
            <ArrowRight className="size-4" />
          </Button>
          <p className="flex items-start gap-2 border-t pt-4 text-xs leading-relaxed text-muted-foreground">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
            Internal demo · email-only sign-in. Use synthetic records only.
          </p>
        </CardContent>
      </Card>
    </main>
  );
}

export function useRecordPermissions() {
  const { user } = useSession();
  const { sample } = useWorkspace();
  const manage = sample || Boolean(user?.is_manager);
  return {
    manage,
    user,
    canEditFollowup: (record: Followup) =>
      manage || record.assigned_staff_id === user?.staff_id,
  };
}
