import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { WorkspaceProvider } from "@/lib/workspace";
import { SessionProvider } from "@/lib/session";
import { sampleRequest } from "@/lib/sample-data";
import type { FollowupDetail } from "@/lib/types";
import { ImportPage } from "@/pages/import";
import { FollowupDetailPanel } from "@/components/followup-detail";

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
function mount(
  children: ReactNode,
  endpoint: (url: URL, options: RequestInit) => Promise<Response>,
  manager = true,
) {
  history.replaceState(null, "", "/");
  vi.stubGlobal(
    "fetch",
    vi.fn((url: URL, options: RequestInit) =>
      url.pathname === "/api/session"
        ? Promise.resolve(
            reply({
              staff_id: "S003",
              name: "Nurse Ana",
              role: manager ? "manager" : "nurse",
              email: "ana@clinic.test",
              is_manager: manager,
            }),
          )
        : endpoint(url, options),
    ),
  );
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={cache}>
      <WorkspaceProvider>
        <SessionProvider>{children}</SessionProvider>
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Merged backend workflows", () => {
  it("shows every import rejection and confirms that nothing was saved", async () => {
    const endpoint = vi.fn(async (url: URL, options: RequestInit) => {
      expect(url.pathname).toBe("/api/import");
      expect(options.method).toBe("POST");
      expect(JSON.parse(options.body as string)).toEqual({ visits: [] });
      return reply(
        {
          saved: false,
          counts: {},
          rejections: [
            {
              kind: "visit",
              record_id: "V001",
              reason: "Unknown staff member",
            },
            {
              kind: "followup",
              record_id: "F001",
              reason: "Invalid scheduled date",
            },
          ],
        },
        422,
      );
    });
    const user = mount(<ImportPage />, endpoint);
    const file = new File(['{"visits":[]}'], "clinic.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", { value: async () => '{"visits":[]}' });
    await user.upload(
      await screen.findByLabelText("Synthetic data file"),
      file,
    );
    // jsdom does not reflect the simulated FileList in native form validity.
    expect(
      (screen.getByLabelText("Synthetic data file") as HTMLInputElement).files,
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Validate and import" }),
    ).toBeEnabled();
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Validate and import" })
        .closest("form")!,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nothing was saved",
    );
    expect(screen.getByText("Unknown staff member")).toBeInTheDocument();
    expect(screen.getByText("Invalid scheduled date")).toBeInTheDocument();
    expect(endpoint).toHaveBeenCalledTimes(1);
  });

  it("rejects unreadable JSON before making an import request", async () => {
    const endpoint = vi.fn();
    const user = mount(<ImportPage />, endpoint);
    const file = new File(["invalid"], "invalid.json", {
      type: "application/json",
    });
    Object.defineProperty(file, "text", { value: async () => "invalid" });
    await user.upload(
      await screen.findByLabelText("Synthetic data file"),
      file,
    );
    // jsdom does not reflect the simulated FileList in native form validity.
    expect(
      (screen.getByLabelText("Synthetic data file") as HTMLInputElement).files,
    ).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Validate and import" }),
    ).toBeEnabled();
    fireEvent.submit(
      screen
        .getByRole("button", { name: "Validate and import" })
        .closest("form")!,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Choose a valid JSON",
    );
    expect(endpoint).not.toHaveBeenCalled();
  });

  it("disables import for staff who are not managers", async () => {
    const endpoint = vi.fn();
    mount(<ImportPage />, endpoint, false);
    expect(
      await screen.findByText("Only a manager can import records."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Synthetic data file")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Validate and import" }),
    ).toBeDisabled();
    expect(endpoint).not.toHaveBeenCalled();
  });

  it("renders field-level status and scheduling history with the recorded actor and note", async () => {
    const detail = await sampleRequest<FollowupDetail>("followups/F003");
    detail.history = [
      {
        change_id: 1,
        field: "status",
        old_value: "open",
        new_value: "done",
        changed_at: "2026-10-30T10:00:00Z",
        changed_by: "S003",
        changed_by_name: "Nurse Ana",
        note: "Patient reached; results received.",
      },
      {
        change_id: 2,
        field: "due_date",
        old_value: null,
        new_value: "2026-10-31",
        changed_at: "2026-10-30T11:00:00Z",
        changed_by: "S003",
        changed_by_name: "Nurse Ana",
        note: null,
      },
    ];
    mount(<FollowupDetailPanel id="F003" onClose={vi.fn()} />, async () =>
      reply(detail),
    );
    expect(await screen.findByText("Open → Done")).toBeInTheDocument();
    expect(screen.getByText("Scheduled date")).toBeInTheDocument();
    expect(
      screen.getByText("Patient reached; results received."),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Nurse Ana/).length).toBeGreaterThan(0);
  });
});
