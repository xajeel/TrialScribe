import { describe, expect, it } from "vitest";

import type { RequestOptions } from "./client";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  EXPORT_PROTOCOL_JOB_KIND,
  GENERATE_JOB_POLL_MS,
  GENERATE_SECTIONS_JOB_KIND,
  VALIDATE_READINESS_JOB_KIND,
  cancelJob,
  createJob,
  downloadExport,
  exportFileFromApi,
  getJob,
  getReadiness,
  getUsage,
  listExports,
  listJobAttempts,
  listJobs,
  listRewriteOptions,
} from "./jobs";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000020";
const JOB_ID = "00000000-0000-4000-8000-000000000030";

function capturingFetcher(): {
  fetcher: AuthorizedFetch;
  calls: Array<{ path: string; options: RequestOptions | undefined }>;
} {
  const calls: Array<{ path: string; options: RequestOptions | undefined }> = [];
  const fetcher: AuthorizedFetch = async <T>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> => {
    calls.push({ path, options });
    return { id: JOB_ID, items: [] } as T;
  };
  return { fetcher, calls };
}

describe("jobs api", () => {
  it("exports the generate-sections kind and one-second poll interval", () => {
    expect(GENERATE_SECTIONS_JOB_KIND).toBe("generate_sections");
    expect(VALIDATE_READINESS_JOB_KIND).toBe("validate_readiness");
    expect(EXPORT_PROTOCOL_JOB_KIND).toBe("export_protocol");
    expect(GENERATE_JOB_POLL_MS).toBe(1000);
  });

  it("creates a job with kind, conversation, and parameters", async () => {
    const { fetcher, calls } = capturingFetcher();

    await createJob(fetcher, ORGANIZATION_ID, GENERATE_SECTIONS_JOB_KIND, CONVERSATION_ID, {
      section_numbers: ["1", "5"],
      expected_revisions: { "1": 0, "5": 0 },
    });

    expect(calls[0]?.path).toBe("/v1/jobs");
    expect(calls[0]?.options).toEqual({
      method: "POST",
      headers: { "X-Organization-ID": ORGANIZATION_ID },
      json: {
        kind: GENERATE_SECTIONS_JOB_KIND,
        conversation_id: CONVERSATION_ID,
        parameters: {
          section_numbers: ["1", "5"],
          expected_revisions: { "1": 0, "5": 0 },
        },
      },
    });
  });

  it("lists jobs with conversation_id and kind", async () => {
    const { fetcher, calls } = capturingFetcher();

    await listJobs(
      fetcher,
      ORGANIZATION_ID,
      CONVERSATION_ID,
      GENERATE_SECTIONS_JOB_KIND,
      1,
    );

    expect(calls[0]?.path).toContain("/v1/jobs?");
    expect(calls[0]?.path).toContain(`conversation_id=${CONVERSATION_ID}`);
    expect(calls[0]?.path).toContain(`kind=${GENERATE_SECTIONS_JOB_KIND}`);
    expect(calls[0]?.path).toContain("limit=1");
  });

  it("reads one job and its attempts", async () => {
    const { fetcher, calls } = capturingFetcher();

    await getJob(fetcher, ORGANIZATION_ID, JOB_ID);
    await listJobAttempts(fetcher, ORGANIZATION_ID, JOB_ID);
    await listRewriteOptions(fetcher, ORGANIZATION_ID, JOB_ID);

    expect(calls[0]?.path).toBe(`/v1/jobs/${JOB_ID}`);
    expect(calls[1]?.path).toBe(`/v1/jobs/${JOB_ID}/attempts`);
    expect(calls[2]?.path).toBe(`/v1/jobs/${JOB_ID}/rewrite-options`);
  });

  it("cancels a job with a POST to /cancel", async () => {
    const { fetcher, calls } = capturingFetcher();

    await cancelJob(fetcher, ORGANIZATION_ID, JOB_ID);

    expect(calls[0]?.path).toBe(`/v1/jobs/${JOB_ID}/cancel`);
    expect(calls[0]?.options?.method).toBe("POST");
  });

  it("reads usage with conversation_id", async () => {
    const { fetcher, calls } = capturingFetcher();

    await getUsage(fetcher, ORGANIZATION_ID, CONVERSATION_ID);

    expect(calls[0]?.path).toContain("/v1/jobs/usage?");
    expect(calls[0]?.path).toContain(`conversation_id=${CONVERSATION_ID}`);
  });

  it("reads readiness with conversation_id", async () => {
    const { fetcher, calls } = capturingFetcher();

    await getReadiness(fetcher, ORGANIZATION_ID, CONVERSATION_ID);

    expect(calls[0]?.path).toContain("/v1/jobs/readiness?");
    expect(calls[0]?.path).toContain(`conversation_id=${CONVERSATION_ID}`);
  });

  it("lists exports with conversation_id", async () => {
    const { fetcher, calls } = capturingFetcher();

    await listExports(fetcher, ORGANIZATION_ID, CONVERSATION_ID);

    expect(calls[0]?.path).toContain("/v1/jobs/exports?");
    expect(calls[0]?.path).toContain(`conversation_id=${CONVERSATION_ID}`);
  });

  it("downloads an export file as a blob", async () => {
    const { fetcher, calls } = capturingFetcher();
    const exportId = "00000000-0000-4000-8000-000000000040";

    await downloadExport(fetcher, ORGANIZATION_ID, exportId);

    expect(calls[0]?.path).toBe(`/v1/jobs/exports/${exportId}/file`);
    expect(calls[0]?.options?.responseType).toBe("blob");
  });

  it("maps an export record onto the file card view", () => {
    const view = exportFileFromApi(
      {
        id: "export-1",
        job_id: JOB_ID,
        filename: "AURORA-301_protocol_2026-08-15.docx",
        byte_size: 2048,
        section_count: 8,
        scope: "done-only",
        created_at: "2026-08-15T12:00:00Z",
        requester: "You",
      },
      "You",
    );
    expect(view.exportId).toBe("export-1");
    expect(view.byteSize).toBe(2048);
    expect(view.sections).toBe(8);
    expect(view.requester).toBe("You");
  });
});
