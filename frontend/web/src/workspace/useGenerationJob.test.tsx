import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RequestOptions } from "../api/client";
import { GENERATE_SECTIONS_JOB_KIND } from "../api/jobs";
import type {
  GenerationAttemptRecord,
  JobRecord,
  M11Section,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  emptyDraftSections,
  useGenerationJob,
  type GenerationJobController,
} from "./useGenerationJob";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000030";
const JOB_ID = "00000000-0000-4000-8000-000000000040";

function section(
  number: string,
  content: string,
  status: M11Section["status"] = "draft",
): M11Section {
  return {
    id: `s-${number}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: number,
    title: `Section ${number}`,
    position: Number(number),
    instructions: "",
    content,
    status,
    current_revision: content.trim() === "" ? 0 : 2,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-08-01T09:00:00Z",
    updated_at: "2026-08-01T09:00:00Z",
  };
}

function jobRecord(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: JOB_ID,
    organization_id: ORGANIZATION_ID,
    conversation_id: CONVERSATION_ID,
    kind: GENERATE_SECTIONS_JOB_KIND,
    status: "queued",
    progress: 0,
    attempt: 1,
    error_code: null,
    correlation_id: "00000000-0000-4000-8000-000000000099",
    created_at: "2026-08-14T09:00:00Z",
    updated_at: "2026-08-14T09:00:00Z",
    started_at: null,
    finished_at: null,
    cancel_requested_at: null,
    ...overrides,
  };
}

function attempt(
  overrides: Partial<GenerationAttemptRecord> = {},
): GenerationAttemptRecord {
  return {
    section_number: "5",
    status: "failed",
    error_code: "provider_failed",
    citation_ids: [],
    attempt: 1,
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
  sections,
  enabled = true,
  onTerminal,
  capture,
}: {
  fetcher: AuthorizedFetch;
  sections: M11Section[];
  enabled?: boolean;
  onTerminal?: () => void;
  capture: (controller: GenerationJobController) => void;
}) {
  const controller = useGenerationJob({
    organizationId: ORGANIZATION_ID,
    conversationId: CONVERSATION_ID,
    sections,
    fetcher,
    enabled,
    onTerminal,
  });
  capture(controller);
  return (
    <div>
      <span data-testid="status">{controller.job?.status ?? "none"}</span>
      <span data-testid="attempts">{controller.attempts.length}</span>
      <button type="button" onClick={() => void controller.start()}>
        start
      </button>
      <button type="button" onClick={() => void controller.cancel()}>
        cancel
      </button>
      <button type="button" onClick={() => void controller.retryFailed()}>
        retry
      </button>
      <button type="button" onClick={() => void controller.retryFailed("5")}>
        retry-5
      </button>
    </div>
  );
}

describe("useGenerationJob", () => {
  it("selects only empty draft sections", () => {
    const sections = [
      section("1", ""),
      section("2", "Already written"),
      section("3", "   "),
      section("4", "", "done"),
    ];
    expect(emptyDraftSections(sections).map((item) => item.section_number)).toEqual([
      "1",
      "3",
    ]);
  });

  it("does not fetch when disabled", async () => {
    const { fetcher, calls } = capturingFetcher(() => {
      throw new Error("should not fetch");
    });
    let latest: GenerationJobController | null = null;
    render(
      <Harness
        fetcher={fetcher}
        sections={[section("1", "")]}
        enabled={false}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );
    await waitFor(() => {
      expect(latest).not.toBeNull();
    });
    expect(calls).toHaveLength(0);
  });

  it("resumes an in-flight job and polls getJob plus attempts", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const running = jobRecord({ status: "running", progress: 40 });
    const { fetcher, calls } = capturingFetcher((path) => {
      if (path.startsWith("/v1/jobs?")) {
        return { items: [running] };
      }
      if (path === `/v1/jobs/${JOB_ID}/attempts`) {
        return { items: [attempt({ status: "succeeded", error_code: null })] };
      }
      if (path === `/v1/jobs/${JOB_ID}`) {
        return { ...running, progress: 55 };
      }
      throw new Error(`unexpected ${path}`);
    });
    render(
      <Harness
        fetcher={fetcher}
        sections={[section("1", "")]}
        capture={() => undefined}
      />,
    );

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("running");
    });
    const before = calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(calls.slice(before).some((call) => call.path === `/v1/jobs/${JOB_ID}`)).toBe(
      true,
    );
    expect(
      calls.slice(before).some((call) => call.path === `/v1/jobs/${JOB_ID}/attempts`),
    ).toBe(true);
    vi.useRealTimers();
  });

  it("starts a job for empty drafts only", async () => {
    const { fetcher, calls } = capturingFetcher((path, options) => {
      if (options?.method === "POST" && path === "/v1/jobs") {
        return jobRecord({ status: "queued" });
      }
      if (path.startsWith("/v1/jobs?")) {
        return { items: [] };
      }
      if (path.endsWith("/attempts")) {
        return { items: [] };
      }
      throw new Error(`unexpected ${path}`);
    });
    render(
      <Harness
        fetcher={fetcher}
        sections={[section("1", ""), section("2", "Kept")]}
        capture={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(calls.some((call) => call.path.startsWith("/v1/jobs?"))).toBe(true);
    });

    await act(async () => {
      screen.getByRole("button", { name: "start" }).click();
    });

    const created = calls.find(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(created?.options?.json).toEqual({
      kind: GENERATE_SECTIONS_JOB_KIND,
      conversation_id: CONVERSATION_ID,
      parameters: {
        section_numbers: ["1"],
        expected_revisions: { "1": 0 },
      },
    });
  });

  it("cancels the current job", async () => {
    const running = jobRecord({ status: "running" });
    const { fetcher, calls } = capturingFetcher((path, options) => {
      if (path.startsWith("/v1/jobs?")) {
        return { items: [running] };
      }
      if (path === `/v1/jobs/${JOB_ID}/attempts`) {
        return { items: [] };
      }
      if (path === `/v1/jobs/${JOB_ID}/cancel` && options?.method === "POST") {
        return { ...running, status: "cancelled" };
      }
      if (path === `/v1/jobs/${JOB_ID}`) {
        return running;
      }
      throw new Error(`unexpected ${path}`);
    });
    render(
      <Harness
        fetcher={fetcher}
        sections={[section("1", "")]}
        capture={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("running");
    });

    await act(async () => {
      screen.getByRole("button", { name: "cancel" }).click();
    });

    expect(
      calls.some(
        (call) =>
          call.path === `/v1/jobs/${JOB_ID}/cancel` && call.options?.method === "POST",
      ),
    ).toBe(true);
  });

  it("retries only failed attempts, or one named section", async () => {
    const finished = jobRecord({ status: "failed" });
    const { fetcher, calls } = capturingFetcher((path, options) => {
      if (path.startsWith("/v1/jobs?")) {
        return { items: [finished] };
      }
      if (path === `/v1/jobs/${JOB_ID}/attempts`) {
        return {
          items: [
            attempt({ section_number: "5", status: "failed" }),
            attempt({
              section_number: "1",
              status: "succeeded",
              error_code: null,
            }),
          ],
        };
      }
      if (options?.method === "POST" && path === "/v1/jobs") {
        return jobRecord({ id: "new-job", status: "queued" });
      }
      throw new Error(`unexpected ${path}`);
    });
    render(
      <Harness
        fetcher={fetcher}
        sections={[section("1", "done text"), section("5", "")]}
        capture={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("attempts")).toHaveTextContent("2");
    });

    await act(async () => {
      screen.getByRole("button", { name: "retry-5" }).click();
    });

    const posted = calls.filter(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(posted[0]?.options?.json).toMatchObject({
      parameters: { section_numbers: ["5"] },
    });
  });
});
