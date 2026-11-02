import { beforeEach, describe, expect, it } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WorkspaceProvider } from "@/lib/workspace";
import { FollowupsPage } from "@/pages/followups";
import { TooltipProvider } from "@/components/ui/tooltip";
function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <WorkspaceProvider>
        <TooltipProvider>
          <FollowupsPage />
        </TooltipProvider>
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
beforeEach(() => {
  window.history.replaceState(null, "", "/?demo=1#/followups");
});
describe("Follow-up worklist", () => {
  it("searches patients and shows a recoverable empty state", async () => {
    const user = setup();
    await screen.findByRole("button", { name: /Amelia Brooks/ });
    await user.type(
      screen.getByRole("textbox", { name: "Search follow-ups" }),
      "Sofia",
    );
    await screen.findByText("1–1 of 1 follow-ups");
    expect(
      screen.getByRole("button", { name: /Sofia Martinez/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Amelia Brooks/ }),
    ).not.toBeInTheDocument();
    await user.clear(
      screen.getByRole("textbox", { name: "Search follow-ups" }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Search follow-ups" }),
      "nonexistent patient",
    );
    expect(
      await screen.findByText("No matching follow-ups"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(
      await screen.findByRole("button", { name: /Amelia Brooks/ }),
    ).toBeInTheDocument();
  });
  it("filters by follow-up type using the shadcn select", async () => {
    const user = setup();
    await screen.findByRole("button", { name: /Amelia Brooks/ });
    await user.click(screen.getByRole("combobox", { name: "All types" }));
    await user.click(screen.getByRole("option", { name: "Lab" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: /Oliver Bennett/ }),
      ).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: /Amelia Brooks/ }),
    ).toBeInTheDocument();
    expect(screen.getByText("1–6 of 6 follow-ups")).toBeInTheDocument();
  });
  it("opens accessible record details, completes a follow-up, and refreshes the worklist", async () => {
    const user = setup();
    await user.click(
      await screen.findByRole("button", { name: /Amelia Brooks/ }),
    );
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("heading", { name: "Amelia Brooks" });
    expect(within(dialog).getByText("Visit summary")).toBeInTheDocument();
    await user.click(
      within(dialog).getByRole("button", { name: "Mark follow-up done" }),
    );
    expect(
      await within(dialog).findByRole("button", { name: "Reopen follow-up" }),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByText("Open follow-ups").parentElement,
      ).toHaveTextContent("11"),
    );
    await user.click(
      within(dialog).getByRole("button", { name: "Reopen follow-up" }),
    );
    expect(
      await within(dialog).findByRole("button", {
        name: "Mark follow-up done",
      }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});
