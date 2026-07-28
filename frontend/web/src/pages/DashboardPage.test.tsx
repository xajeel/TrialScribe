import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
import { DashboardPage } from "./DashboardPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";

function conversation(id: string, title: string): Conversation {
  return {
    id,
    organization_id: ORGANIZATION_ID,
    owner_account_id: "00000000-0000-4000-8000-000000000020",
    title,
    status: "active",
    collaborator_account_ids: [],
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
    last_activity_at: "2026-07-28T09:00:00Z",
    archived_at: null,
  };
}

function message(
  conversationId: string,
  id: string,
  content: string,
): ConversationMessage {
  return {
    id,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    author_account_id: "00000000-0000-4000-8000-000000000020",
    role: "user",
    content,
    sequence: 1,
    created_at: "2026-07-28T09:01:00Z",
  };
}

function documentRecord(
  conversationId: string,
  id: string,
  filename: string,
): DocumentRecord {
  return {
    id,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: "00000000-0000-4000-8000-000000000020",
    kind: "research_document",
    filename,
    content_type: "application/pdf",
    byte_size: 2048,
    status: "ready",
    error: null,
    created_at: "2026-07-28T09:02:00Z",
    updated_at: "2026-07-28T09:02:00Z",
  };
}

function section(
  conversationId: string,
  id: string,
  title: string,
  content: string,
  overrides: Partial<M11Section> = {},
): M11Section {
  return {
    id,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: "1",
    title,
    position: 1,
    instructions: "Use precise protocol language.",
    content,
    status: "draft",
    current_revision: 0,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-07-28T09:03:00Z",
    updated_at: "2026-07-28T09:03:00Z",
    ...overrides,
  };
}

interface WorkspaceData {
  messages: ConversationMessage[];
  documents: DocumentRecord[];
  sections: M11Section[];
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

function readHandler(
  conversations: Conversation[],
  data: Record<string, WorkspaceData>,
) {
  return (path: string, options?: RequestOptions): unknown => {
    const method = options?.method ?? "GET";
    if (
      method === "GET" &&
      path === "/v1/ai/conversations?limit=100"
    ) {
      return { items: conversations, next_cursor: null };
    }
    const match = path.match(
      /^\/v1\/ai\/conversations\/([^/?]+)\/(messages|documents|m11-sections)/,
    );
    const conversationId = match?.[1];
    const resource = match?.[2];
    if (conversationId === undefined || resource === undefined) {
      throw new Error(`Unexpected request: ${method} ${path}`);
    }
    const workspace = data[conversationId];
    if (workspace === undefined) {
      throw new Error(`Missing fixture for ${conversationId}`);
    }
    if (resource === "messages" && method === "GET") {
      return { items: workspace.messages, next_cursor: null };
    }
    if (resource === "documents" && method === "GET") {
      return { items: workspace.documents, next_cursor: null };
    }
    if (resource === "m11-sections" && method === "PUT") {
      return { catalog_version: "2025.1", items: workspace.sections };
    }
    throw new Error(`Unexpected request: ${method} ${path}`);
  };
}

function renderDashboard(fetcher: AuthorizedFetch) {
  const auth: AuthContextValue = {
    status: "authenticated",
    account: {
      id: "00000000-0000-4000-8000-000000000020",
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
    <MemoryRouter>
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <DashboardPage />
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe("DashboardPage authoring workspace", () => {
  it("renders all three panes and independent scrolling regions", async () => {
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const { fetcher } = createFetcher(
      readHandler([alpha], {
        [alpha.id]: {
          messages: [message(alpha.id, "message-alpha", "Alpha instruction")],
          documents: [
            documentRecord(alpha.id, "document-alpha", "alpha.pdf"),
          ],
          sections: [
            section(
              alpha.id,
              "section-alpha",
              "Trial synopsis",
              "Alpha section content",
            ),
          ],
        },
      }),
    );

    renderDashboard(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Protocol Alpha" }),
    ).toBeInTheDocument();
    await screen.findByText("Alpha instruction");
    expect(
      screen.getByRole("navigation", { name: "Conversations" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "Sources & sections" }),
    ).toBeInTheDocument();
    for (const label of [
      "Conversation list",
      "Conversation messages",
      "Uploaded documents",
      "M11 section titles",
    ]) {
      expect(screen.getByLabelText(label)).toHaveClass("pane-scroll");
      expect(screen.getByLabelText(label)).toHaveAttribute("tabindex", "0");
    }
  });

  it("creates and switches conversations without accepting delayed stale data", async () => {
    const user = userEvent.setup();
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const beta = conversation("conversation-beta", "Protocol Beta");
    const gamma = conversation("conversation-gamma", "Protocol Gamma");
    const betaMessages = deferred<unknown>();
    const betaDocuments = deferred<unknown>();
    const betaSections = deferred<unknown>();
    const data: Record<string, WorkspaceData> = {
      [alpha.id]: {
        messages: [message(alpha.id, "message-alpha", "Alpha instruction")],
        documents: [
          documentRecord(alpha.id, "document-alpha", "alpha.pdf"),
        ],
        sections: [
          section(
            alpha.id,
            "section-alpha",
            "Alpha section",
            "Alpha section content",
          ),
        ],
      },
      [beta.id]: {
        messages: [message(beta.id, "message-beta", "Beta instruction")],
        documents: [documentRecord(beta.id, "document-beta", "beta.pdf")],
        sections: [
          section(
            beta.id,
            "section-beta",
            "Beta section",
            "Beta section content",
          ),
        ],
      },
      [gamma.id]: {
        messages: [],
        documents: [],
        sections: [
          section(gamma.id, "section-gamma", "Gamma section", ""),
        ],
      },
    };
    const base = readHandler([alpha, beta], data);
    const { fetcher, calls } = createFetcher((path, options) => {
      if (
        path === "/v1/ai/conversations" &&
        options?.method === "POST"
      ) {
        return gamma;
      }
      if (path.includes(`/${beta.id}/messages`)) {
        return betaMessages.promise;
      }
      if (path.includes(`/${beta.id}/documents`)) {
        return betaDocuments.promise;
      }
      if (path.includes(`/${beta.id}/m11-sections`)) {
        return betaSections.promise;
      }
      return base(path, options);
    });

    renderDashboard(fetcher);
    expect(await screen.findByText("Alpha instruction")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Protocol Beta/ }));
    expect(
      await screen.findByText("Loading this authoring workspace…"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Protocol Alpha/ }));
    expect(await screen.findByText("Alpha section content")).toBeInTheDocument();

    await act(async () => {
      betaMessages.resolve({
        items: data[beta.id].messages,
        next_cursor: null,
      });
      betaDocuments.resolve({
        items: data[beta.id].documents,
        next_cursor: null,
      });
      betaSections.resolve({
        catalog_version: "2025.1",
        items: data[beta.id].sections,
      });
      await Promise.all([
        betaMessages.promise,
        betaDocuments.promise,
        betaSections.promise,
      ]);
    });

    expect(screen.getByText("Alpha instruction")).toBeInTheDocument();
    expect(screen.getByText("alpha.pdf")).toBeInTheDocument();
    expect(screen.queryByText("Beta instruction")).not.toBeInTheDocument();
    expect(screen.queryByText("beta.pdf")).not.toBeInTheDocument();

    await user.type(
      screen.getByLabelText("New conversation"),
      "Protocol Gamma",
    );
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(
      await screen.findByRole("heading", { name: "Protocol Gamma" }),
    ).toBeInTheDocument();
    const createCall = calls.find(
      (call) =>
        call.path === "/v1/ai/conversations" &&
        call.options?.method === "POST",
    );
    expect(new Headers(createCall?.options?.headers)).toHaveProperty(
      "get",
    );
    expect(
      new Headers(createCall?.options?.headers).get("X-Organization-ID"),
    ).toBe(ORGANIZATION_ID);
  });

  it("persists instructions and revision-safe section transitions", async () => {
    const user = userEvent.setup();
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    let currentSection = section(
      alpha.id,
      "section-alpha",
      "Trial synopsis",
      "Initial section content",
    );
    const workspaceData: WorkspaceData = {
      messages: [],
      documents: [],
      sections: [currentSection],
    };
    const base = readHandler([alpha], { [alpha.id]: workspaceData });
    const { fetcher, calls } = createFetcher((path, options) => {
      if (
        path.endsWith(`/${alpha.id}/messages`) &&
        options?.method === "POST"
      ) {
        return message(
          alpha.id,
          "message-new",
          (options.json as { content: string }).content,
        );
      }
      if (
        path.endsWith(`/${currentSection.section_number}`) &&
        options?.method === "PATCH"
      ) {
        const body = options.json as {
          expected_revision: number;
          instructions: string;
          content: string;
        };
        currentSection = {
          ...currentSection,
          instructions: body.instructions,
          content: body.content,
          current_revision: body.expected_revision + 1,
        };
        return currentSection;
      }
      if (path.endsWith("/done") && options?.method === "POST") {
        currentSection = {
          ...currentSection,
          status: "done",
          current_revision: currentSection.current_revision + 1,
          completed_at: "2026-07-28T10:00:00Z",
        };
        return currentSection;
      }
      if (path.endsWith("/reopen") && options?.method === "POST") {
        currentSection = {
          ...currentSection,
          status: "draft",
          current_revision: currentSection.current_revision + 1,
          completed_at: null,
        };
        return currentSection;
      }
      return base(path, options);
    });

    renderDashboard(fetcher);
    await screen.findByRole("heading", { name: "Protocol Alpha" });

    await user.type(
      await screen.findByLabelText("Add an instruction"),
      "Use the latest eligibility criteria.",
    );
    await user.click(
      screen.getByRole("button", { name: "Save instruction" }),
    );
    expect(
      await screen.findByText("Use the latest eligibility criteria."),
    ).toBeInTheDocument();

    const instructions = screen.getByLabelText("Section instructions");
    const content = screen.getByLabelText("Section content");
    await user.clear(instructions);
    await user.type(instructions, "Use concise language.");
    await user.clear(content);
    await user.type(content, "Updated complete section.");
    await user.click(screen.getByRole("button", { name: "Save section" }));
    expect(await screen.findByText("Revision 1")).toBeInTheDocument();

    const patchCall = calls.find(
      (call) => call.options?.method === "PATCH",
    );
    expect(patchCall?.options?.json).toEqual({
      expected_revision: 0,
      instructions: "Use concise language.",
      content: "Updated complete section.",
    });

    await user.click(screen.getByRole("button", { name: "Mark done" }));
    expect(
      await screen.findByRole("button", { name: "Reopen section" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Section content")).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Reopen section" }));
    expect(
      await screen.findByRole("button", { name: "Mark done" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Section content")).toBeEnabled();
  });

  it("uploads multipart files with contextual pending and success feedback", async () => {
    const user = userEvent.setup();
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const uploaded = deferred<unknown>();
    const data: WorkspaceData = {
      messages: [],
      documents: [],
      sections: [
        section(alpha.id, "section-alpha", "Trial synopsis", ""),
      ],
    };
    const base = readHandler([alpha], { [alpha.id]: data });
    const { fetcher, calls } = createFetcher((path, options) => {
      if (
        path.endsWith(`/${alpha.id}/documents`) &&
        options?.method === "POST"
      ) {
        return uploaded.promise;
      }
      return base(path, options);
    });
    renderDashboard(fetcher);
    await screen.findByRole("heading", { name: "Protocol Alpha" });

    await user.selectOptions(screen.getByLabelText("Document kind"), "trial_data");
    const file = new File(['{"trial":"TS-1"}'], "trial.json", {
      type: "application/json",
    });
    await user.upload(screen.getByLabelText("Choose file"), file);
    const uploadButton = screen.getByRole("button", { name: "Upload" });
    expect(uploadButton).toBeEnabled();
    fireEvent.submit(uploadButton.closest("form") as HTMLFormElement);
    expect(await screen.findByText("Uploading document…")).toBeInTheDocument();

    const uploadCall = calls.find(
      (call) =>
        call.path.endsWith(`/${alpha.id}/documents`) &&
        call.options?.method === "POST",
    );
    const headers = new Headers(uploadCall?.options?.headers);
    expect(headers.get("X-Organization-ID")).toBe(ORGANIZATION_ID);
    expect(headers.has("Content-Type")).toBe(false);
    expect(uploadCall?.options?.body).toBeInstanceOf(FormData);
    const body = uploadCall?.options?.body as FormData;
    expect(body.get("kind")).toBe("trial_data");
    expect((body.get("file") as File).name).toBe("trial.json");

    await act(async () => {
      uploaded.resolve({
        ...documentRecord(alpha.id, "document-uploaded", "trial.json"),
        kind: "trial_data",
        content_type: "application/json",
      });
      await uploaded.promise;
    });
    expect(
      await screen.findByText("trial.json uploaded successfully."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Trial data/)).toBeInTheDocument();
  });

  it("opens full section content in a modal and returns focus on close", async () => {
    const user = userEvent.setup();
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const { fetcher } = createFetcher(
      readHandler([alpha], {
        [alpha.id]: {
          messages: [],
          documents: [],
          sections: [
            section(
              alpha.id,
              "section-alpha",
              "Trial synopsis",
              "The complete protocol synopsis appears here.",
            ),
          ],
        },
      }),
    );
    renderDashboard(fetcher);
    const opener = await screen.findByRole("button", {
      name: "Open full section",
    });

    await user.click(opener);
    const dialog = await screen.findByRole("dialog", {
      name: "Trial synopsis",
    });
    expect(
      within(dialog).getByText(
        "The complete protocol synopsis appears here.",
      ),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(opener).toHaveFocus();
  });

  it("shows loading, fixed public errors, retry, and empty states", async () => {
    const user = userEvent.setup();
    const firstList = deferred<unknown>();
    let listAttempts = 0;
    const { fetcher } = createFetcher((path, options) => {
      if (
        path === "/v1/ai/conversations?limit=100" &&
        (options?.method ?? "GET") === "GET"
      ) {
        listAttempts += 1;
        if (listAttempts === 1) {
          return firstList.promise;
        }
        return { items: [], next_cursor: null };
      }
      throw new Error(`Unexpected request: ${path}`);
    });
    renderDashboard(fetcher);

    expect(
      await screen.findByText("Loading conversations…"),
    ).toBeInTheDocument();
    await act(async () => {
      firstList.reject(new Error("database password leaked"));
      try {
        await firstList.promise;
      } catch {
        // The component deliberately replaces the raw failure with fixed copy.
      }
    });
    expect(
      await screen.findByText("Could not load conversations."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/database password leaked/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No conversations yet")).toBeInTheDocument();
    expect(screen.getByText("Create a conversation")).toBeInTheDocument();
  });
});
