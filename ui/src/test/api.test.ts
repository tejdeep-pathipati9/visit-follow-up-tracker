import { afterEach, describe, expect, it, vi } from "vitest";
import { request, ApiError } from "@/lib/api";
import { sampleRequest } from "@/lib/sample-data";
import type { Followup, Page, Summary } from "@/lib/types";
afterEach(() => vi.unstubAllGlobals());
describe("API boundary", () => {
  it("encodes filters and keeps list parameters separate", async () => {
    const mock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", mock);
    await request("followups", {
      params: {
        q: "Zoë & Ana",
        flag: ["overdue", "unassigned"],
        status: "open",
      },
    });
    const url = new URL(String(mock.mock.calls[0][0]));
    expect(url.searchParams.get("q")).toBe("Zoë & Ana");
    expect(url.searchParams.getAll("flag")).toEqual(["overdue", "unassigned"]);
  });
  it("surfaces database errors rather than substituting demo records", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "database_unavailable",
              message: "Database unavailable.",
            },
          }),
          { status: 503 },
        ),
      ),
    );
    await expect(request("followups")).rejects.toMatchObject({
      status: 503,
      code: "database_unavailable",
      message: "Database unavailable.",
    });
  });
  it("preserves server validation messages", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: [{ msg: "Due date is required" }] }),
            { status: 422 },
          ),
        ),
    );
    await expect(
      request("followups", { method: "POST", body: {} }),
    ).rejects.toThrow("Due date is required");
  });
  it("calculates sample urgency and completion consistently", async () => {
    const summary = await sampleRequest<Summary>("dashboard");
    const overdue = await sampleRequest<Page<Followup>>("followups", {
      params: { preset: "overdue" },
    });
    expect(summary.followups.overdue_followups).toBe(overdue.total);
    expect(
      overdue.items.every(
        (r) => r.status === "open" && r.flags.includes("overdue"),
      ),
    ).toBe(true);
    const done = await sampleRequest<Page<Followup>>("followups", {
      params: { status: "done" },
    });
    expect(done.items.every((r) => r.flags.length === 0)).toBe(true);
  });
  it("does not fabricate AI answers or allow sample record creation", async () => {
    await expect(
      sampleRequest("ask", { method: "POST", body: { question: "Show labs" } }),
    ).rejects.toBeInstanceOf(ApiError);
    await expect(
      sampleRequest("patients", { method: "POST", body: { name: "Example" } }),
    ).rejects.toThrow("connected workspace");
  });
});

describe("Sample record relationships", () => {
  it("paginates record lists and resolves staff, visit, and episode details", async () => {
    const first = await sampleRequest<Page<Record<string, unknown>>>(
      "patients",
      { params: { limit: 15 } },
    );
    const second = await sampleRequest<Page<Record<string, unknown>>>(
      "patients",
      { params: { limit: 15, offset: 15 } },
    );
    expect(first.items).toHaveLength(15);
    expect(second.items).toHaveLength(1);
    expect(
      first.items.some((r) => r.patient_id === second.items[0].patient_id),
    ).toBe(false);
    const staff = await sampleRequest<{ staff: { name: string } }>(
      "staff/S001",
    );
    expect(staff.staff.name).toBe("Dr. Maya Chen");
    const visit = await sampleRequest<{ visit: { followups: Followup[] } }>(
      "visits/V001",
    );
    expect(visit.visit.followups[0].patient_id).toBe("P001");
    const episode = await sampleRequest<{ episode: { patient_id: string } }>(
      "episodes/E001",
    );
    expect(episode.episode.patient_id).toBe("P001");
  });
});
