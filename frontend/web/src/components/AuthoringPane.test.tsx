import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { M11Section } from "../api/types";
import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import { AuthoringPane } from "./AuthoringPane";

const SECTION: M11Section = {
  id: "section-1",
  conversation_id: "conversation-1",
  organization_id: "org-1",
  catalog_version: "2025.1",
  section_number: "1",
  title: "Trial synopsis",
  position: 1,
  instructions: "",
  content: "Stored section text",
  status: "draft",
  current_revision: 1,
  completed_at: null,
  completed_by_account_id: null,
  created_at: "2026-08-01T09:00:00Z",
  updated_at: "2026-08-01T09:00:00Z",
};

function workspace(
  overrides: Partial<AuthoringWorkspaceController> = {},
): AuthoringWorkspaceController {
  return {
    conversationStatus: "ready",
    workspaceStatus: "ready",
    conversations: [
      {
        id: "conversation-1",
        organization_id: "org-1",
        owner_account_id: "account-1",
        title: "Protocol Alpha",
        status: "active",
        collaborator_account_ids: [],
        created_at: "2026-08-01T09:00:00Z",
        updated_at: "2026-08-01T09:00:00Z",
        last_activity_at: "2026-08-01T09:00:00Z",
        archived_at: null,
      },
    ],
    selectedConversationId: "conversation-1",
    selectedConversation: {
      id: "conversation-1",
      organization_id: "org-1",
      owner_account_id: "account-1",
      title: "Protocol Alpha",
      status: "active",
      collaborator_account_ids: [],
      created_at: "2026-08-01T09:00:00Z",
      updated_at: "2026-08-01T09:00:00Z",
      last_activity_at: "2026-08-01T09:00:00Z",
      archived_at: null,
    },
    messages: [],
    documents: [],
    sections: [SECTION],
    selectedSectionNumber: SECTION.section_number,
    selectedSection: SECTION,
    action: "idle",
    feedback: null,
    selectConversation: () => undefined,
    selectSection: () => undefined,
    retryConversations: () => undefined,
    retryWorkspace: () => undefined,
    dismissFeedback: () => undefined,
    create: () => Promise.resolve(false),
    rename: () => Promise.resolve(false),
    appendInstruction: () => Promise.resolve(false),
    upload: () => Promise.resolve(false),
    removeDocument: () => Promise.resolve(false),
    saveSection: () => Promise.resolve(false),
    restore: () => Promise.resolve(false),
    markDone: () => Promise.resolve(false),
    reopen: () => Promise.resolve(false),
    ...overrides,
  };
}

describe("AuthoringPane rewrite control", () => {
  it("opens a whole-section rewrite when the draft is saved", async () => {
    const user = userEvent.setup();
    const onRewrite = vi.fn();
    render(<AuthoringPane workspace={workspace()} onRewrite={onRewrite} />);

    await user.click(screen.getByRole("button", { name: "Rewrite section" }));
    expect(onRewrite).toHaveBeenCalledWith(null);
  });

  it("disables rewrite while there are unsaved changes", async () => {
    const user = userEvent.setup();
    render(<AuthoringPane workspace={workspace()} onRewrite={vi.fn()} />);

    await user.type(screen.getByLabelText("Section content"), " extra");
    expect(screen.getByRole("button", { name: "Rewrite section" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Rewrite section" })).toHaveAttribute(
      "title",
      "Save changes before rewriting",
    );
  });

  it("does not reuse a text selection after the section changes", async () => {
    const user = userEvent.setup();
    const onRewrite = vi.fn();
    const other: M11Section = {
      ...SECTION,
      id: "section-2",
      section_number: "2",
      title: "Trial population",
      content: "Stored section text also long enough",
    };
    const { rerender } = render(
      <AuthoringPane workspace={workspace()} onRewrite={onRewrite} />,
    );
    const textarea = screen.getByLabelText("Section content") as HTMLTextAreaElement;
    await user.click(textarea);
    (textarea as HTMLTextAreaElement).setSelectionRange(0, 7);
    fireEvent.select(textarea);
    await user.click(screen.getByRole("button", { name: "Rewrite section" }));
    expect(onRewrite).toHaveBeenCalledWith({ start: 0, end: 7 });

    onRewrite.mockClear();
    rerender(
      <AuthoringPane
        workspace={workspace({
          selectedSection: other,
          selectedSectionNumber: other.section_number,
          sections: [SECTION, other],
        })}
        onRewrite={onRewrite}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Rewrite section" }));
    expect(onRewrite).toHaveBeenCalledWith(null);
  });

  it("hides rewrite until a done section is reopened", () => {
    render(
      <AuthoringPane
        workspace={workspace({
          selectedSection: { ...SECTION, status: "done" },
        })}
        onRewrite={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: "Rewrite section" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reopen section" })).toBeInTheDocument();
  });
});
