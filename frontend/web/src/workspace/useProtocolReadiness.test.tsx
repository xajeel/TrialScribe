import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import { VALIDATE_READINESS_JOB_KIND } from "../api/jobs";
import type { JobRecord, ReadinessRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  useProtocolReadiness,
  type ProtocolReadinessController,
} from "./useProtocolReadiness";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000030";
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
    correlation_id: "00000000-0000-4000-8000-000000000099",
    created_at: "2026-08-15T09:00:00Z",
    updated_at: "2026-08-15T09:00:00Z",
    started_at: "2026-08-15T09:00:00Z",
    finished_at: "2026-08-15T09:01:00Z",
    cancel_requested_at: null,
    ...overrides,
  };
}

function capturingFetcher(
  handler: (path: string, options: RequestOptions | undefined) => unknown,
): {
  fetcher: AuthorizedFetch;
  calls: Array<{ path: string; options: RequestOptions | undefined }>;
} {
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

function Harness({
  fetcher,
  enabled = true,
  capture,
}: {
  fetcher: AuthorizedFetch;
  enabled?: boolean;
  capture: (controller: ProtocolReadinessController) => void;
}) {
  const controller = useProtocolReadiness({
    organizationId: ORGANIZATION_ID,
    conversationId: CONVERSATION_ID,
    fetcher,
    enabled,
  });
  capture(controller);
  return (
    <div>
      <span data-testid="checked">{String(controller.record?.checked ?? "")}</span>
      <span data-testid="error">{controller.error ?? ""}</span>
      <button type="button" onClick={() => void controller.start()}>
        start
      </button>
    </div>
  );
}

describe("useProtocolReadiness", () => {
  it("does not fetch when disabled", async () => {
    const { fetcher, calls } = capturingFetcher(() => {
      throw new Error("should not fetch");
    });
    let latest: ProtocolReadinessController | null = null;
    render(
      <Harness
        fetcher={fetcher}
        enabled={false}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );
    await act(async () => {
      await latest?.start();
    });
    expect(calls).toHaveLength(0);
  });

  it("loads the snapshot then starts a validate_readiness job", async () => {
    let snapshot = emptyReadiness();
    const { fetcher, calls } = capturingFetcher((path, options) => {
      if (path.startsWith("/v1/jobs/readiness?")) {
        return snapshot;
      }
      if (path === "/v1/jobs" && options?.method === "POST") {
        return jobRecord({ status: "queued", progress: 0 });
      }
      if (path === `/v1/jobs/${JOB_ID}`) {
        snapshot = emptyReadiness({
          checked: true,
          ready: false,
          job_id: JOB_ID,
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
            latest_activity: "2026-08-15T09:00:00Z",
            citations: { resolved: 0, needing_review: 0 },
          },
        });
        return jobRecord();
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    let latest: ProtocolReadinessController | null = null;
    render(
      <Harness
        fetcher={fetcher}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("checked")).toHaveTextContent("false");
    });
    await act(async () => {
      await latest?.start();
    });

    const created = calls.find(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(created?.options?.json).toEqual({
      kind: VALIDATE_READINESS_JOB_KIND,
      conversation_id: CONVERSATION_ID,
      parameters: {},
    });
    await waitFor(() => {
      expect(latest?.view?.issues[0]?.id).toBe("section-not-done-s5");
    });
  });
});
