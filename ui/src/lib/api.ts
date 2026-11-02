import type { RequestOptions, Params } from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  payload: unknown;
  constructor(
    message: string,
    status: number,
    code = "request_failed",
    payload?: unknown,
  ) {
    super(message);
    this.status = status;
    this.code = code;
    this.payload = payload;
  }
}
function apiUrl(path: string, params: Params = {}) {
  const url = new URL(`/api/${path}`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === "") return;
    if (Array.isArray(value))
      value.forEach((item) => url.searchParams.append(key, item));
    else url.searchParams.set(key, String(value));
  });
  return url;
}
export async function request<T>(
  path: string,
  { method = "GET", params = {}, body, signal }: RequestOptions = {},
): Promise<T> {
  const response = await fetch(apiUrl(path, params), {
    method,
    signal,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "session")
      window.dispatchEvent(new Event("session-expired"));
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((e: { msg: string }) => e.msg).join("; ")
      : detail?.message ||
        (typeof detail === "string"
          ? detail
          : "Unable to reach the clinic workspace. Please try again.");
    throw new ApiError(message, response.status, detail?.code, data);
  }
  return data as T;
}

export async function downloadCsv(resource: string, params: Params) {
  const response = await fetch(apiUrl(`${resource}/export`, params));
  if (!response.ok) {
    if (response.status === 401)
      window.dispatchEvent(new Event("session-expired"));
    const data = await response.json().catch(() => null);
    throw new ApiError(
      data?.detail?.message || "The export failed. Please try again.",
      response.status,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `${resource}-${params.as_of_date || "report"}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
