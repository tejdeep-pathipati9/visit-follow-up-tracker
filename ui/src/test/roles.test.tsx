import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { WorkspaceProvider } from "@/lib/workspace";
import { SessionProvider } from "@/lib/session";
import { sampleRequest } from "@/lib/sample-data";
import { DashboardPage } from "@/pages/dashboard";
import { RecordsPage } from "@/pages/records";

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
// A connected workspace answered from the sample data, signed in as a manager or a nurse.
function mount(children: ReactNode, path: string, manager: boolean) {
  history.replaceState(null, "", path);
  const requests: URL[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: URL) => {
      requests.push(url);
      if (url.pathname === "/api/session")
        return reply({
          staff_id: "S003",
          name: "Nurse Ana Rivera",
          role: manager ? "manager" : "nurse",
          email: "ana@clinic.test",
          is_manager: manager,
        });
      const params: Record<string, string | string[]> = {};
      for (const key of new Set(url.searchParams.keys())) {
        const values = url.searchParams.getAll(key);
        params[key] = values.length > 1 ? values : values[0];
      }
      return reply(await sampleRequest(url.pathname.replace("/api/", ""), { params }));
    }),
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
  return { user: userEvent.setup(), requests };
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Manager and staff views", () => {
  it("shows a nurse her own workload, not the team's", async () => {
    mount(<DashboardPage />, "/#/overview", false);
    expect(await screen.findByText("My workload")).toBeInTheDocument();
    expect(screen.getByText(/^Your follow-ups and what needs attention/)).toBeInTheDocument();
    expect(screen.queryByText("Most overdue")).not.toBeInTheDocument();
    expect(screen.queryByText("Staff with overdue work")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /View my workload/ })).toBeInTheDocument();
  });

  it("shows a manager the team and opens overdue patients as a filtered list", async () => {
    const { user } = mount(<DashboardPage />, "/#/overview", true);
    expect(await screen.findByText("Team and workload")).toBeInTheDocument();
    expect(screen.getByText("Most overdue")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Patients with overdue follow-ups/ }));
    expect(location.hash).toBe("#/patients?flag=overdue");
  });

  it("lists only patients with overdue follow-ups when the address asks for it", async () => {
    const { user, requests } = mount(
      <RecordsPage resource="patients" />,
      "/#/patients?flag=overdue",
      true,
    );
    const chip = await screen.findByRole("button", {
      name: /Only patients with overdue follow-ups/,
    });
    const patients = requests.filter((url) => url.pathname === "/api/patients");
    expect(patients.at(-1)?.searchParams.get("flag")).toBe("overdue");
    await user.click(chip);
    expect(location.hash).toBe("#/patients");
  });
});
