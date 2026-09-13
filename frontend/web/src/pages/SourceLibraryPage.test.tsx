import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
import { SourceLibraryPage } from "./SourceLibraryPage";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "conversation-alpha";

const CONVERSATION: Conversation = {
  id: CONVERSATION_ID,
  organization_id: ORGANIZATION_ID,
  owner_account_id: "00000000-0000-4000-8000-000000000020",
  title: "Protocol Alpha",
  status: "active",
  collaborator_account_ids: [],
  created_at: "2026-07-28T09:00:00Z",
  updated_at: "2026-07-28T09:00:00Z",
  last_activity_at: "2026-07-28T09:00:00Z",
  archived_at: null,
};

function documentRecord(
  id: string,
  filename: string,
  overrides: Partial<DocumentRecord> = {},
): DocumentRecord {
  return {
    id,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: "00000000-0000-4000-8000-000000000020",
    kind: "research_document",
    filename,
    content_type: "application/pdf",
    byte_size: 2_097_152,
    status: "ready",
    error: null,
    created_at: "2026-07-28T09:02:00Z",
    updated_at: "2026-07-28T09:02:00Z",
    ...overrides,
  };
}

const SECTIONS: M11Section[] = [];

function handler(documents: DocumentRecord[]) {
  return (path: string, options?: RequestOptions): unknown => {
    const method = options?.method ?? "GET";
    if (method === "GET" && path === "/v1/ai/conversations?limit=100") {
      return { items: [CONVERSATION], next_cursor: null };
    }
    if (path.includes("/messages")) {
      return { items: [], next_cursor: null };
    }
    if (path.includes("/documents")) {
      return { items: documents, next_cursor: null };
    }
    if (path.includes("/m11-sections")) {
      return { catalog_version: "2025.1", items: SECTIONS };
    }
    throw new Error(`Unexpected request: ${method} ${path}`);
  };
}

interface FetchCall {
  path: string;
  options: RequestOptions | undefined;
}

function createFetcher(
  route: (
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
    return (await route(path, options)) as T;
  }
  return { fetcher, calls };
}

function renderLibrary(fetcher: AuthorizedFetch) {
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
    <MemoryRouter initialEntries={[`/workspace/${CONVERSATION_ID}/sources`]}>
      <AuthContext.Provider value={auth}>
        <OrganizationContext.Provider value={organization}>
          <Routes>
            <Route
              path="/workspace/:conversationId/sources"
              element={<SourceLibraryPage />}
            />
          </Routes>
        </OrganizationContext.Provider>
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

describe("SourceLibraryPage", () => {
  it("groups sources by kind with their real status", async () => {
    const { fetcher } = createFetcher(
      handler([
        documentRecord("doc-1", "brochure.pdf"),
        documentRecord("doc-2", "trial.json", {
          kind: "trial_data",
          content_type: "application/json",
          byte_size: 88_402,
        }),
        documentRecord("doc-3", "interim.pdf", { status: "pending" }),
        documentRecord("doc-4", "broken.pdf", { status: "failed" }),
      ]),
    );
    renderLibrary(fetcher);

    const research = await screen.findByRole("list", {
      name: "Research documents",
    });
    const trial = screen.getByRole("list", { name: "Trial data" });

    expect(within(research).getByText("brochure.pdf")).toBeInTheDocument();
    expect(within(trial).getByText("trial.json")).toBeInTheDocument();
    expect(within(research).getByText("Ready")).toBeInTheDocument();
    expect(within(research).getByText("Processing")).toBeInTheDocument();
    expect(within(research).getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("3 items")).toBeInTheDocument();
    expect(screen.getByText("1 item")).toBeInTheDocument();
  });

  it("offers Add source from the empty state", async () => {
    const { fetcher } = createFetcher(handler([]));
    renderLibrary(fetcher);

    expect(
      await screen.findByRole("heading", { name: "No sources added" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Add source" }).length,
    ).toBeGreaterThan(0);
  });

  it("asks before removing a source and drops the row once confirmed", async () => {
    const user = userEvent.setup();
    const documents = [documentRecord("doc-1", "brochure.pdf")];
    const base = handler(documents);
    const { fetcher, calls } = createFetcher((path, options) => {
      if (options?.method === "DELETE") {
        return undefined;
      }
      return base(path, options);
    });
    renderLibrary(fetcher);

    await user.click(
      await screen.findByRole("button", { name: "Remove brochure.pdf" }),
    );

    // The confirmation must arrive before any request is issued.
    expect(
      calls.some((call) => call.options?.method === "DELETE"),
    ).toBe(false);
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByText(/brochure\.pdf will be deleted/),
    ).toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("button", { name: "Remove source" }),
    );

    await waitFor(() =>
      expect(screen.queryByText("brochure.pdf")).not.toBeInTheDocument(),
    );
    const removal = calls.find((call) => call.options?.method === "DELETE");
    expect(removal?.path).toBe(
      `/v1/ai/conversations/${CONVERSATION_ID}/documents/doc-1`,
    );
  });

  it("keeps the source when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    const { fetcher, calls } = createFetcher(
      handler([documentRecord("doc-1", "brochure.pdf")]),
    );
    renderLibrary(fetcher);

    await user.click(
      await screen.findByRole("button", { name: "Remove brochure.pdf" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("brochure.pdf")).toBeInTheDocument();
    expect(calls.some((call) => call.options?.method === "DELETE")).toBe(false);
  });

  it("uploads through the sheet and appends the stored source", async () => {
    const user = userEvent.setup();
    const base = handler([]);
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path.includes("/documents") && options?.method === "POST") {
        return documentRecord("doc-new", "synopsis.pdf");
      }
      return base(path, options);
    });
    renderLibrary(fetcher);

    await user.click(
      (await screen.findAllByRole("button", { name: "Add source" }))[0],
    );
    const sheet = await screen.findByRole("dialog", { name: "Add source" });

    const file = new File(["%PDF-1.4"], "synopsis.pdf", {
      type: "application/pdf",
    });
    await user.upload(within(sheet).getByLabelText("Choose file"), file);
    await user.click(
      within(sheet).getByRole("button", { name: "Upload source" }),
    );

    expect(await screen.findByText("synopsis.pdf")).toBeInTheDocument();
    const upload = calls.find(
      (call) => call.path.includes("/documents") && call.options?.method === "POST",
    );
    const body = upload?.options?.body as FormData;
    expect(body.get("kind")).toBe("research_document");
    expect((body.get("file") as File).name).toBe("synopsis.pdf");
  });

  it("rejects an oversized file before issuing a request", async () => {
    const user = userEvent.setup();
    const { fetcher, calls } = createFetcher(handler([]));
    renderLibrary(fetcher);

    await user.click(
      (await screen.findAllByRole("button", { name: "Add source" }))[0],
    );
    const sheet = await screen.findByRole("dialog", { name: "Add source" });

    const huge = new File([new Uint8Array(11 * 1024 * 1024)], "huge.pdf", {
      type: "application/pdf",
    });
    await user.upload(within(sheet).getByLabelText("Choose file"), huge);

    expect(
      await within(sheet).findByText(/The maximum is 10 MB/),
    ).toBeInTheDocument();
    expect(
      within(sheet).getByRole("button", { name: "Upload source" }),
    ).toBeDisabled();
    expect(
      calls.some(
        (call) =>
          call.path.includes("/documents") && call.options?.method === "POST",
      ),
    ).toBe(false);
  });

  it("rejects a dropped file whose type does not match the chosen kind", async () => {
    const user = userEvent.setup();
    const { fetcher } = createFetcher(handler([]));
    renderLibrary(fetcher);

    await user.click(
      (await screen.findAllByRole("button", { name: "Add source" }))[0],
    );
    const sheet = await screen.findByRole("dialog", { name: "Add source" });
    await user.click(within(sheet).getByLabelText("Trial data"));

    // The file input's accept attribute filters a chosen file, but a drop
    // bypasses it entirely, so the drop path must validate for itself.
    const wrong = new File(["%PDF-1.4"], "notes.pdf", {
      type: "application/pdf",
    });
    fireEvent.drop(within(sheet).getByText("Drop a document here"), {
      dataTransfer: { files: [wrong] },
    });

    expect(
      await within(sheet).findByText("Trial data must be a .json file."),
    ).toBeInTheDocument();
  });

  it("queues a dropped file that matches the chosen kind", async () => {
    const user = userEvent.setup();
    const { fetcher } = createFetcher(handler([]));
    renderLibrary(fetcher);

    await user.click(
      (await screen.findAllByRole("button", { name: "Add source" }))[0],
    );
    const sheet = await screen.findByRole("dialog", { name: "Add source" });

    const dropped = new File(["%PDF-1.4"], "dropped.pdf", {
      type: "application/pdf",
    });
    fireEvent.drop(within(sheet).getByText("Drop a document here"), {
      dataTransfer: { files: [dropped] },
    });

    expect(await within(sheet).findByText("dropped.pdf")).toBeInTheDocument();
    expect(
      within(sheet).getByRole("button", { name: "Upload source" }),
    ).toBeEnabled();
  });

  it("tracks the accepted file types against the chosen kind", async () => {
    const user = userEvent.setup();
    const { fetcher } = createFetcher(handler([]));
    renderLibrary(fetcher);

    await user.click(
      (await screen.findAllByRole("button", { name: "Add source" }))[0],
    );
    const sheet = await screen.findByRole("dialog", { name: "Add source" });
    const input = within(sheet).getByLabelText("Choose file");

    expect(input).toHaveAttribute(
      "accept",
      ".pdf,.txt,.md,application/pdf,text/plain,text/markdown",
    );
    await user.click(within(sheet).getByLabelText("Trial data"));
    expect(input).toHaveAttribute("accept", ".json,application/json");
    expect(
      within(sheet).getByText("Trial data must be a JSON object. Maximum 10 MB."),
    ).toBeInTheDocument();
  });

  it("closes the add-source sheet on Escape", async () => {
    const user = userEvent.setup();
    const { fetcher } = createFetcher(handler([]));
    renderLibrary(fetcher);

    await user.click(
      (await screen.findAllByRole("button", { name: "Add source" }))[0],
    );
    await screen.findByRole("dialog", { name: "Add source" });
    await user.keyboard("{Escape}");

    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Add source" }),
      ).not.toBeInTheDocument(),
    );
  });

  it("states a fixed public failure when removal fails", async () => {
    const user = userEvent.setup();
    const base = handler([documentRecord("doc-1", "brochure.pdf")]);
    const { fetcher } = createFetcher((path, options) => {
      if (options?.method === "DELETE") {
        throw new Error("boom: connection refused at 10.0.0.4");
      }
      return base(path, options);
    });
    renderLibrary(fetcher);

    await user.click(
      await screen.findByRole("button", { name: "Remove brochure.pdf" }),
    );
    const dialog = await screen.findByRole("dialog");
    await user.click(
      within(dialog).getByRole("button", { name: "Remove source" }),
    );

    expect(
      await screen.findByText("Could not remove the document. Please try again."),
    ).toBeInTheDocument();
    expect(screen.getByText("brochure.pdf")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("connection refused");
  });
});
