import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RequestOptions } from "../api/client";
import type { UsageRecord } from "../api/types";
import {
  AuthContext,
  AuthProvider,
  type AuthContextValue,
  type AuthorizedFetch,
} from "../auth/AuthContext";
import {
  OrganizationContext,
  OrganizationProvider,
  type OrganizationContextValue,
} from "../org/OrganizationContext";
import { formatCostMicros } from "../product/deliveryAuditReviewFixtures";
import { UsagePage, type UsageReviewState } from "./UsagePage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const ACCOUNT_ID = "00000000-0000-4000-8000-000000000020";
const CONVERSATION_ID = "c-aurora";

function unauthorized(): Response {
  return new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

function renderReview(review: UsageReviewState) {
  return render(
    <MemoryRouter initialEntries={[`/review/usage/${review}`]}>
      <AuthProvider>
        <OrganizationProvider>
          <UsagePage review={review} />
        </OrganizationProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function usageSnapshot(totalCostMicros: number): UsageRecord {
  return {
    protocol_title: "AURORA-301",
    protocol_id: CONVERSATION_ID,
    summary: {
      total_cost_micros: totalCostMicros,
      input_tokens: 20,
      output_tokens: 10,
      successful_jobs: totalCostMicros === 0 ? 0 : 1,
      failed_or_cancelled: 0,
      generation_count: totalCostMicros === 0 ? 0 : 1,
      pricing_basis: "Versioned provider pricing",
      updated_at: totalCostMicros === 0 ? null : "2026-08-13T12:00:00Z",
    },
    generations:
      totalCostMicros === 0
        ? []
        : [
            {
              id: "job-1",
              job_id: "job-1",
              scope: "Section 6",
              section_numbers: ["6"],
              requester: "You",
              model: "fake-chat",
              input_tokens: 20,
              output_tokens: 10,
              latency_ms: 6,
              outcome: "complete",
              cost_micros: totalCostMicros,
              pricing_version: "2026-08-13",
              started_at: "2026-08-13T12:00:00Z",
              completed_at: "2026-08-13T12:00:01Z",
              provider_calls: [],
            },
          ],
  };
}

function createFetcher(
  handler: (
    path: string,
    options: RequestOptions | undefined,
  ) => unknown | Promise<unknown>,
): { fetcher: AuthorizedFetch; calls: Array<{ path: string; options: RequestOptions | undefined }> } {
  const calls: Array<{ path: string; options: RequestOptions | undefined }> = [];
  async function fetcher<T>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> {
    calls.push({ path, options });
    return (await handler(path, options)) as T;
  }
  return { fetcher, calls };
}

function renderLive(fetcher: AuthorizedFetch) {
  const auth: AuthContextValue = {
    status: "authenticated",
    account: {
      id: ACCOUNT_ID,
      email: "author@example.com",
      is_active: true,
      created_at: "2026-07-28T08:00:00Z",
    },
    signIn: async () => undefined,
    signOut: async () => undefined,
    authorizedFetch: fetcher,
  };
  const organization: OrganizationContextValue = {
    status: "ready",
    organizations: [
      {
        id: ORGANIZATION_ID,
        name: "Acme Trials",
        role: "owner",
        created_at: "2026-07-28T08:00:00Z",
      },
    ],
    activeId: ORGANIZATION_ID,
    action: "idle",
    feedback: null,
    select: () => undefined,
    reload: () => undefined,
    create: async () => true,
    join: async () => true,
    dismissFeedback: () => undefined,
  };
  return render(
    <MemoryRouter initialEntries={[`/workspace/${CONVERSATION_ID}/usage`]}>
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <Routes>
            <Route
              path="/workspace/:conversationId/usage"
              element={<UsagePage />}
            />
          </Routes>
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("UsagePage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders a workspace-scoped populated audit with an explicit fixture note", () => {
    renderReview("populated");

    expect(screen.getByRole("dialog", { name: "Usage and cost" })).toBeInTheDocument();
    expect(screen.getByText("$12.46")).toBeInTheDocument();
    expect(screen.getByText(/costs and provider calls are illustrative/i)).toBeInTheDocument();
    expect(screen.queryByText(/manage billing|download csv|export json/i)).not.toBeInTheDocument();
  });

  it("opens expanded call detail directly", () => {
    renderReview("expanded");

    expect(screen.getByText("JOB-7729-X")).toBeInTheDocument();
    expect(screen.getByText("Provider-call breakdown")).toBeInTheDocument();
    const fetchMock = vi.mocked(fetch);
    expect(
      fetchMock.mock.calls.some((call) => String(call[0]).includes("/v1/jobs/usage")),
    ).toBe(false);
  });

  it("shows running activity without estimating final cost", () => {
    renderReview("running");

    expect(screen.getAllByText("In progress").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Finalizes on completion").length).toBeGreaterThan(0);
    expect(screen.queryByText(/estimated cost/i)).not.toBeInTheDocument();
  });

  it("keeps filters visible in a filtered-to-nothing state and clears them", async () => {
    const user = userEvent.setup();
    renderReview("filtered");

    expect(screen.getByLabelText("Outcome")).toHaveValue("attention");
    await user.selectOptions(screen.getByLabelText("Section"), "5");
    expect(screen.getByText(/filters changed locally/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Section")).toBeInTheDocument();
  });

  it("recovers from the review error without claiming a stored read", async () => {
    const user = userEvent.setup();
    renderReview("error");

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText(/no model usage recorded/i)).toBeInTheDocument();
    expect(screen.getByText(/no stored usage was read or changed/i)).toBeInTheDocument();
  });

  it("shows stored catalog totals on the live page", async () => {
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path.includes("/v1/jobs/usage")) {
        return usageSnapshot(4);
      }
      if (path.includes("/messages")) {
        return { items: [], next_cursor: null };
      }
      if (path.includes("/documents")) {
        return { items: [], next_cursor: null };
      }
      if (path.includes("/m11-sections")) {
        return { catalog_version: "2025.1", items: [] };
      }
      if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
        return {
          id: CONVERSATION_ID,
          organization_id: ORGANIZATION_ID,
          owner_account_id: ACCOUNT_ID,
          title: "AURORA-301",
          status: "active",
          collaborator_account_ids: [],
          created_at: "2026-08-13T12:00:00Z",
          updated_at: "2026-08-13T12:00:00Z",
          last_activity_at: "2026-08-13T12:00:00Z",
          archived_at: null,
        };
      }
      throw new Error(`Unexpected request: ${options?.method ?? "GET"} ${path}`);
    });

    renderLive(fetcher);

    expect(
      (await screen.findAllByText(formatCostMicros(4))).length,
    ).toBeGreaterThan(0);
    expect(
      screen.queryByText(/provider usage records are not connected/i),
    ).not.toBeInTheDocument();
    expect(calls.some((call) => call.path.includes("/v1/jobs/usage"))).toBe(true);
    expect(calls.some((call) => call.options?.method === "POST")).toBe(false);
  });
});
