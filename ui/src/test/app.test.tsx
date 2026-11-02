import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "next-themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceProvider } from "@/lib/workspace";
import { TooltipProvider } from "@/components/ui/tooltip";
import App from "@/App";

describe("Application shell", () => {
  it("renders the clinic dashboard, navigates to the worklist, and keeps live errors separate from sample data", async () => {
    window.history.replaceState(null, "", "/?demo=1#/overview");
    const cache = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    render(
      <ThemeProvider attribute="class" defaultTheme="light">
        <QueryClientProvider client={cache}>
          <WorkspaceProvider>
            <TooltipProvider>
              <App />
            </TooltipProvider>
          </WorkspaceProvider>
        </QueryClientProvider>
      </ThemeProvider>,
    );
    const user = userEvent.setup();
    expect(
      await screen.findByRole("heading", { name: "Clinic overview" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Priority follow-ups")).toBeInTheDocument();
    expect(screen.getByText("Staff workload")).toBeInTheDocument();
    expect(
      screen.getByText("Scheduled by due date · through the next 7 days"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Follow-ups" }));
    expect(
      await screen.findByRole("heading", { name: "Follow-ups" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /Amelia Brooks/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Skip to content" }));
    expect(screen.getByRole("main")).toContainElement(
      document.activeElement as HTMLElement,
    );
    expect(location.hash).toBe("#/followups");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              detail: {
                code: "database_unavailable",
                message: "Database unavailable for this test.",
              },
            }),
            { status: 503 },
          ),
      ),
    );
    await user.click(screen.getByRole("button", { name: "Sample workspace" }));
    await user.click(
      screen.getByRole("menuitem", { name: "Switch to connected workspace" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "We couldn’t load your workspace",
      }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /Amelia Brooks/ }),
      ).not.toBeInTheDocument(),
    );
    expect(location.search).not.toContain("demo=1");
    vi.unstubAllGlobals();
  });
});
