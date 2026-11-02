import { useSyncExternalStore } from "react";
const subscribe = (callback: () => void) => {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
};
export function useRoute() {
  const hash = useSyncExternalStore(
    subscribe,
    () => location.hash,
    () => "#/overview",
  );
  const [path, query] = (hash.replace(/^#\/?/, "") || "overview").split("?");
  return {
    page: path === "events" ? "followups" : path,
    params: new URLSearchParams(query),
    path: `#/${path}`,
  };
}
export function navigate(page: string, params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  location.hash = `/${page}${query ? "?" + query : ""}`;
}
