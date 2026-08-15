import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import { GENERATE_SECTIONS_JOB_KIND } from "../api/jobs";
import type { JobRecord, M11Section } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  useSectionRewrite,
  type SectionRewriteController,
} from "./useSectionRewrite";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000030";
const JOB_ID = "00000000-0000-4000-8000-000000000040";

function sectionRecord(overrides: Partial<M11Section> = {}): M11Section {
  return {
    id: "section-5",
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: "5",
    title: "Trial Population",
    position: 5,
    instructions: "Keep eligibility precise.",
    content: "Current draft wording.",
    status: "draft",
    current_revision: 2,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-08-01T09:00:00Z",
    updated_at: "2026-08-01T09:00:00Z",
    ...overrides,
  };
}

function jobRecord(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: JOB_ID,
    organization_id: ORGANIZATION_ID,
    conversation_id: CONVERSATION_ID,
    kind: GENERATE_SECTIONS_JOB_KIND,
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
  section,
  enabled = true,
  capture,
}: {
  fetcher: AuthorizedFetch;
  section: M11Section | null;
  enabled?: boolean;
  capture: (controller: SectionRewriteController) => void;
}) {
  const controller = useSectionRewrite({
    organizationId: ORGANIZATION_ID,
    conversationId: CONVERSATION_ID,
    section,
    fetcher,
    enabled,
  });
  capture(controller);
  return (
    <div>
      <span data-testid="options">{controller.options.length}</span>
      <span data-testid="error">{controller.error ?? ""}</span>
      <button
        type="button"
        onClick={() =>
          void controller.start({
            instruction: "Tighten the wording.",
            keepCitations: true,
            useSources: false,
            selectionStart: 0,
            selectionEnd: 7,
          })
        }
      >
        start
      </button>
      <button
        type="button"
        onClick={() => void controller.useOption("alternative-1")}
      >
        use
      </button>
    </div>
  );
}

describe("useSectionRewrite", () => {
  it("does not fetch when disabled or the section is done", async () => {
    const { fetcher, calls } = capturingFetcher(() => {
      throw new Error("should not fetch");
    });
    let latest: SectionRewriteController | null = null;
    const disabled = render(
      <Harness
        fetcher={fetcher}
        section={sectionRecord()}
        enabled={false}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );
    await act(async () => {
      await latest?.start({
        instruction: "Tighten the wording.",
        keepCitations: true,
        useSources: true,
      });
    });
    expect(calls).toHaveLength(0);
    disabled.unmount();

    render(
      <Harness
        fetcher={fetcher}
        section={sectionRecord({ status: "done" })}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );
    await act(async () => {
      await latest?.start({
        instruction: "Tighten the wording.",
        keepCitations: true,
        useSources: true,
      });
    });
    expect(calls).toHaveLength(0);
  });

  it("starts a rewrite job and applies the chosen option", async () => {
    const { fetcher, calls } = capturingFetcher((path, options) => {
      if (path === "/v1/jobs" && options?.method === "POST") {
        return jobRecord();
      }
      if (path === `/v1/jobs/${JOB_ID}`) {
        return jobRecord();
      }
      if (path === `/v1/jobs/${JOB_ID}/rewrite-options`) {
        return {
          items: [
            { id: "alternative-1", text: "Rewritten option one." },
            { id: "alternative-2", text: "Rewritten option two." },
          ],
        };
      }
      if (path.includes("/m11-sections/5") && options?.method === "PATCH") {
        return sectionRecord({ content: "Rewritten option one.", current_revision: 3 });
      }
      throw new Error(`unexpected ${path}`);
    });
    let latest: SectionRewriteController | null = null;
    render(
      <Harness
        fetcher={fetcher}
        section={sectionRecord()}
        capture={(controller) => {
          latest = controller;
        }}
      />,
    );

    await act(async () => {
      screen.getByRole("button", { name: "start" }).click();
    });
    await waitFor(() => {
      expect(screen.getByTestId("options")).toHaveTextContent("2");
    });

    const created = calls.find(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(created?.options?.json).toEqual({
      kind: GENERATE_SECTIONS_JOB_KIND,
      conversation_id: CONVERSATION_ID,
      parameters: {
        mode: "rewrite",
        section_numbers: ["5"],
        expected_revisions: { "5": 2 },
        rewrite_instruction: "Tighten the wording.",
        keep_citations: true,
        use_sources: false,
        selection_start: 0,
        selection_end: 7,
      },
    });

    await act(async () => {
      screen.getByRole("button", { name: "use" }).click();
    });
    await waitFor(() => {
      const patched = calls.find(
        (call) => call.options?.method === "PATCH",
      );
      expect(patched?.options?.json).toEqual({
        expected_revision: 2,
        instructions: "Keep eligibility precise.",
        content: "Rewritten option one.",
      });
    });
  });
});
