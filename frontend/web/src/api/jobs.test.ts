import { describe, expect, it } from "vitest";

import type { RequestOptions } from "./client";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  GENERATE_JOB_POLL_MS,
  GENERATE_SECTIONS_JOB_KIND,
  cancelJob,
  createJob,
  getJob,
  getUsage,
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
});
