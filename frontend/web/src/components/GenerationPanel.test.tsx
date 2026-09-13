import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GENERATE_SECTIONS_JOB_KIND } from "../api/jobs";
import type { JobRecord } from "../api/types";
import { GenerationPanel, generationErrorText } from "./GenerationPanel";

function job(overrides: Partial<JobRecord> = {}): JobRecord {
  return {
    id: "job-1",
    organization_id: "org-1",
    conversation_id: "conversation-1",
    kind: GENERATE_SECTIONS_JOB_KIND,
    status: "running",
    progress: 40,
    attempt: 1,
    error_code: null,
    correlation_id: "corr-1",
    created_at: "2026-08-14T09:00:00Z",
    updated_at: "2026-08-14T09:00:00Z",
    started_at: "2026-08-14T09:00:01Z",
    finished_at: null,
    cancel_requested_at: null,
    ...overrides,
  };
}

describe("GenerationPanel", () => {
  it("maps public error codes", () => {
    expect(generationErrorText("provider_failed")).toBe(
      "The writing service did not finish.",
    );
    expect(generationErrorText("empty_output")).toBe("The draft was empty.");
    expect(generationErrorText("missing_section")).toBe("That section was missing.");
    expect(generationErrorText("revision_conflict")).toBe(
      "That section already changed.",
    );
    expect(generationErrorText("mystery")).toBe("That section could not be written.");
  });

  it("keeps the unavailable copy and no controls when reviewing", () => {
    render(<GenerationPanel sourceCount={2} reviewing />);
    const panel = screen.getByRole("complementary", {
      name: "Generate section drafts",
    });
    expect(
      screen.getByText(
        "Draft generation is not available yet. Sections are written and revised manually in the workspace.",
      ),
    ).toBeInTheDocument();
    expect(within(panel).queryAllByRole("button")).toHaveLength(0);
    expect(within(panel).queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("shows generate when live and empty drafts exist", () => {
    const onGenerate = vi.fn();
    render(
      <GenerationPanel
        sourceCount={1}
        emptyDraftCount={3}
        onGenerate={onGenerate}
      />,
    );
    screen.getByRole("button", { name: "Generate" }).click();
    expect(onGenerate).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("shows a progressbar and cancel while a job is in flight", () => {
    render(
      <GenerationPanel
        sourceCount={1}
        job={job()}
        emptyDraftCount={2}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
  });

  it("lists failed attempts with public error text and a retry control", () => {
    render(
      <GenerationPanel
        sourceCount={1}
        job={job({ status: "failed", progress: 50 })}
        attempts={[
          {
            section_number: "5",
            status: "failed",
            error_code: "provider_failed",
            citation_ids: [],
            attempt: 1,
          },
        ]}
        onRetryFailed={vi.fn()}
      />,
    );
    expect(screen.getByText(/Section 5 · failed/)).toBeInTheDocument();
    expect(
      screen.getByText("The writing service did not finish."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Retry failed sections" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/token/i)).not.toBeInTheDocument();
  });
});
