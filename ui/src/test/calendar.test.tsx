import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceProvider } from "@/lib/workspace";
import { SessionProvider } from "@/lib/session";
import { addDays, formatDate, localDate } from "@/lib/types";
import { CalendarPage } from "@/pages/calendar";

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
const page = (items: unknown[] = []) => ({
  items,
  total: items.length,
  offset: 0,
  limit: 1000,
  as_of_date: localDate(),
});
function mount(
  path: string,
  endpoint?: (url: URL, options: RequestInit) => Promise<Response>,
  manager = true,
) {
  history.replaceState(null, "", path);
  if (endpoint)
    vi.stubGlobal(
      "fetch",
      vi.fn((url: URL, options: RequestInit) =>
        url.pathname === "/api/session"
          ? Promise.resolve(
              reply({
                staff_id: "S002",
                name: "Nurse Birch Sample",
                role: manager ? "manager" : "nurse",
                email: "birch@clinic.test",
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
        <SessionProvider>
          <CalendarPage />
        </SessionProvider>
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
// A connected workspace with no follow-ups; events and created events are recorded.
function workspace(events: unknown[] = [], followups: unknown[] = []) {
  const posted: { method?: string; body: unknown }[] = [];
  const endpoint = vi.fn(async (url: URL, options: RequestInit) => {
    if (url.pathname === "/api/events" && options.method === "POST") {
      posted.push({ method: options.method, body: JSON.parse(options.body as string) });
      return reply({ event_id: "C001" }, 201);
    }
    if (url.pathname === "/api/events") return reply(events);
    if (url.pathname === "/api/options")
      return reply({
        staff: [{ staff_id: "S001", name: "Dr. Alder Example", role: "doctor" }],
        action_types: ["lab", "referral", "recheck"],
        followup_statuses: ["open", "done", "closed"],
        due_soon_days_by_action: { lab: 3, referral: 14, recheck: 14 },
      });
    if (url.pathname === "/api/followups")
      return reply(page(url.searchParams.get("preset") ? [] : followups));
    throw new Error(`unexpected ${url.pathname}`);
  });
  return { endpoint, posted };
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Calendar", () => {
  it("shows the sample month, today's important dates, and follow-ups without a date", async () => {
    const user = mount("/?demo=1#/calendar");
    expect(
      await screen.findByRole("heading", { name: "Calendar" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Team huddle").length).toBeGreaterThan(0);
    const waiting = screen
      .getByText("No scheduled date")
      .closest("[data-slot=card]") as HTMLElement;
    expect(within(waiting).getByText("Sofia Martinez")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New event" }));
    expect(
      await screen.findByText("Connect your workspace to add or change events."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add event" })).toBeDisabled();
  });

  it("puts events and follow-ups on their day", async () => {
    const day = addDays(localDate(), 1);
    const { endpoint } = workspace(
      [
        {
          event_id: "C001",
          title: "Clinic closed",
          event_date: day,
          start_time: null,
          staff_id: null,
          staff_name: null,
          notes: null,
          created_by: "S005",
          created_by_name: "Manager",
        },
      ],
      [
        {
          followup_id: "F009",
          patient_name: "Emery Testwell",
          action_type: "lab",
          due_date: day,
          status: "open",
          flags: ["due_soon"],
          assigned_staff_id: "S002",
          assigned_staff_name: "Nurse Birch Sample",
        },
      ],
    );
    const user = mount("/#/calendar", endpoint);
    await user.click(
      await screen.findByRole("button", {
        name: `${formatDate(day)}: 1 follow-ups, 1 events`,
      }),
    );
    expect(
      screen.getByText(formatDate(day), { selector: "[data-slot=card-title]" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Clinic closed").length).toBe(2); // the month and the day
    expect(screen.getByText("Emery Testwell")).toBeInTheDocument();
  });

  it("adds an event for the whole clinic as a manager", async () => {
    const { endpoint, posted } = workspace();
    const user = mount("/#/calendar", endpoint);
    await user.click(await screen.findByRole("button", { name: "New event" }));
    await user.type(screen.getByLabelText(/Title/), "Team meeting");
    await user.type(screen.getByLabelText("Time (optional)"), "09:30");
    await user.click(screen.getByRole("button", { name: "Add event" }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].body).toEqual({
      title: "Team meeting",
      event_date: localDate(),
      start_time: "09:30",
      notes: null,
      staff_id: null,
    });
  });

  it("adds a nurse's event for herself", async () => {
    const { endpoint, posted } = workspace();
    const user = mount("/#/calendar", endpoint, false);
    await user.click(await screen.findByRole("button", { name: "New event" }));
    expect(screen.getByText("You (Nurse Birch Sample)")).toBeInTheDocument();
    expect(screen.getByText("For you. Use synthetic records only.")).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Title/), "Call the lab");
    await user.click(screen.getByRole("button", { name: "Add event" }));
    await vi.waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0].body).toEqual({
      title: "Call the lab",
      event_date: localDate(),
      start_time: null,
      notes: null,
    });
  });

  it("schedules a follow-up by dragging it from No scheduled date onto a day", async () => {
    const day = addDays(localDate(), 3);
    const patched: unknown[] = [];
    const waiting = {
      followup_id: "F070",
      patient_name: "Harper Dummerfield",
      action_type: "referral",
      due_date: null,
      status: "open",
      flags: ["unassigned"],
      assigned_staff_id: "S002",
      assigned_staff_name: "Nurse Birch Sample",
    };
    const endpoint = vi.fn(async (url: URL, options: RequestInit) => {
      if (options.method === "PATCH") {
        patched.push([url.pathname, JSON.parse(options.body as string)]);
        return reply({});
      }
      if (url.pathname === "/api/events") return reply([]);
      return reply(page(url.searchParams.get("preset") === "unassigned" ? [waiting] : []));
    });
    mount("/#/calendar", endpoint, false); // the nurse, who is assigned F070
    const card = await screen.findByRole("button", { name: /Harper Dummerfield/ });
    expect(card).toHaveAttribute("draggable", "true");
    const data = new Map<string, string>();
    const dataTransfer = {
      setData: (key: string, value: string) => data.set(key, value),
      getData: (key: string) => data.get(key) ?? "",
      effectAllowed: "",
    };
    fireEvent.dragStart(card, { dataTransfer });
    const cell = document.querySelector(`[data-date="${day}"]`)!;
    fireEvent.dragOver(cell, { dataTransfer });
    fireEvent.drop(cell, { dataTransfer });
    await vi.waitFor(() =>
      expect(patched).toEqual([["/api/followups/F070", { due_date: day }]]),
    );
  });
});
