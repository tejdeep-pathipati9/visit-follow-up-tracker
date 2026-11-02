import {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { request } from "./api";
import { sampleRequest } from "./sample-data";
import { localDate } from "./types";
import type { RequestOptions, Params, FollowupStatus } from "./types";

interface Workspace {
  sample: boolean;
  setSample: (v: boolean) => void;
  asOf: string;
  setAsOf: (v: string) => void;
  api: <T>(path: string, options?: RequestOptions) => Promise<T>;
}
const Context = createContext<Workspace | null>(null);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [sample, setMode] = useState(
    new URLSearchParams(location.search).get("demo") === "1",
  );
  const [asOf, setAsOf] = useState(localDate());
  const setSample = useCallback((v: boolean) => {
    const url = new URL(location.href);
    if (v) url.searchParams.set("demo", "1");
    else url.searchParams.delete("demo");
    history.replaceState(null, "", url);
    setMode(v);
  }, []);
  const api = useCallback(
    <T,>(path: string, options: RequestOptions = {}) =>
      (sample ? sampleRequest<T> : request<T>)(path, {
        ...options,
        params: { as_of_date: asOf, ...options.params },
      }),
    [sample, asOf],
  );
  return (
    <Context.Provider value={{ sample, setSample, asOf, setAsOf, api }}>
      {children}
    </Context.Provider>
  );
}
export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error("WorkspaceProvider is required");
  return value;
}
export function useApi<T>(path: string, params: Params = {}, enabled = true) {
  const { sample, asOf, api } = useWorkspace();
  return useQuery({
    queryKey: [sample, asOf, path, params],
    queryFn: ({ signal }) => api<T>(path, { params, signal }),
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}
export function useComplete() {
  const { sample, api } = useWorkspace();
  const cache = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: FollowupStatus }) =>
      api(`followups/${encodeURIComponent(id)}`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: async (_, v) => {
      await cache.invalidateQueries();
      toast.success(
        `${sample ? "Sample: " : ""}Follow-up ${v.status === "done" ? "completed" : "reopened"}.`,
      );
    },
    onError: (error) => toast.error(error.message),
  });
}
