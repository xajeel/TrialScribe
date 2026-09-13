import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
import type { ExportReviewState } from "../product/deliveryAuditReviewFixtures";
import { ExportPage } from "./ExportPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const ACCOUNT_ID = "00000000-0000-4000-8000-000000000020";
const CONVERSATION_ID = "conversation-1";

function unauthorized(): Response {
  return new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

function renderReview(review: ExportReviewState) {
  return render(
    <MemoryRouter initialEntries={[`/review/export/${review}`]}>
      <AuthProvider>
        <OrganizationProvider>
          <ExportPage review={review} />
        </OrganizationProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ExportPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders configuration with all fixed-order sections and review disclosure", () => {
    renderReview("configuration");

    expect(screen.getByRole("dialog", { name: "Export protocol" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(14);
    expect(screen.getByText(/development review data/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate DOCX" })).toBeEnabled();
  });

  it("selects drafts and moves generation into a local-only building state", async () => {
    const user = userEvent.setup();
    renderReview("configuration");

    await user.click(screen.getByLabelText(/include unfinished sections/i));
    expect(screen.getByRole("status")).toHaveTextContent(/marked as draft/i);
    await user.click(screen.getByRole("button", { name: "Generate DOCX" }));
    expect(screen.getByRole("heading", { name: "Preparing export" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/no export job was created/i);
  });

  it("disables generation when no section is Done", () => {
    renderReview("empty");

    expect(screen.getByText(/complete at least one section/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate DOCX" })).toBeDisabled();
  });

  it("supports ready download feedback without creating a file", async () => {
    const user = userEvent.setup();
    renderReview("ready");

    await user.click(screen.getByRole("button", { name: "Download DOCX" }));
    expect(screen.getByRole("status")).toHaveTextContent(/was not downloaded/i);
  });

  it("retries a failed export only inside the review", async () => {
    const user = userEvent.setup();
    renderReview("failed");

    await user.click(screen.getByRole("button", { name: "Retry export" }));
    expect(screen.getByRole("heading", { name: "Preparing export" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/development review only/i);
  });

  it("keeps the review ready panel without fetching jobs", () => {
    renderReview("ready");

    expect(screen.getByRole("heading", { name: "Protocol ready" })).toBeInTheDocument();
    expect(
      vi.mocked(fetch).mock.calls.some(([input]) =>
        String(input).includes("/v1/jobs/readiness"),
      ),
    ).toBe(false);
    expect(
      vi.mocked(fetch).mock.calls.some(([input]) =>
        String(input).includes("/v1/jobs/exports"),
      ),
    ).toBe(false);
  });

  it("blocks live export when the stored check is not ready", async () => {
    const conversation = {
      id: CONVERSATION_ID,
      organization_id: ORGANIZATION_ID,
      owner_account_id: ACCOUNT_ID,
      title: "AURORA-301",
      status: "active",
      collaborator_account_ids: [],
      created_at: "2026-07-28T09:00:00Z",
      updated_at: "2026-07-28T09:00:00Z",
      last_activity_at: "2026-07-28T09:00:00Z",
      archived_at: null,
    };
    const section = {
      id: "section-1",
      conversation_id: CONVERSATION_ID,
      organization_id: ORGANIZATION_ID,
      catalog_version: "2025.1",
      section_number: "1",
      title: "Protocol Summary",
      position: 1,
      instructions: "",
      content: "Done wording",
      status: "done",
      current_revision: 1,
      completed_at: "2026-07-28T09:00:00Z",
      completed_by_account_id: ACCOUNT_ID,
      created_at: "2026-07-28T09:00:00Z",
      updated_at: "2026-07-28T09:00:00Z",
    };
    const fetcher: AuthorizedFetch = async (path) => {
      if (path.startsWith("/v1/jobs/readiness?")) {
        return {
          checked: false,
          ready: false,
          stale: false,
          job_id: null,
          computed_at: null,
          protocol_title: "AURORA-301",
          protocol_id: CONVERSATION_ID,
          summary: {
            total_sections: 0,
            done_sections: 0,
            draft_sections: 0,
            ready_sources: 0,
            pending_sources: 0,
            failed_sources: 0,
            latest_activity: null,
            citations: null,
          },
          issues: [],
          sections: [],
        } as never;
      }
      if (path.includes("/messages")) {
        return { items: [], next_cursor: null } as never;
      }
      if (path.includes("/documents")) {
        return { items: [], next_cursor: null } as never;
      }
      if (path.includes("/m11-sections")) {
        return { catalog_version: "2025.1", items: [section] } as never;
      }
      if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
        return conversation as never;
      }
      throw new Error(`Unexpected request: ${path}`);
    };
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

    render(
      <MemoryRouter initialEntries={[`/workspace/${CONVERSATION_ID}/export`]}>
        <AuthContext.Provider value={auth}>
          <OrganizationContext.Provider value={organization}>
            <Routes>
              <Route
                path="/workspace/:conversationId/export"
                element={<ExportPage />}
              />
            </Routes>
          </OrganizationContext.Provider>
        </AuthContext.Provider>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Protocol is not ready to export."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate DOCX" })).toBeDisabled();
    expect(screen.queryByText(/protocol ready/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review readiness" })).toBeInTheDocument();
  });

  it("enables live generate when the stored check is ready", async () => {
    const user = userEvent.setup();
    const posts: string[] = [];
    const conversation = {
      id: CONVERSATION_ID,
      organization_id: ORGANIZATION_ID,
      owner_account_id: ACCOUNT_ID,
      title: "AURORA-301",
      status: "active",
      collaborator_account_ids: [],
      created_at: "2026-07-28T09:00:00Z",
      updated_at: "2026-07-28T09:00:00Z",
      last_activity_at: "2026-07-28T09:00:00Z",
      archived_at: null,
    };
    const section = {
      id: "section-1",
      conversation_id: CONVERSATION_ID,
      organization_id: ORGANIZATION_ID,
      catalog_version: "2025.1",
      section_number: "1",
      title: "Protocol Summary",
      position: 1,
      instructions: "",
      content: "Done wording",
      status: "done",
      current_revision: 1,
      completed_at: "2026-07-28T09:00:00Z",
      completed_by_account_id: ACCOUNT_ID,
      created_at: "2026-07-28T09:00:00Z",
      updated_at: "2026-07-28T09:00:00Z",
    };
    const job = {
      id: "00000000-0000-4000-8000-000000000070",
      organization_id: ORGANIZATION_ID,
      conversation_id: CONVERSATION_ID,
      kind: "export_protocol",
      status: "queued",
      progress: 0,
      attempt: 0,
      error_code: null,
      correlation_id: "00000000-0000-4000-8000-000000000071",
      created_at: "2026-08-15T09:00:00Z",
      updated_at: "2026-08-15T09:00:00Z",
      started_at: null,
      finished_at: null,
      cancel_requested_at: null,
    };
    const fetcher: AuthorizedFetch = async (path, options) => {
      if (path === "/v1/jobs" && options?.method === "POST") {
        posts.push(JSON.stringify(options.json));
        return { ...job } as never;
      }
      if (path === `/v1/jobs/${job.id}`) {
        return { ...job, status: "succeeded", progress: 100 } as never;
      }
      if (path.startsWith("/v1/jobs/exports?")) {
        return {
          items: [
            {
              id: "00000000-0000-4000-8000-000000000080",
              job_id: job.id,
              filename: "AURORA-301_protocol_2026-08-15.docx",
              byte_size: 2048,
              section_count: 1,
              scope: "done-only",
              created_at: "2026-08-15T09:01:00Z",
              requester: "You",
            },
          ],
        } as never;
      }
      if (path.startsWith("/v1/jobs/readiness?")) {
        return {
          checked: true,
          ready: true,
          stale: false,
          job_id: "00000000-0000-4000-8000-000000000060",
          computed_at: "2026-07-28T09:00:00Z",
          protocol_title: "AURORA-301",
          protocol_id: CONVERSATION_ID,
          summary: {
            total_sections: 14,
            done_sections: 14,
            draft_sections: 0,
            ready_sources: 1,
            pending_sources: 0,
            failed_sources: 0,
            latest_activity: "2026-07-28T09:00:00Z",
            citations: { resolved: 1, needing_review: 0 },
          },
          issues: [],
          sections: [],
        } as never;
      }
      if (path.includes("/messages")) {
        return { items: [], next_cursor: null } as never;
      }
      if (path.includes("/documents")) {
        return { items: [], next_cursor: null } as never;
      }
      if (path.includes("/m11-sections")) {
        return { catalog_version: "2025.1", items: [section] } as never;
      }
      if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
        return conversation as never;
      }
      throw new Error(`Unexpected request: ${path}`);
    };
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

    render(
      <MemoryRouter initialEntries={[`/workspace/${CONVERSATION_ID}/export`]}>
        <AuthContext.Provider value={auth}>
          <OrganizationContext.Provider value={organization}>
            <Routes>
              <Route
                path="/workspace/:conversationId/export"
                element={<ExportPage />}
              />
            </Routes>
          </OrganizationContext.Provider>
        </AuthContext.Provider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole("button", { name: "Generate DOCX" })).toBeEnabled();
    expect(screen.queryByText(/not connected/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate DOCX" }));
    expect(posts).toHaveLength(1);
    expect(posts[0]).toContain("export_protocol");
    expect(posts[0]).toContain("done-only");
  });
});
