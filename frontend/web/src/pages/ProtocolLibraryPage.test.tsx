import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type { Conversation, DocumentRecord, M11Section } from "../api/types";
import {
  AuthContext,
  type AuthContextValue,
  type AuthorizedFetch,
} from "../auth/AuthContext";
import {
  OrganizationContext,
  type OrganizationContextValue,
} from "../org/OrganizationContext";
import { ProtocolLibraryPage } from "./ProtocolLibraryPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";

function conversation(
  id: string,
  title: string,
  overrides: Partial<Conversation> = {},
): Conversation {
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
    ...overrides,
  };
}

function section(
  conversationId: string,
  number: string,
  status: M11Section["status"],
): M11Section {
  return {
    id: `${conversationId}-${number}`,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: number,
    title: `Section ${number}`,
    position: Number(number),
    instructions: "",
    content: "",
    status,
    current_revision: 0,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

function documentRecord(
  conversationId: string,
  id: string,
  status: DocumentRecord["status"] = "ready",
): DocumentRecord {
  return {
    id,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: null,
    kind: "research_document",
    filename: `${id}.pdf`,
    content_type: "application/pdf",
    byte_size: 2048,
    status,
    error: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

interface Fixture {
  sections: M11Section[];
  documents: DocumentRecord[];
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

function libraryHandler(
  active: Conversation[],
  fixtures: Record<string, Fixture> = {},
  archived: Conversation[] = [],
) {
  return (path: string, options?: RequestOptions): unknown => {
    const method = options?.method ?? "GET";
    if (path.startsWith("/v1/ai/conversations?")) {
      return {
        items: path.includes("archived=true") ? archived : active,
        next_cursor: null,
      };
    }
    const match = path.match(
      /^\/v1\/ai\/conversations\/([^/?]+)(?:\/(m11-sections|documents|restore))?/,
    );
    const conversationId = match?.[1];
    const resource = match?.[2];
    if (conversationId === undefined) {
      throw new Error(`Unexpected request: ${method} ${path}`);
    }
    if (resource === "m11-sections") {
      return {
        catalog_version: "2025.1",
        items: fixtures[conversationId]?.sections ?? [],
      };
    }
    if (resource === "documents") {
      return {
        items: fixtures[conversationId]?.documents ?? [],
        next_cursor: null,
      };
    }
    if (method === "DELETE" || resource === "restore") {
      return (
        [...active, ...archived].find((item) => item.id === conversationId) ??
        conversation(conversationId, "Unknown")
      );
    }
    throw new Error(`Unexpected request: ${method} ${path}`);
  };
}

function renderLibrary(
  fetcher: AuthorizedFetch,
  organizations: OrganizationContextValue["organizations"] = [
    {
      id: ORGANIZATION_ID,
      name: "Acme Trials",
      role: "owner",
      created_at: "2026-07-28T08:00:00Z",
    },
  ],
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
    organizations,
    activeId: organizations[0]?.id ?? null,
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
          <ProtocolLibraryPage />
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("ProtocolLibraryPage", () => {
  it("lists protocols and links each row to its workspace", async () => {
    const aurora = conversation("c-aurora", "AURORA-301");
    const { fetcher } = createFetcher(
      libraryHandler([aurora], {
        [aurora.id]: {
          sections: [
            section(aurora.id, "1", "done"),
            section(aurora.id, "2", "draft"),
          ],
          documents: [documentRecord(aurora.id, "doc-1")],
        },
      }),
    );

    renderLibrary(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Protocol workspaces" }),
    ).toBeInTheDocument();
    // Named in the header switcher and again as the page eyebrow.
    expect(screen.getAllByText("Acme Trials")).toHaveLength(2);
    const link = await screen.findByRole("link", { name: "AURORA-301" });
    expect(link).toHaveAttribute("href", "/workspace/c-aurora");
    expect(await screen.findByText("1 of 2 complete")).toBeInTheDocument();
    expect(await screen.findByText("1 source")).toBeInTheDocument();
  });

  it("shows no sources when a protocol has none", async () => {
    const empty = conversation("c-empty", "PATHWAY-404");
    const { fetcher } = createFetcher(libraryHandler([empty]));

    renderLibrary(fetcher);

    expect(await screen.findByText("No sources")).toBeInTheDocument();
  });

  it("filters by search and sorts by title", async () => {
    const { fetcher } = createFetcher(
      libraryHandler([
        conversation("c-1", "AURORA-301", {
          last_activity_at: "2026-07-20T09:00:00Z",
        }),
        conversation("c-2", "LUMEN-204", {
          last_activity_at: "2026-07-28T09:00:00Z",
        }),
      ]),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    const rows = () =>
      screen
        .getAllByRole("row")
        .slice(1)
        .map((row) => within(row).getByRole("link").textContent);
    expect(rows()).toEqual(["LUMEN-204", "AURORA-301"]);

    await user.selectOptions(screen.getByLabelText("Sort by"), "title");
    expect(rows()).toEqual(["AURORA-301", "LUMEN-204"]);

    await user.type(screen.getByLabelText("Search protocols"), "lumen");
    expect(rows()).toEqual(["LUMEN-204"]);
  });

  it("shows a search message when nothing matches", async () => {
    const { fetcher } = createFetcher(
      libraryHandler([conversation("c-1", "AURORA-301")]),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    await user.type(screen.getByLabelText("Search protocols"), "zzz");

    expect(
      await screen.findByText("No protocols match your search."),
    ).toBeInTheDocument();
  });

  it("requests archived protocols from the filter", async () => {
    const { fetcher, calls } = createFetcher(
      libraryHandler(
        [conversation("c-1", "AURORA-301")],
        {},
        [conversation("c-2", "ORBIT registry", { status: "archived" })],
      ),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    await user.click(screen.getByRole("button", { name: "Archived" }));

    expect(
      await screen.findByRole("link", { name: "ORBIT registry" }),
    ).toBeInTheDocument();
    expect(
      calls.some((call) => call.path.includes("archived=true")),
    ).toBe(true);
    expect(screen.getAllByText("Archived").length).toBeGreaterThan(0);
  });

  it("shows the fixed load failure with a working retry", async () => {
    let attempt = 0;
    const { fetcher } = createFetcher((path, options) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        attempt += 1;
        if (attempt === 1) {
          throw new Error("network");
        }
      }
      return libraryHandler([conversation("c-1", "AURORA-301")])(
        path,
        options,
      );
    });
    const user = userEvent.setup();

    renderLibrary(fetcher);

    expect(
      await screen.findByText("Could not load protocol workspaces."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(
      await screen.findByRole("link", { name: "AURORA-301" }),
    ).toBeInTheDocument();
  });

  it("shows the first-protocol empty state with its step sequence", async () => {
    const { fetcher } = createFetcher(libraryHandler([]));

    renderLibrary(fetcher);

    expect(
      await screen.findByRole("heading", {
        name: "Create your first protocol workspace",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Create workspace")).toBeInTheDocument();
    expect(screen.getByText("Add sources")).toBeInTheDocument();
    expect(screen.getByText("Draft sections")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create protocol" }),
    ).toBeInTheDocument();
  });

  it("offers only API-backed row actions", async () => {
    const { fetcher } = createFetcher(
      libraryHandler([conversation("c-1", "AURORA-301")]),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    await user.click(
      screen.getByRole("button", { name: "Actions for AURORA-301" }),
    );

    expect(
      screen.getByRole("link", { name: "Open workspace" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Rename" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archive" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Writing instructions" }),
    ).toHaveAttribute("href", "/workspace/c-1/instructions");
    expect(screen.queryByText("Export")).not.toBeInTheDocument();
    expect(screen.queryByText("View usage")).not.toBeInTheDocument();
  });

  it("confirms an archive, removes the row, and returns focus", async () => {
    const { fetcher, calls } = createFetcher(
      libraryHandler([conversation("c-1", "AURORA-301")]),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    const trigger = screen.getByRole("button", {
      name: "Actions for AURORA-301",
    });
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Archive" }));

    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(
        "Existing content stays readable, but authoring actions are disabled.",
      ),
    ).toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("button", { name: "Archive protocol" }),
    );

    await waitFor(() =>
      expect(
        screen.queryByRole("link", { name: "AURORA-301" }),
      ).not.toBeInTheDocument(),
    );
    expect(
      calls.some(
        (call) =>
          call.path === "/v1/ai/conversations/c-1" &&
          call.options?.method === "DELETE",
      ),
    ).toBe(true);
    expect(await screen.findByText("AURORA-301 archived.")).toBeInTheDocument();
  });

  it("cancels an archive without calling the API", async () => {
    const { fetcher, calls } = createFetcher(
      libraryHandler([conversation("c-1", "AURORA-301")]),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    await user.click(
      screen.getByRole("button", { name: "Actions for AURORA-301" }),
    );
    await user.click(screen.getByRole("button", { name: "Archive" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Cancel",
      }),
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "AURORA-301" }),
    ).toBeInTheDocument();
    expect(
      calls.some((call) => call.options?.method === "DELETE"),
    ).toBe(false);
  });

  it("lists protocols needing attention from failed sources only", async () => {
    const failing = conversation("c-1", "AURORA-301");
    const healthy = conversation("c-2", "LUMEN-204");
    const { fetcher } = createFetcher(
      libraryHandler([failing, healthy], {
        [failing.id]: {
          sections: [],
          documents: [documentRecord(failing.id, "doc-1", "failed")],
        },
        [healthy.id]: {
          sections: [],
          documents: [documentRecord(healthy.id, "doc-2", "ready")],
        },
      }),
    );

    renderLibrary(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Needs attention (1)" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("1 source failed to process"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "View sources" }),
    ).toHaveAttribute("href", "/workspace/c-1");
  });

  it("omits the attention section when nothing needs action", async () => {
    const { fetcher } = createFetcher(
      libraryHandler([conversation("c-1", "AURORA-301")]),
    );

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    expect(screen.queryByText(/Needs attention/)).not.toBeInTheDocument();
  });

  it("renames a protocol in place", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (options?.method === "PATCH") {
        return conversation("c-1", "AURORA-301 amended");
      }
      return libraryHandler([conversation("c-1", "AURORA-301")])(
        path,
        options,
      );
    });
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    await user.click(
      screen.getByRole("button", { name: "Actions for AURORA-301" }),
    );
    await user.click(screen.getByRole("button", { name: "Rename" }));

    const field = await screen.findByLabelText("Protocol title");
    await user.clear(field);
    await user.type(field, "AURORA-301 amended");
    await user.click(screen.getByRole("button", { name: "Save title" }));

    expect(
      await screen.findByRole("link", { name: "AURORA-301 amended" }),
    ).toBeInTheDocument();
  });

  it("creates a protocol from the dialog", async () => {
    const created = conversation("c-new", "ORBIT-100");
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path === "/v1/ai/conversations" && options?.method === "POST") {
        return created;
      }
      return libraryHandler([])(path, options);
    });
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("heading", {
      name: "Create your first protocol workspace",
    });

    await user.click(screen.getByRole("button", { name: "New protocol" }));
    await user.type(
      await screen.findByLabelText("Protocol title"),
      "ORBIT-100",
    );
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    await waitFor(() =>
      expect(
        calls.some(
          (call) =>
            call.path === "/v1/ai/conversations" &&
            call.options?.method === "POST",
        ),
      ).toBe(true),
    );
  });

  it("shows organization setup for an account with no organization", () => {
    const { fetcher } = createFetcher(libraryHandler([]));

    renderLibrary(fetcher, []);

    expect(
      screen.getByRole("heading", {
        name: /where will your protocol work live/i,
      }),
    ).toBeInTheDocument();
  });
  it("keeps the toolbar when the archived tab is empty", async () => {
    const { fetcher } = createFetcher(
      libraryHandler([conversation("c-1", "AURORA-301")], {}, []),
    );
    const user = userEvent.setup();

    renderLibrary(fetcher);
    await screen.findByRole("link", { name: "AURORA-301" });

    await user.click(screen.getByRole("button", { name: "Archived" }));

    expect(
      await screen.findByRole("heading", {
        name: "No archived protocol workspaces",
      }),
    ).toBeInTheDocument();
    // The filter that produced this view stays on screen and reversible.
    expect(screen.getByLabelText("Search protocols")).toBeInTheDocument();
    expect(screen.getByLabelText("Sort by")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Archived" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(screen.getByRole("button", { name: "Active" }));
    expect(
      await screen.findByRole("link", { name: "AURORA-301" }),
    ).toBeInTheDocument();
  });
});
