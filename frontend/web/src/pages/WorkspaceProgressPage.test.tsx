import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type {
  Conversation,
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
import { WorkspaceProgressPage } from "./WorkspaceProgressPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const ACCOUNT_ID = "00000000-0000-4000-8000-000000000020";
const CONVERSATION_ID = "c-aurora";

function conversation(): Conversation {
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
  };
}

function section(
  number: string,
  title: string,
  state: "done" | "drafted" | "empty",
): M11Section {
  return {
    id: `s-${number}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: number,
    title,
    position: Number(number),
    instructions: "",
    content: state === "empty" ? "" : "Three drafted words here",
    status: state === "done" ? "done" : "draft",
    current_revision: state === "empty" ? 0 : 2,
    completed_at: state === "done" ? "2026-07-30T09:00:00Z" : null,
    completed_by_account_id: state === "done" ? ACCOUNT_ID : null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

function documentRecord(
  id: string,
  status: DocumentRecord["status"] = "ready",
  kind: DocumentRecord["kind"] = "research_document",
): DocumentRecord {
  return {
    id,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: ACCOUNT_ID,
    kind,
    filename: `${id}.pdf`,
    content_type: "application/pdf",
    byte_size: 2_097_152,
    status,
    error: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

function createFetcher(
  handler: (
    path: string,
    options: RequestOptions | undefined,
  ) => unknown | Promise<unknown>,
): AuthorizedFetch {
  async function fetcher<T>(
    path: string,
    options?: RequestOptions,
  ): Promise<T> {
    return (await handler(path, options)) as T;
  }
  return fetcher;
}

function progressHandler(
  sections: M11Section[],
  documents: DocumentRecord[],
  sectionsFail = false,
) {
  return (path: string, options?: RequestOptions): unknown => {
    const method = options?.method ?? "GET";
    if (path.includes("/messages")) {
      return { items: [], next_cursor: null };
    }
    if (path.includes("/documents")) {
      return { items: documents, next_cursor: null };
    }
    if (path.includes("/m11-sections")) {
      if (sectionsFail) {
        throw new Error("not initialized");
      }
      return { catalog_version: "2025.1", items: sections };
    }
    if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
      return conversation();
    }
    throw new Error(`Unexpected request: ${method} ${path}`);
  };
}

function renderProgress(fetcher: AuthorizedFetch) {
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
    <MemoryRouter initialEntries={[`/workspace/${CONVERSATION_ID}/progress`]}>
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <Routes>
            <Route
              path="/workspace/:conversationId/progress"
              element={<WorkspaceProgressPage />}
            />
          </Routes>
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

const MIXED = [
  section("1", "Protocol Summary", "done"),
  section("2", "Introduction", "drafted"),
  section("3", "Trial Objectives", "empty"),
];

describe("WorkspaceProgressPage", () => {
  it("shows each section's real drafting state", async () => {
    const fetcher = createFetcher(
      progressHandler(MIXED, [documentRecord("doc-1")]),
    );

    renderProgress(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Protocol progress" }),
    ).toBeInTheDocument();
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Done")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Drafted")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Not started")).toBeInTheDocument();
    expect(within(rows[2]).getByText("No content yet")).toBeInTheDocument();
    expect(within(rows[1]).getByText("4 words")).toBeInTheDocument();
  });

  it("summarises the counts from the loaded sections", async () => {
    const fetcher = createFetcher(
      progressHandler(MIXED, [documentRecord("doc-1")]),
    );

    renderProgress(fetcher);

    expect(
      await screen.findByText("1 done · 1 drafted · 1 not started, of 3 sections."),
    ).toBeInTheDocument();
    expect(screen.getByText("1 of 3 sections complete")).toBeInTheDocument();
  });

  it("shows the complete state when every section is done", async () => {
    const fetcher = createFetcher(
      progressHandler(
        [
          section("1", "Protocol Summary", "done"),
          section("2", "Introduction", "done"),
        ],
        [documentRecord("doc-1")],
      ),
    );

    renderProgress(fetcher);

    expect(
      await screen.findByRole("heading", { name: "All sections drafted" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Every section has been marked done. Review the protocol before export.",
      ),
    ).toBeInTheDocument();
  });

  it("lists attention rows only for failed or processing sources", async () => {
    const fetcher = createFetcher(
      progressHandler(MIXED, [
        documentRecord("ready-doc"),
        documentRecord("failed-doc", "failed"),
        documentRecord("pending-doc", "pending"),
      ]),
    );

    renderProgress(fetcher);

    const attention = await screen.findByRole("region", {
      name: "Needs attention",
    });
    expect(within(attention).getByText("failed-doc.pdf")).toBeInTheDocument();
    expect(within(attention).getByText("pending-doc.pdf")).toBeInTheDocument();
    expect(
      within(attention).queryByText("ready-doc.pdf"),
    ).not.toBeInTheDocument();
  });

  it("omits the attention region when every source is ready", async () => {
    const fetcher = createFetcher(
      progressHandler(MIXED, [documentRecord("doc-1")]),
    );

    renderProgress(fetcher);

    await screen.findByRole("heading", { name: "Protocol progress" });
    expect(
      screen.queryByRole("region", { name: "Needs attention" }),
    ).not.toBeInTheDocument();
  });

  it("shows source kind, size, and status for every upload", async () => {
    const fetcher = createFetcher(
      progressHandler(MIXED, [
        documentRecord("trial", "ready", "trial_data"),
      ]),
    );

    renderProgress(fetcher);

    expect(await screen.findByText("trial.pdf")).toBeInTheDocument();
    expect(screen.getByText("Trial data · 2.0 MB")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });

  it("invites the user to upload when the protocol has no sources", async () => {
    const fetcher = createFetcher(progressHandler(MIXED, []));

    renderProgress(fetcher);

    expect(
      await screen.findByText(/No sources uploaded yet/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Add trial data and research documents",
      }),
    ).toHaveAttribute("href", `/workspace/${CONVERSATION_ID}`);
  });

  it("shows the not-started state when the outline was never prepared", async () => {
    const fetcher = createFetcher(
      progressHandler([], [documentRecord("doc-1")], true),
    );

    renderProgress(fetcher);

    expect(
      await screen.findByRole("heading", { name: "Sections not started" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Open the workspace to prepare the 14-section ICH M11 outline.",
      ),
    ).toBeInTheDocument();
    // No zero counts are invented for a workspace that has no sections.
    expect(screen.queryByText(/of 0 sections complete/)).not.toBeInTheDocument();
  });

  it("offers a working retry when the workspace fails to load", async () => {
    let attempt = 0;
    const fetcher = createFetcher((path, options) => {
      if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
        attempt += 1;
        if (attempt === 1) {
          throw new Error("network");
        }
      }
      return progressHandler(MIXED, [documentRecord("doc-1")])(path, options);
    });
    const user = userEvent.setup();

    renderProgress(fetcher);

    expect(
      await screen.findByText("Could not load this protocol workspace."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Protocol Summary")).toBeInTheDocument();
  });

  it("shows no percentage, token, cost, or retry-section control", async () => {
    const fetcher = createFetcher(
      progressHandler(MIXED, [
        documentRecord("doc-1"),
        documentRecord("failed-doc", "failed"),
      ]),
    );

    renderProgress(fetcher);
    await screen.findByRole("heading", { name: "Protocol progress" });

    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/\d+%/);
    expect(text).not.toMatch(/\$\d/);
    expect(text).not.toMatch(/token/i);
    expect(text).not.toMatch(/est\. remaining/i);
    expect(
      screen.queryByRole("button", { name: /retry section/i }),
    ).not.toBeInTheDocument();
  });
});
