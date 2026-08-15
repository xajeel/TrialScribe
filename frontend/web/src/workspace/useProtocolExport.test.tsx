import { act, render, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import { EXPORT_PROTOCOL_JOB_KIND } from "../api/jobs";
import type { ExportList, JobRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  useProtocolExport,
  type ProtocolExportController,
} from "./useProtocolExport";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000030";
const ACCOUNT_ID = "00000000-0000-4000-8000-000000000020";
const JOB_ID = "00000000-0000-4000-8000-000000000040";
const EXPORT_ID = "00000000-0000-4000-8000-000000000050";

function jobRecord(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: JOB_ID,
    organization_id: ORGANIZATION_ID,
    conversation_id: CONVERSATION_ID,
    kind: EXPORT_PROTOCOL_JOB_KIND,
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

function exportList(): ExportList {
  return {
    items: [
      {
        id: EXPORT_ID,
        job_id: JOB_ID,
        filename: "AURORA-301_protocol_2026-08-15.docx",
        byte_size: 2048,
        section_count: 8,
        scope: "done-only",
        created_at: "2026-08-15T09:01:00Z",
        requester: "You",
      },
    ],
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
  capture: (controller: ProtocolExportController) => void;
}) {
  const controller = useProtocolExport({
    organizationId: ORGANIZATION_ID,
    conversationId: CONVERSATION_ID,
    fetcher,
    enabled,
    accountId: ACCOUNT_ID,
  });
  capture(controller);
  return <button type="button" onClick={() => void controller.start("done-only")}>start</button>;
}

describe("useProtocolExport", () => {
  it("does not fetch when disabled", async () => {
    const { fetcher, calls } = capturingFetcher(() => {
      throw new Error("should not fetch");
    });
    let latest: ProtocolExportController | null = null;
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
      await latest?.start("done-only");
    });
    expect(calls).toHaveLength(0);
  });

  it("creates an export_protocol job then lists the stored file", async () => {
    const { fetcher, calls } = capturingFetcher((path, options) => {
      if (path === "/v1/jobs" && options?.method === "POST") {
        return jobRecord({ status: "queued", progress: 0, finished_at: null });
      }
      if (path === `/v1/jobs/${JOB_ID}`) {
        return jobRecord();
      }
      if (path.startsWith("/v1/jobs/exports?")) {
        return exportList();
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    let latest: ProtocolExportController | null = null;
    render(
      <Harness
        fetcher={fetcher}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );

    await act(async () => {
      await latest?.start("done-only");
    });

    const created = calls.find(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(created?.options?.json).toEqual({
      kind: EXPORT_PROTOCOL_JOB_KIND,
      conversation_id: CONVERSATION_ID,
      parameters: { scope: "done-only" },
    });
    expect(
      calls.some((call) => call.path.startsWith("/v1/jobs/exports?")),
    ).toBe(true);
    await waitFor(() => {
      expect(latest?.panelState).toBe("ready");
      expect(latest?.jobView?.readyFile.exportId).toBe(EXPORT_ID);
    });
  });
});
