import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import { WorkspaceProvider } from "@/lib/workspace";
import { SessionProvider, useSession } from "@/lib/session";
import { RecordEditor } from "@/components/record-editor";
import { ReportsPage } from "@/pages/reports";
import type { ReactNode } from "react";
import * as session from "@/lib/session";
const manager = {
  staff_id: "M001",
  name: "Manager",
  role: "manager",
  email: "manager@clinic.test",
  is_manager: true,
};
const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
function mount(children: ReactNode) {
  history.replaceState(null, "", "/");
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={cache}>
      <WorkspaceProvider>{children}</WorkspaceProvider>
    </QueryClientProvider>,
  );
  return { cache, user: userEvent.setup() };
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function Identity() {
  const { user, logout } = useSession();
  return (
    <>
      <p>
        {user?.name} · {user?.role}
      </p>
      <button onClick={() => void logout()}>Switch demo account</button>
    </>
  );
}
describe("Confirmed client workflows", () => {
  it("signs in by staff email and clears previous records on login/logout", async () => {
    const account = {
      staff_id: "S001",
      name: "Nurse Ana",
      role: "nurse",
      email: "ana@clinic.test",
      is_manager: false,
    };
    const fetcher = vi
      .fn()
      .mockImplementation(async (url: URL, options: RequestInit) => {
        expect(url.pathname).toBe("/api/session");
        if (options.method === "POST") return reply(account);
        if (options.method === "DELETE")
          return new Response(null, { status: 204 });
        return reply({ detail: "Sign in first" }, 401);
      });
    vi.stubGlobal("fetch", fetcher);
    const { cache, user } = mount(
      <SessionProvider>
        <Identity />
      </SessionProvider>,
    );
    cache.setQueryData(["previous-patients"], ["private"]);
    await user.type(
      await screen.findByRole("textbox", { name: "Staff email" }),
      "ana@clinic.test",
    );
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Nurse Ana · nurse")).toBeInTheDocument();
    expect(cache.getQueryData(["previous-patients"])).toBeUndefined();
    const login = fetcher.mock.calls.find(([, init]) => init.method === "POST");
    expect(JSON.parse(login![1].body)).toEqual({ email: "ana@clinic.test" });
    cache.setQueryData(["nurse-patients"], ["private"]);
    await user.click(
      screen.getByRole("button", { name: "Switch demo account" }),
    );
    expect(
      await screen.findByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
    expect(cache.getQueryData(["nurse-patients"])).toBeUndefined();
    expect(
      fetcher.mock.calls.some(([, init]) => init.method === "DELETE"),
    ).toBe(true);
  });
  it("requires a closure reason and submits Closed without inventing a missing due date", async () => {
    vi.spyOn(session, "useRecordPermissions").mockReturnValue({
      manage: true,
      user: manager,
      canEditFollowup: () => true,
    });
    const fetcher = vi
      .fn()
      .mockImplementation(async (_url, options: RequestInit) =>
        options.method === "PATCH"
          ? reply({ status: "closed" })
          : reply({
              items: [],
              staff: [{ staff_id: "S001", name: "Nurse Ana", role: "nurse" }],
            }),
      );
    vi.stubGlobal("fetch", fetcher);
    const error = vi.spyOn(toast, "error");
    const onClose = vi.fn();
    const { user } = mount(
      <RecordEditor
        resource="followups"
        open
        onClose={onClose}
        record={{
          followup_id: "F001",
          action_type: "lab",
          due_date: null,
          assigned_staff_id: "S001",
          status: "open",
          notes: null,
          completed_at: null,
        }}
        prefill={{ status: "closed", notes: "" }}
      />,
    );
    expect(screen.getByRole("combobox", { name: /^Status/ })).toHaveTextContent(
      "Closed",
    );
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() =>
      expect(error).toHaveBeenCalledWith(
        expect.stringContaining("reason in notes"),
      ),
    );
    expect(
      fetcher.mock.calls.filter(([, init]) => init.method === "PATCH"),
    ).toHaveLength(0);
    await user.type(
      screen.getByRole("textbox", { name: "Follow-up notes / closure reason" }),
      "Duplicate request; replacement is open.",
    );
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const mutation = fetcher.mock.calls.find(
      ([, init]) => init.method === "PATCH",
    );
    expect(JSON.parse(mutation![1].body)).toEqual({
      status: "closed",
      notes: "Duplicate request; replacement is open.",
    });
  });
  it("provides a printable report link and distinguishes Closed and missing due dates in summaries", async () => {
    const totals = {
      followup_count: 3,
      open_followups: 1,
      done_followups: 1,
      closed_followups: 1,
      overdue_followups: 0,
      due_soon_followups: 0,
      due_today_followups: 0,
      unassigned_followups: 1,
      next_due_date: null,
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(async () =>
          reply({ totals, groups: [{ key: "lab", label: "Lab", ...totals }] }),
        ),
    );
    mount(<ReportsPage />);
    const print = await screen.findByRole("link", { name: "Print report" });
    expect(print.getAttribute("href")).toMatch(
      /^\/report\?as_of_date=\d{4}-\d{2}-\d{2}$/,
    );
    expect(
      screen.getAllByRole("columnheader", { name: "Closed" }),
    ).toHaveLength(2);
    expect(
      screen.getAllByRole("columnheader", { name: "No date" }),
    ).toHaveLength(2);
  });
});

it("preserves existing notes when archiving completed work without a new closure reason", async () => {
  vi.spyOn(session, "useRecordPermissions").mockReturnValue({
    manage: true,
    user: manager,
    canEditFollowup: () => true,
  });
  const fetcher = vi
    .fn()
    .mockImplementation(async (_url, options: RequestInit) =>
      options.method === "PATCH"
        ? reply({ status: "closed" })
        : reply({
            items: [],
            staff: [{ staff_id: "S001", name: "Nurse Ana", role: "nurse" }],
          }),
    );
  vi.stubGlobal("fetch", fetcher);
  const onClose = vi.fn();
  const { user } = mount(
    <RecordEditor
      resource="followups"
      open
      onClose={onClose}
      record={{
        followup_id: "F005",
        action_type: "lab",
        due_date: null,
        assigned_staff_id: "S001",
        status: "done",
        notes: "Results received and reviewed.",
        completed_at: "2026-10-20T12:00:00Z",
      }}
      prefill={{ status: "closed" }}
    />,
  );
  expect(
    screen.getByRole("textbox", { name: "Follow-up notes / closure reason" }),
  ).toHaveValue("Results received and reviewed.");
  await user.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  const mutation = fetcher.mock.calls.find(
    ([, init]) => init.method === "PATCH",
  );
  expect(JSON.parse(mutation![1].body)).toEqual({ status: "closed" });
});
