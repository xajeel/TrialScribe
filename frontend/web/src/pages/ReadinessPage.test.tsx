import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import { VALIDATE_READINESS_JOB_KIND } from "../api/jobs";
import type { JobRecord, ReadinessRecord } from "../api/types";
import {
  AuthContext,
  type AuthContextValue,
  type AuthorizedFetch,
} from "../auth/AuthContext";
import {
  OrganizationContext,
  type OrganizationContextValue,
} from "../org/OrganizationContext";
import { ReadinessPage } from "./ReadinessPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const ACCOUNT_ID = "00000000-0000-4000-8000-000000000020";
const CONVERSATION_ID = "conversation-1";
const JOB_ID = "00000000-0000-4000-8000-000000000040";

function emptyReadiness(
  overrides: Partial<ReadinessRecord> = {},
): ReadinessRecord {
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
    ...overrides,
  };
}

function jobRecord(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: JOB_ID,
    organization_id: ORGANIZATION_ID,
    conversation_id: CONVERSATION_ID,
    kind: VALIDATE_READINESS_JOB_KIND,
    status: "succeeded",
    progress: 100,
    attempt: 1,
    error_code: null,
    correlation_id: "corr-1",
    created_at: "2026-08-15T09:00:00Z",
    updated_at: "2026-08-15T09:00:00Z",
    started_at: "2026-08-15T09:00:00Z",
    finished_at: "2026-08-15T09:01:00Z",
    cancel_requested_at: null,
    ...overrides,
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
    <MemoryRouter initialEntries={[`/workspace/${CONVERSATION_ID}/readiness`]}>
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <Routes>
            <Route
              path="/workspace/:conversationId/readiness"
              element={<ReadinessPage />}
            />
          </Routes>
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("ReadinessPage", () => {
  it("posts validate_readiness and renders snapshot issues", async () => {
    const user = userEvent.setup();
    let snapshot = emptyReadiness();
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path.startsWith("/v1/jobs/readiness?")) {
        return snapshot;
      }
      if (path === "/v1/jobs" && options?.method === "POST") {
        return jobRecord({ status: "queued", progress: 0, finished_at: null });
      }
      if (path === `/v1/jobs/${JOB_ID}`) {
        snapshot = emptyReadiness({
          checked: true,
          ready: false,
          job_id: JOB_ID,
          computed_at: "2026-08-15T09:01:00Z",
          issues: [
            {
              id: "section-not-done-s5",
              title: "Section is not marked done",
              detail: "5 · Trial Population",
              severity: "error",
              code: "section_not_done",
              action: "open-section",
              action_label: "Open section",
              section_number: "5",
            },
          ],
          summary: {
            total_sections: 14,
            done_sections: 13,
            draft_sections: 1,
            ready_sources: 1,
            pending_sources: 0,
            failed_sources: 0,
            latest_activity: "2026-08-15T09:01:00Z",
            citations: { resolved: 0, needing_review: 0 },
          },
        });
        return jobRecord();
      }
      throw new Error(`Unexpected request: ${options?.method ?? "GET"} ${path}`);
    });

    renderLive(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Protocol readiness" }),
    ).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Check protocol" }));

    const created = calls.find(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(created?.options?.json).toEqual({
      kind: VALIDATE_READINESS_JOB_KIND,
      conversation_id: CONVERSATION_ID,
      parameters: {},
    });
    expect(
      await screen.findByText("Section is not marked done"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Check again" })).toBeInTheDocument();
    });
  });
});
