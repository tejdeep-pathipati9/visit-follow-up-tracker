import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ClinicAgent } from "@/components/clinic-agent";
import { SessionProvider } from "@/lib/session";
import { WorkspaceProvider, useWorkspace } from "@/lib/workspace";
import { sampleRequest } from "@/lib/sample-data";
import type { Followup, Page } from "@/lib/types";
const answer = {
  explanation: "One overdue laboratory follow-up needs attention.",
  sql: "SELECT patient_name FROM permitted_followups",
  result: {
    columns: ["Patient"],
    rows: [["Iris Example"]],
    row_count: 1,
    truncated: false,
  },
};
function Status() {
  const { sample, setAsOf } = useWorkspace();
  return (
    <>
      <p>
        {sample
          ? "Synthetic dashboard selected"
          : "Connected workspace selected"}
      </p>
      <button onClick={() => setAsOf("2030-01-01")}>
        Change assessment date
      </button>
    </>
  );
}
function setup({ sample = false, login = false } = {}) {
  history.replaceState(null, "", sample ? "/?demo=1#/overview" : "/#/overview");
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={cache}>
      <WorkspaceProvider>
        {login ? (
          <SessionProvider>
            <Status />
          </SessionProvider>
        ) : (
          <>
            <ClinicAgent />
            <Status />
          </>
        )}
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
  return userEvent.setup();
}
afterEach(() => vi.unstubAllGlobals());
describe("Floating clinic agent", () => {
  it("opens with keyboard focus, expands, minimizes with its draft intact, and closes with Escape", async () => {
    const user = setup();
    const launcher = screen.getByRole("button", { name: "Open clinic agent" });
    await user.click(launcher);
    expect(
      screen.getByRole("dialog", { name: "New chat" }),
    ).toBeInTheDocument();
    const input = screen.getByRole("textbox", { name: "Ask clinic agent" });
    expect(input).toHaveFocus();
    await user.type(input, "Check the overdue labs");
    await user.click(screen.getByRole("button", { name: "Expand agent" }));
    expect(
      screen.getByRole("button", { name: "Restore agent size" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Minimize agent" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(launcher).toHaveFocus();
    await user.click(launcher);
    expect(
      screen.getByRole("textbox", { name: "Ask clinic agent" }),
    ).toHaveValue("Check the overdue labs");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(launcher).toHaveFocus();
  });
  it("submits to the existing read-only API and keeps results after minimizing", async () => {
    const fetcher = vi
      .fn()
      .mockImplementation(
        async () => new Response(JSON.stringify(answer), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetcher);
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    await user.type(
      screen.getByRole("textbox", { name: "Ask clinic agent" }),
      "Which labs are overdue?{Enter}",
    );
    expect(await screen.findByText("Iris Example")).toBeInTheDocument();
    expect(screen.getByText(answer.explanation)).toBeInTheDocument();
    expect(screen.getByText("1 result")).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, options] = fetcher.mock.calls[0];
    expect(url.pathname).toBe("/api/ask");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      question: "Which labs are overdue?",
      as_of_date: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
    });
    await user.click(screen.getByRole("button", { name: "Minimize agent" }));
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    expect(screen.getByText("Iris Example")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(screen.queryByText("Iris Example")).not.toBeInTheDocument();
    expect(
      screen.getByRole("textbox", { name: "Ask clinic agent" }),
    ).toHaveFocus();
  });
  it("cancels a pending question on new chat and ignores its late response", async () => {
    let resolve!: (response: Response) => void;
    let signal!: AbortSignal;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url, options) => {
        signal = options.signal;
        return new Promise<Response>((done) => {
          resolve = done;
        });
      }),
    );
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    await user.type(
      screen.getByRole("textbox", { name: "Ask clinic agent" }),
      "Show my records{Enter}",
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Searching");
    await user.click(screen.getByRole("button", { name: "New chat" }));
    expect(signal.aborted).toBe(true);
    resolve(new Response(JSON.stringify(answer), { status: 200 }));
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
    expect(screen.queryByText("Iris Example")).not.toBeInTheDocument();
    expect(
      screen.getByRole("dialog", { name: "New chat" }),
    ).toBeInTheDocument();
  });
  it("cancels and clears the conversation when the assessment date changes", async () => {
    let signal!: AbortSignal;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_url, options) => {
        signal = options.signal;
        return new Promise<Response>(() => {});
      }),
    );
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    await user.type(
      screen.getByRole("textbox", { name: "Ask clinic agent" }),
      "Find overdue labs{Enter}",
    );
    await screen.findByRole("status");
    await user.click(
      screen.getByRole("button", { name: "Change assessment date" }),
    );
    expect(signal.aborted).toBe(true);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    expect(
      screen.getByRole("dialog", { name: "New chat" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Find overdue labs")).not.toBeInTheDocument();
  });
  it("shows backend errors rather than fabricating an answer", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              detail: { message: "AI search is not configured." },
            }),
            { status: 503 },
          ),
      ),
    );
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    await user.type(
      screen.getByRole("textbox", { name: "Ask clinic agent" }),
      "Find overdue labs{Enter}",
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "AI search is not configured.",
    );
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
  it("opens the populated sample dashboard without requesting AI or writing records", async () => {
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const user = setup();
    await user.click(screen.getByRole("button", { name: "Open clinic agent" }));
    await user.click(
      screen.getByRole("button", { name: /Explore a sample dashboard/ }),
    );
    expect(
      await screen.findByText("Synthetic dashboard selected"),
    ).toBeInTheDocument();
    expect(location.search).toContain("demo=1");
    expect(location.hash).toBe("#/overview");
    expect(fetcher).not.toHaveBeenCalled();
    const rows = await sampleRequest<Page<Followup>>("followups");
    expect(rows.total).toBe(16);
    expect(new Set(rows.items.map((row) => row.status))).toEqual(
      new Set(["open", "done", "closed"]),
    );
    expect(
      rows.items.some((row) => !row.due_date && row.assigned_staff_id),
    ).toBe(true);
    expect(rows.items.every((row) => Boolean(row.assigned_staff_id))).toBe(
      true,
    );
  });
  it("offers a sample dashboard from login even when the backend is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockImplementation(
          async () =>
            new Response(
              JSON.stringify({ detail: { message: "Backend unavailable" } }),
              { status: 503 },
            ),
        ),
    );
    const user = setup({ login: true });
    await user.click(
      screen.getByRole("button", { name: /View sample dashboard/ }),
    );
    expect(
      await screen.findByText("Synthetic dashboard selected"),
    ).toBeInTheDocument();
    expect(location.search).toContain("demo=1");
  });
});
