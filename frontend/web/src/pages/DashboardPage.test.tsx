import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
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

function renderDashboard(
  fetcher: AuthorizedFetch,
  conversationId?: string,
) {
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
    <MemoryRouter
      initialEntries={[
        conversationId === undefined
          ? "/workspace"
          : `/workspace/${conversationId}`,
      ]}
    >
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <Routes>
            <Route path="/workspace" element={<DashboardPage />} />
            <Route
              path="/workspace/:conversationId"
              element={<DashboardPage />}
            />
          </Routes>
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
      await screen.findByRole("button", { name: /Protocol Alpha/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "TrialScribe protocols" }),
    ).toHaveAttribute("href", "/protocols");
    expect(
      screen.getByRole("link", { name: "TrialScribe protocols" }),
    ).toHaveClass("brand-logo");
    expect(
      screen.getByRole("navigation", { name: "Protocol workspaces" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "Sources and sections" }),
    ).toBeInTheDocument();

    // The centre presents the section as a document; the outline lists all of
    // them; the rail lists the protocols.
    expect(
      await screen.findByRole("heading", { name: "1 · Trial synopsis" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Protocol list")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Outline" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // Instructions live behind the centre's second view.
    expect(screen.queryByText("Alpha instruction")).not.toBeInTheDocument();
    await userEvent.setup().click(
      screen.getByRole("button", { name: "Instructions" }),
    );
    expect(await screen.findByText("Alpha instruction")).toBeInTheDocument();
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
    expect(
      await screen.findByText("Alpha section content"),
    ).toBeInTheDocument();

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

    // The slow Beta responses must not overwrite the reselected Alpha.
    expect(screen.getByText("Alpha section content")).toBeInTheDocument();
    expect(screen.queryByText("Beta section content")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Sources" }));
    expect(screen.getByText("alpha.pdf")).toBeInTheDocument();
    expect(screen.queryByText("beta.pdf")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Instructions" }));
    expect(screen.getByText("Alpha instruction")).toBeInTheDocument();
    expect(screen.queryByText("Beta instruction")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Document" }));

    await user.click(screen.getByRole("button", { name: "New protocol" }));
    await user.type(
      screen.getByLabelText("New protocol title"),
      "Protocol Gamma",
    );
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(
      await screen.findByRole("button", { name: /Protocol Gamma/ }),
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
    await screen.findByRole("button", { name: /Protocol Alpha/ });

    await user.click(screen.getByRole("button", { name: "Instructions" }));
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

    await user.click(screen.getByRole("button", { name: "Document" }));
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

  it("sends uploads to the source library instead of the workbench", async () => {
    const user = userEvent.setup();
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const { fetcher } = createFetcher(
      readHandler([alpha], {
        [alpha.id]: {
          messages: [],
          documents: [
            documentRecord(alpha.id, "document-alpha", "alpha.pdf"),
          ],
          sections: [section(alpha.id, "section-alpha", "Trial synopsis", "")],
        },
      }),
    );
    renderDashboard(fetcher);
    await screen.findByRole("button", { name: /Protocol Alpha/ });
    await user.click(screen.getByRole("tab", { name: "Sources" }));
    expect(await screen.findByText("alpha.pdf")).toBeInTheDocument();

    // Uploading is the source library's job, so the workbench offers no file
    // input of its own — only a route to the surface that owns it.
    expect(screen.queryByLabelText("Choose file")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Upload" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage" })).toHaveAttribute(
      "href",
      `/workspace/${alpha.id}/sources`,
    );
  });

  it("opens full section content in a reader and returns focus on close", async () => {
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
    await screen.findByRole("button", { name: /Protocol Alpha/ });
    const opener = await screen.findByRole("button", {
      name: "Read Trial synopsis",
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
      await screen.findByText("Loading protocols…"),
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
      await screen.findByText("Could not load protocols."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/database password leaked/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Create a protocol")).toBeInTheDocument();
    expect(
      screen.getByText(/Your durable instructions, sources, and M11 sections/),
    ).toBeInTheDocument();
  });
  it("opens the protocol named in the route instead of the first one", async () => {
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const beta = conversation("conversation-beta", "Protocol Beta");
    const { fetcher } = createFetcher(
      readHandler([alpha, beta], {
        [alpha.id]: { messages: [], documents: [], sections: [] },
        [beta.id]: {
          messages: [message(beta.id, "message-beta", "Beta instruction")],
          documents: [documentRecord(beta.id, "document-beta", "beta.pdf")],
          sections: [
            section(beta.id, "section-beta", "Trial synopsis", "Beta content"),
          ],
        },
      }),
    );

    renderDashboard(fetcher, beta.id);

    expect(
      await screen.findByRole("button", { name: /Protocol Beta/ }),
    ).toBeInTheDocument();
    await userEvent.setup().click(
      screen.getByRole("button", { name: "Instructions" }),
    );
    expect(await screen.findByText("Beta instruction")).toBeInTheDocument();
  });

  it("opens and closes each side pane as a drawer", async () => {
    const user = userEvent.setup();
    const alpha = conversation("conversation-alpha", "Protocol Alpha");
    const { fetcher } = createFetcher(
      readHandler([alpha], {
        [alpha.id]: {
          messages: [],
          documents: [],
          sections: [section(alpha.id, "section-alpha", "Trial synopsis", "")],
        },
      }),
    );
    renderDashboard(fetcher);
    await screen.findByRole("button", { name: /Protocol Alpha/ });

    const protocols = screen.getByRole("button", { name: "Protocols" });
    const resources = screen.getByRole("button", { name: "Outline & sources" });
    expect(protocols).toHaveAttribute("aria-expanded", "false");
    expect(resources).toHaveAttribute("aria-expanded", "false");

    await user.click(resources);
    expect(resources).toHaveAttribute("aria-expanded", "true");

    // Opening one drawer closes the other, so they never overlap.
    await user.click(protocols);
    expect(protocols).toHaveAttribute("aria-expanded", "true");
    expect(resources).toHaveAttribute("aria-expanded", "false");

    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(protocols).toHaveAttribute("aria-expanded", "false"),
    );
  });

  it("shows the empty and populated source groups in the resource pane", async () => {
    const empty = conversation("conversation-empty", "Protocol Empty");
    const filled = conversation("conversation-filled", "Protocol Filled");
    const fixtures = {
      [empty.id]: { messages: [], documents: [], sections: [] },
      [filled.id]: {
        messages: [],
        documents: [
          documentRecord(filled.id, "document-filled", "filled.pdf"),
        ],
        sections: [],
      },
    };

    const { fetcher } = createFetcher(readHandler([empty, filled], fixtures));
    const { unmount } = renderDashboard(fetcher, empty.id);

    await userEvent.setup().click(
      await screen.findByRole("tab", { name: "Sources" }),
    );
    expect(
      await screen.findByText("No research documents added."),
    ).toBeInTheDocument();
    expect(screen.getByText("No trial data added.")).toBeInTheDocument();
    unmount();

    const second = createFetcher(readHandler([empty, filled], fixtures));
    renderDashboard(second.fetcher, filled.id);

    await userEvent.setup().click(
      await screen.findByRole("tab", { name: "Sources" }),
    );
    expect(await screen.findByText("filled.pdf")).toBeInTheDocument();
    expect(
      screen.queryByText("No research documents added."),
    ).not.toBeInTheDocument();
  });
});
