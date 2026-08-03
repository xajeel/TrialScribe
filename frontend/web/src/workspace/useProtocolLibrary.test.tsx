import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type {
  Conversation,
  DocumentRecord,
  M11Section,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  useProtocolLibrary,
  type ProtocolLibraryController,
} from "./useProtocolLibrary";

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
  id: string,
  status: M11Section["status"],
): M11Section {
  return {
    id,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: id,
    title: `Section ${id}`,
    position: Number(id),
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
  status: DocumentRecord["status"],
): DocumentRecord {
  return {
    id,
    conversation_id: conversationId,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: null,
    kind: "research_document",
    filename: `${id}.pdf`,
    content_type: "application/pdf",
    byte_size: 1024,
    status,
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

function Harness({
  fetcher,
  onController,
}: {
  fetcher: AuthorizedFetch;
  onController: (controller: ProtocolLibraryController) => void;
}) {
  const controller = useProtocolLibrary(ORGANIZATION_ID, fetcher);
  onController(controller);
  return (
    <div>
      <p data-testid="status">{controller.status}</p>
      <p data-testid="titles">
        {controller.visible.map((item) => item.title).join("|")}
      </p>
      <p data-testid="feedback">{controller.feedback?.message ?? ""}</p>
    </div>
  );
}

function renderLibrary(fetcher: AuthorizedFetch) {
  const state: { current: ProtocolLibraryController | null } = {
    current: null,
  };
  render(
    <Harness
      fetcher={fetcher}
      onController={(controller) => {
        state.current = controller;
      }}
    />,
  );
  return {
    controller: () => {
      if (state.current === null) {
        throw new Error("controller not ready");
      }
      return state.current;
    },
  };
}

function emptyDetailHandler(path: string): unknown {
  if (path.includes("/m11-sections")) {
    return { catalog_version: "2025.1", items: [] };
  }
  if (path.includes("/documents")) {
    return { items: [], next_cursor: null };
  }
  throw new Error(`unexpected path ${path}`);
}

describe("useProtocolLibrary", () => {
  it("loads the active protocols and reports ready", async () => {
    const { fetcher, calls } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [conversation("c-1", "AURORA-301")],
          next_cursor: null,
        };
      }
      return emptyDetailHandler(path);
    });

    renderLibrary(fetcher);

    expect(await screen.findByText("AURORA-301")).toBeInTheDocument();
    expect(screen.getByTestId("status")).toHaveTextContent("ready");
    expect(calls[0].path).toBe("/v1/ai/conversations?limit=50");
  });

  it("reports a fixed failure message and recovers on retry", async () => {
    let attempt = 0;
    const { fetcher } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        attempt += 1;
        if (attempt === 1) {
          throw new Error("network");
        }
        return {
          items: [conversation("c-1", "AURORA-301")],
          next_cursor: null,
        };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);

    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("error"),
    );

    act(() => {
      library.controller().retry();
    });

    expect(await screen.findByText("AURORA-301")).toBeInTheDocument();
  });

  it("requests archived protocols when the scope changes", async () => {
    const { fetcher, calls } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return { items: [], next_cursor: null };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("ready"),
    );

    act(() => {
      library.controller().setScope("archived");
    });

    await waitFor(() =>
      expect(
        calls.some((call) => call.path.includes("archived=true")),
      ).toBe(true),
    );
  });

  it("filters by search and sorts by title or activity", async () => {
    const { fetcher } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [
            conversation("c-1", "AURORA-301", {
              last_activity_at: "2026-07-20T09:00:00Z",
            }),
            conversation("c-2", "LUMEN-204", {
              last_activity_at: "2026-07-28T09:00:00Z",
            }),
          ],
          next_cursor: null,
        };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("titles")).toHaveTextContent(
        "LUMEN-204|AURORA-301",
      ),
    );

    act(() => {
      library.controller().setSort("title");
    });
    expect(screen.getByTestId("titles")).toHaveTextContent(
      "AURORA-301|LUMEN-204",
    );

    act(() => {
      library.controller().setSearch("lumen");
    });
    expect(screen.getByTestId("titles")).toHaveTextContent("LUMEN-204");
  });

  it("fills row details and tolerates a failed detail request", async () => {
    const { fetcher } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [conversation("c-1", "AURORA-301"), conversation("c-2", "LUMEN-204")],
          next_cursor: null,
        };
      }
      if (path.includes("/c-1/m11-sections")) {
        return {
          catalog_version: "2025.1",
          items: [
            section("c-1", "1", "done"),
            section("c-1", "2", "draft"),
          ],
        };
      }
      if (path.includes("/c-1/documents")) {
        return {
          items: [
            documentRecord("c-1", "d-1", "ready"),
            documentRecord("c-1", "d-2", "failed"),
          ],
          next_cursor: null,
        };
      }
      throw new Error("detail unavailable");
    });

    const library = renderLibrary(fetcher);

    await waitFor(() => {
      expect(library.controller().details["c-1"]).toEqual({
        sections: { done: 1, total: 2 },
        sources: 2,
        processing: 0,
        failed: 1,
      });
    });

    await waitFor(() => {
      expect(library.controller().details["c-2"]).toEqual({
        sections: null,
        sources: null,
        processing: 0,
        failed: 0,
      });
    });
    expect(screen.getByTestId("status")).toHaveTextContent("ready");
  });

  it("rejects a blank title before any request", async () => {
    const { fetcher, calls } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return { items: [], next_cursor: null };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("ready"),
    );
    const before = calls.length;

    await act(async () => {
      await library.controller().create("   ");
    });

    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "Enter a protocol title.",
    );
    expect(calls.length).toBe(before);
  });

  it("rejects a title over the 200 character limit", async () => {
    const { fetcher } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return { items: [], next_cursor: null };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("ready"),
    );

    await act(async () => {
      await library.controller().create("x".repeat(201));
    });

    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "Protocol titles must be 200 characters or fewer.",
    );
  });

  it("creates a protocol and puts it at the top of the list", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path === "/v1/ai/conversations" && options?.method === "POST") {
        return conversation("c-new", "ORBIT-100", {
          last_activity_at: "2026-07-29T09:00:00Z",
        });
      }
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [conversation("c-1", "AURORA-301")],
          next_cursor: null,
        };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("ready"),
    );

    let created: Conversation | null = null;
    await act(async () => {
      created = await library.controller().create("  ORBIT-100  ");
    });

    expect(created).not.toBeNull();
    expect(screen.getByTestId("titles")).toHaveTextContent(
      "ORBIT-100|AURORA-301",
    );
    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "ORBIT-100 created. Opening the workspace…",
    );
  });

  it("reports a fixed public message when creation fails", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path === "/v1/ai/conversations" && options?.method === "POST") {
        throw new Error("boom");
      }
      if (path.startsWith("/v1/ai/conversations?")) {
        return { items: [], next_cursor: null };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("status")).toHaveTextContent("ready"),
    );

    await act(async () => {
      await library.controller().create("ORBIT-100");
    });

    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "Could not create the protocol workspace. Please try again.",
    );
  });

  it("archives a protocol out of the active scope", async () => {
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [conversation("c-1", "AURORA-301")],
          next_cursor: null,
        };
      }
      if (options?.method === "DELETE") {
        return conversation("c-1", "AURORA-301", { status: "archived" });
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("titles")).toHaveTextContent("AURORA-301"),
    );

    await act(async () => {
      await library.controller().archive("c-1");
    });

    expect(screen.getByTestId("titles")).toHaveTextContent("");
    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "AURORA-301 archived.",
    );
    expect(
      calls.some(
        (call) =>
          call.path === "/v1/ai/conversations/c-1" &&
          call.options?.method === "DELETE",
      ),
    ).toBe(true);
  });

  it("restores a protocol out of the archived scope", async () => {
    const { fetcher, calls } = createFetcher((path, options) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [conversation("c-1", "ORBIT registry")],
          next_cursor: null,
        };
      }
      if (path.endsWith("/restore")) {
        return conversation("c-1", "ORBIT registry");
      }
      if (options?.method === "PATCH") {
        return conversation("c-1", "ORBIT amended");
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("titles")).toHaveTextContent("ORBIT registry"),
    );

    await act(async () => {
      await library.controller().restore("c-1");
    });

    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "ORBIT registry restored.",
    );
    expect(
      calls.some((call) => call.path === "/v1/ai/conversations/c-1/restore"),
    ).toBe(true);
  });

  it("renames a protocol in place", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        return {
          items: [conversation("c-1", "AURORA-301")],
          next_cursor: null,
        };
      }
      if (options?.method === "PATCH") {
        return conversation("c-1", "AURORA-301 amended");
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    await waitFor(() =>
      expect(screen.getByTestId("titles")).toHaveTextContent("AURORA-301"),
    );

    await act(async () => {
      await library.controller().rename("c-1", "AURORA-301 amended");
    });

    expect(screen.getByTestId("titles")).toHaveTextContent(
      "AURORA-301 amended",
    );
  });

  it("ignores a slow response from a previous scope", async () => {
    let releaseFirst: ((value: unknown) => void) | null = null;
    const { fetcher } = createFetcher((path) => {
      if (path.startsWith("/v1/ai/conversations?")) {
        if (!path.includes("archived=true")) {
          return new Promise((resolve) => {
            releaseFirst = resolve;
          });
        }
        return {
          items: [conversation("c-2", "ORBIT registry")],
          next_cursor: null,
        };
      }
      return emptyDetailHandler(path);
    });

    const library = renderLibrary(fetcher);
    act(() => {
      library.controller().setScope("archived");
    });

    await waitFor(() =>
      expect(screen.getByTestId("titles")).toHaveTextContent("ORBIT registry"),
    );

    await act(async () => {
      releaseFirst?.({
        items: [conversation("c-1", "AURORA-301")],
        next_cursor: null,
      });
      await Promise.resolve();
    });

    expect(screen.getByTestId("titles")).toHaveTextContent("ORBIT registry");
    expect(screen.getByTestId("titles")).not.toHaveTextContent("AURORA-301");
  });
});
