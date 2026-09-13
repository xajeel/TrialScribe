import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { RequestOptions } from "../api/client";
import type { EvidenceChunkRecord, M11Section } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { SectionReader, wordCountOf } from "./SectionReader";

function section(overrides: Partial<M11Section> = {}): M11Section {
  return {
    id: "section-1",
    conversation_id: "conversation-1",
    organization_id: "organization-1",
    catalog_version: "2025.1",
    section_number: "5",
    title: "Trial Population",
    position: 5,
    instructions: "Describe the population to be enrolled.",
    content: "Individuals must meet all inclusion criteria.",
    status: "draft",
    current_revision: 7,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-07-01T09:00:00Z",
    updated_at: "2026-07-31T11:20:00Z",
    ...overrides,
  };
}

function renderReader(value: M11Section) {
  const onOpenInEditor = vi.fn();
  const onAddInstruction = vi.fn();
  const onClose = vi.fn();
  render(
    <SectionReader
      section={value}
      returnFocusTo={null}
      onOpenInEditor={onOpenInEditor}
      onAddInstruction={onAddInstruction}
      onClose={onClose}
    />,
  );
  return { onOpenInEditor, onAddInstruction, onClose };
}

describe("SectionReader", () => {
  it("counts words over the stored content", () => {
    expect(wordCountOf("")).toBe(0);
    expect(wordCountOf("   ")).toBe(0);
    expect(wordCountOf("one two  three\nfour")).toBe(4);
  });

  it("shows instructions, prose, and real details for a draft", () => {
    renderReader(section());
    const dialog = screen.getByRole("dialog", { name: "Trial Population" });

    expect(within(dialog).getByText("Section 5")).toBeInTheDocument();
    expect(
      within(dialog).getByText("Describe the population to be enrolled."),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("Individuals must meet all inclusion criteria."),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("7")).toBeInTheDocument();
    expect(within(dialog).getByText("2025.1")).toBeInTheDocument();
    expect(within(dialog).getByText("6")).toBeInTheDocument();
    expect(
      within(dialog).getByRole("button", { name: "Open in editor" }),
    ).toBeInTheDocument();
  });

  it("locks a done section and exposes no editing control", () => {
    renderReader(
      section({
        status: "done",
        completed_at: "2026-07-30T17:05:00Z",
      }),
    );
    const dialog = screen.getByRole("dialog", { name: "Trial Population" });

    expect(within(dialog).getByText("Read only")).toBeInTheDocument();
    expect(
      within(dialog).getByText(/Reopen it from the editor/),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: "Open in editor" }),
    ).not.toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: "Add instruction" }),
    ).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    // A done section must not surface its instruction brief as if it still
    // applies to work in progress.
    expect(
      within(dialog).queryByText("Describe the population to be enrolled."),
    ).not.toBeInTheDocument();
  });

  it("offers both starting actions when the section is empty", () => {
    const { onOpenInEditor, onAddInstruction } = renderReader(
      section({ content: "   ", current_revision: 0 }),
    );
    const dialog = screen.getByRole("dialog", { name: "Trial Population" });

    expect(
      within(dialog).getByRole("heading", { name: "No content available" }),
    ).toBeInTheDocument();
    const empty = within(dialog).getByText(/This section has no content yet/);
    expect(empty).toBeInTheDocument();

    within(dialog)
      .getAllByRole("button", { name: "Open in editor" })[0]
      .click();
    expect(onOpenInEditor).toHaveBeenCalledTimes(1);

    within(dialog).getByRole("button", { name: "Add instruction" }).click();
    expect(onAddInstruction).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when no section is selected", () => {
    render(
      <SectionReader
        section={null}
        returnFocusTo={null}
        onOpenInEditor={vi.fn()}
        onAddInstruction={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens a citation onto trial data from the live inspector", async () => {
    const chunkId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    const chunk: EvidenceChunkRecord = {
      id: chunkId,
      conversation_id: "conversation-1",
      organization_id: "organization-1",
      source_kind: "trial_data",
      source_identity: "trial-1",
      page_number: null,
      start_char: 0,
      end_char: 12,
      text: "Age 18 years",
    };
    async function fetcher<T>(
      path: string,
      _options?: RequestOptions,
    ): Promise<T> {
      if (path.includes("evidence-chunks") && path.includes(chunkId)) {
        return { items: [chunk] } as T;
      }
      throw new Error(`unexpected ${path}`);
    }
    const user = userEvent.setup();
    render(
      <SectionReader
        section={section({
          content: `Individuals must be adults [cite:${chunkId}].`,
        })}
        returnFocusTo={null}
        onOpenInEditor={vi.fn()}
        onAddInstruction={vi.fn()}
        onClose={vi.fn()}
        inspectCitations={{
          fetcher: fetcher as AuthorizedFetch,
          organizationId: "organization-1",
          conversationId: "conversation-1",
        }}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: `Inspect citation ${chunkId}` }),
    );

    expect(await screen.findByRole("heading", { name: "Citation" })).toBeInTheDocument();
    expect(screen.getByText("Trial data")).toBeInTheDocument();
    expect(screen.getByText("Age 18 years")).toBeInTheDocument();
  });

  it("shows the missing copy for an unknown citation", async () => {
    const chunkId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    async function fetcher<T>(
      path: string,
      _options?: RequestOptions,
    ): Promise<T> {
      if (path.includes("evidence-chunks")) {
        return { items: [] } as T;
      }
      throw new Error(`unexpected ${path}`);
    }
    const user = userEvent.setup();
    render(
      <SectionReader
        section={section({ content: `[cite:${chunkId}]` })}
        returnFocusTo={null}
        onOpenInEditor={vi.fn()}
        onAddInstruction={vi.fn()}
        onClose={vi.fn()}
        inspectCitations={{
          fetcher: fetcher as AuthorizedFetch,
          organizationId: "organization-1",
          conversationId: "conversation-1",
        }}
      />,
    );

    await user.click(
      screen.getByRole("button", { name: `Inspect citation ${chunkId}` }),
    );

    expect(
      await screen.findByText("That source is not in this conversation."),
    ).toBeInTheDocument();
  });
});
