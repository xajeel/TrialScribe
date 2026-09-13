import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type {
  Conversation,
  ConversationMessage,
  DocumentRecord,
  M11Section,
} from "../api/types";
import {
  AuthContext,
  type AuthContextValue,
  type AuthorizedFetch,
} from "../auth/AuthContext";
import {
  OrganizationContext,
  type OrganizationContextValue,
} from "../org/OrganizationContext";
import { WorkspaceInstructionsPage } from "./WorkspaceInstructionsPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const ACCOUNT_ID = "00000000-0000-4000-8000-000000000020";
const TEAMMATE_ID = "00000000-0000-4000-8000-000000000021";
const CONVERSATION_ID = "c-aurora";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    owner_account_id: ACCOUNT_ID,
    title: "AURORA-301",
    status: "active",
    collaborator_account_ids: [],
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
    last_activity_at: "2026-07-28T09:00:00Z",
    archived_at: null,
    ...overrides,
  };
}

function message(
  sequence: number,
  content: string,
  authorId: string = ACCOUNT_ID,
): ConversationMessage {
  return {
    id: `m-${sequence}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    author_account_id: authorId,
    role: "user",
    content,
    sequence,
    created_at: "2026-07-28T09:00:00Z",
  };
}

function documentRecord(id: string): DocumentRecord {
  return {
    id,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: ACCOUNT_ID,
    kind: "research_document",
    filename: `${id}.pdf`,
    content_type: "application/pdf",
    byte_size: 2048,
    status: "ready",
    error: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

interface FetchCall {
  path: string;
  options: RequestOptions | undefined;
}

function createFetcher(
  handler: (
    path: string,
    options: RequestOptions | undefined,
  ) => unknown | Promise<unknown>,
): { fetcher: AuthorizedFetch; calls: FetchCall[] } {
  const calls: FetchCall[] = [];
  async function fetcher<T>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> {
    calls.push({ path, options });
    return (await handler(path, options)) as T;
  }
  return { fetcher, calls };
}

function draftSection(number: string, content = ""): M11Section {
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
    status: "draft",
    current_revision: content.trim() === "" ? 0 : 1,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

function queuedJob() {
  return {
    id: "job-gen-1",
    organization_id: ORGANIZATION_ID,
    conversation_id: CONVERSATION_ID,
    kind: "generate_sections",
    status: "queued",
    progress: 0,
    attempt: 0,
    error_code: null,
    correlation_id: "corr-1",
    created_at: "2026-08-14T09:00:00Z",
    updated_at: "2026-08-14T09:00:00Z",
    started_at: null,
    finished_at: null,
    cancel_requested_at: null,
  };
}

function workspaceHandler(
  instructions: ConversationMessage[],
  documents: DocumentRecord[] = [documentRecord("doc-1")],
  record: Conversation = conversation(),
  sections: M11Section[] = [],
) {
  return (path: string, options?: RequestOptions): unknown => {
    const method = options?.method ?? "GET";
    if (path === "/v1/jobs" && method === "POST") {
      return queuedJob();
    }
    if (path.endsWith("/cancel") && path.startsWith("/v1/jobs/")) {
      return { ...queuedJob(), status: "cancelled" };
    }
    if (path.endsWith("/attempts") && path.startsWith("/v1/jobs/")) {
      return { items: [] };
    }
    if (path.startsWith("/v1/jobs")) {
      return { items: [] };
    }
    if (path.includes("/messages")) {
      if (method === "POST") {
        const body = options?.json as { content: string };
        return message(instructions.length + 1, body.content);
      }
      return { items: instructions, next_cursor: null };
    }
    if (path.includes("/documents")) {
      return { items: documents, next_cursor: null };
    }
    if (path.includes("/m11-sections")) {
      return { catalog_version: "2025.1", items: sections };
    }
    if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
      return record;
    }
    throw new Error(`Unexpected request: ${method} ${path}`);
  };
}

function renderInstructions(fetcher: AuthorizedFetch) {
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
    <MemoryRouter
      initialEntries={[`/workspace/${CONVERSATION_ID}/instructions`]}
    >
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <Routes>
            <Route
              path="/workspace/:conversationId/instructions"
              element={<WorkspaceInstructionsPage />}
            />
          </Routes>
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("WorkspaceInstructionsPage", () => {
  it("lists saved instructions oldest first with their author", async () => {
    const { fetcher } = createFetcher(
      workspaceHandler([
        message(2, "Second instruction", TEAMMATE_ID),
        message(1, "First instruction"),
      ]),
    );

    renderInstructions(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Writing instructions" }),
    ).toBeInTheDocument();
    const entries = within(
      screen.getByRole("list", { name: "Saved instructions" }),
    ).getAllByRole("listitem");
    expect(entries[0]).toHaveTextContent("First instruction");
    expect(entries[0]).toHaveTextContent("You");
    expect(entries[1]).toHaveTextContent("Second instruction");
    expect(entries[1]).toHaveTextContent("Team member");
  });

  it("shows the tab bar with instructions marked current", async () => {
    const { fetcher } = createFetcher(workspaceHandler([message(1, "One")]));

    renderInstructions(fetcher);

    const tab = await screen.findByRole("link", { name: "Instructions" });
    expect(tab).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Progress" })).toHaveAttribute(
      "href",
      `/workspace/${CONVERSATION_ID}/progress`,
    );
    expect(screen.getByRole("link", { name: "Workspace" })).toHaveAttribute(
      "href",
      `/workspace/${CONVERSATION_ID}`,
    );
  });

  it("renders the empty state with labelled examples when nothing is saved", async () => {
    const { fetcher } = createFetcher(workspaceHandler([]));

    renderInstructions(fetcher);

    expect(
      await screen.findByRole("heading", { name: "No saved instructions" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Tone")).toBeInTheDocument();
    expect(screen.getByText("Compliance")).toBeInTheDocument();
    expect(screen.getByText("Terminology")).toBeInTheDocument();
    // The examples must never read as content already saved to the protocol.
    expect(
      screen.getByText(
        "These are examples only. Nothing above is saved to this protocol.",
      ),
    ).toBeInTheDocument();
  });

  it("saves a new instruction and clears the field", async () => {
    const { fetcher } = createFetcher(workspaceHandler([message(1, "One")]));
    const user = userEvent.setup();

    renderInstructions(fetcher);
    const field = await screen.findByLabelText("Add a workspace instruction");

    await user.type(field, "Cite the investigator brochure.");
    await user.click(screen.getByRole("button", { name: "Save instruction" }));

    expect(
      await screen.findByText("Cite the investigator brochure."),
    ).toBeInTheDocument();
    expect(field).toHaveValue("");
    expect(screen.getByText("Instruction saved.")).toBeInTheDocument();
  });

  it("rejects a blank instruction without issuing a request", async () => {
    const { fetcher, calls } = createFetcher(
      workspaceHandler([message(1, "One")]),
    );
    const user = userEvent.setup();

    renderInstructions(fetcher);
    await screen.findByLabelText("Add a workspace instruction");
    const before = calls.length;

    await user.click(screen.getByRole("button", { name: "Save instruction" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Enter an instruction.",
    );
    expect(calls).toHaveLength(before);
  });

  it("keeps the typed instruction and shows a fixed message when saving fails", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path.includes("/messages") && options?.method === "POST") {
        throw new Error("network");
      }
      return workspaceHandler([message(1, "One")])(path, options);
    });
    const user = userEvent.setup();

    renderInstructions(fetcher);
    const field = await screen.findByLabelText("Add a workspace instruction");

    await user.type(field, "Rejected instruction");
    await user.click(screen.getByRole("button", { name: "Save instruction" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not save the instruction. Please try again.",
    );
    expect(field).toHaveValue("Rejected instruction");
  });

  it("offers a working retry when the workspace fails to load", async () => {
    let attempt = 0;
    const { fetcher } = createFetcher((path, options) => {
      if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
        attempt += 1;
        if (attempt === 1) {
          throw new Error("network");
        }
      }
      return workspaceHandler([message(1, "First instruction")])(path, options);
    });
    const user = userEvent.setup();

    renderInstructions(fetcher);

    expect(
      await screen.findByText("Could not load this protocol workspace."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("First instruction")).toBeInTheDocument();
  });

  it("starts generation for empty drafts from the live panel", async () => {
    const { fetcher, calls } = createFetcher(
      workspaceHandler(
        [message(1, "One")],
        [documentRecord("doc-1")],
        conversation(),
        [draftSection("1"), draftSection("2", "Already written")],
      ),
    );
    const user = userEvent.setup();

    renderInstructions(fetcher);

    const generate = await screen.findByRole("button", { name: "Generate" });
    await user.click(generate);

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.path === "/v1/jobs" &&
            call.options?.method === "POST" &&
            (call.options.json as { kind?: string }).kind === "generate_sections",
        ),
      ).toBe(true);
    });
    const created = calls.find(
      (call) => call.path === "/v1/jobs" && call.options?.method === "POST",
    );
    expect(created?.options?.json).toMatchObject({
      kind: "generate_sections",
      conversation_id: CONVERSATION_ID,
      parameters: {
        section_numbers: ["1"],
        expected_revisions: { "1": 0 },
      },
    });
  });

  it("keeps the unavailable copy and no generate control on the review route", async () => {
    const { fetcher } = createFetcher(() => {
      throw new Error("review routes must not fetch");
    });
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
      organizations: [],
      activeId: null,
      action: "idle",
      feedback: null,
      select: () => undefined,
      reload: () => undefined,
      create: async () => true,
      join: async () => true,
      dismissFeedback: () => undefined,
    };

    render(
      <MemoryRouter>
        <AuthContext.Provider value={auth}>
          <OrganizationContext.Provider value={organization}>
            <WorkspaceInstructionsPage review="populated" />
          </OrganizationContext.Provider>
        </AuthContext.Provider>
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Generate section drafts" }),
    ).toBeInTheDocument();
    const panel = screen.getByRole("complementary", {
      name: "Generate section drafts",
    });
    expect(
      screen.getByText(
        "Draft generation is not available yet. Sections are written and revised manually in the workspace.",
      ),
    ).toBeInTheDocument();
    expect(within(panel).queryAllByRole("button")).toHaveLength(0);
    expect(
      screen.queryByRole("button", { name: /generate/i }),
    ).not.toBeInTheDocument();
  });

  it("shows no fabricated percentage, token, or currency figure", async () => {
    const { fetcher } = createFetcher(workspaceHandler([message(1, "One")]));

    renderInstructions(fetcher);
    await screen.findByRole("heading", { name: "Writing instructions" });

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d+%/);
    expect(text).not.toMatch(/\$\d/);
    expect(text).not.toMatch(/token/i);
  });

  it("disables the composer for an archived protocol", async () => {
    const { fetcher } = createFetcher(
      workspaceHandler(
        [message(1, "One")],
        [documentRecord("doc-1")],
        conversation({ status: "archived", archived_at: "2026-07-30T09:00:00Z" }),
      ),
    );

    renderInstructions(fetcher);

    await waitFor(() => {
      expect(
        screen.getByLabelText("Add a workspace instruction"),
      ).toBeDisabled();
    });
    expect(
      screen.getByText(
        "This protocol is archived. Restore it from the library to add instructions.",
      ),
    ).toBeInTheDocument();
  });
});
