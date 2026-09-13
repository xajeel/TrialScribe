import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type {
  Conversation,
  ConversationMessage,
  DocumentRecord,
  M11Section,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  useProtocolOverview,
  type ProtocolOverviewController,
} from "./useProtocolOverview";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000010";
const CONVERSATION_ID = "00000000-0000-4000-8000-000000000030";

function conversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    owner_account_id: "00000000-0000-4000-8000-000000000020",
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

function message(sequence: number, content: string): ConversationMessage {
  return {
    id: `m-${sequence}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    author_account_id: "00000000-0000-4000-8000-000000000020",
    role: "user",
    content,
    sequence,
    created_at: "2026-07-28T09:00:00Z",
  };
}

function section(number: string, position: number): M11Section {
  return {
    id: `s-${number}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: number,
    title: `Section ${number}`,
    position,
    instructions: "",
    content: "",
    status: "draft",
    current_revision: 0,
    completed_at: null,
    completed_by_account_id: null,
    created_at: "2026-07-28T09:00:00Z",
    updated_at: "2026-07-28T09:00:00Z",
  };
}

function documentRecord(id: string): DocumentRecord {
  return {
    id,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: null,
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

/** Default handler: one conversation, two instructions, one source, two sections. */
function fullHandler(path: string): unknown {
  if (path.includes("/messages")) {
    return {
      items: [message(2, "Second instruction"), message(1, "First instruction")],
      next_cursor: null,
    };
  }
  if (path.includes("/documents")) {
    return { items: [documentRecord("d-1")], next_cursor: null };
  }
  if (path.includes("/m11-sections")) {
    return {
      catalog_version: "2025.1",
      items: [section("2", 2), section("1", 1)],
    };
  }
  return conversation();
}

function Harness({
  fetcher,
  conversationId = CONVERSATION_ID,
  onController,
}: {
  fetcher: AuthorizedFetch;
  conversationId?: string;
  onController: (controller: ProtocolOverviewController) => void;
}) {
  const controller = useProtocolOverview(
    ORGANIZATION_ID,
    conversationId,
    fetcher,
  );
  onController(controller);
  return (
    <div>
      <p data-testid="status">{controller.status}</p>
      <p data-testid="instructions">
        {controller.instructions.map((item) => item.content).join("|")}
      </p>
      <p data-testid="sections">
        {controller.sections.map((item) => item.section_number).join("|")}
      </p>
      <p data-testid="initialized">
        {controller.sectionsInitialized ? "yes" : "no"}
      </p>
      <p data-testid="feedback">{controller.feedback?.message ?? ""}</p>
    </div>
  );
}

function renderOverview(fetcher: AuthorizedFetch, conversationId?: string) {
  const state: { current: ProtocolOverviewController | null } = {
    current: null,
  };
  const capture = (controller: ProtocolOverviewController) => {
    state.current = controller;
  };
  const view = render(
    <Harness
      fetcher={fetcher}
      conversationId={conversationId}
      onController={capture}
    />,
  );
  return {
    view,
    capture,
    controller: () => {
      if (state.current === null) {
        throw new Error("controller not ready");
      }
      return state.current;
    },
  };
}

describe("useProtocolOverview", () => {
  it("loads the conversation, instructions, sources, and sections in one pass", async () => {
    const { fetcher, calls } = createFetcher(fullHandler);

    renderOverview(fetcher);

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });
    expect(calls).toHaveLength(4);
    expect(
      calls.some((call) => call.path === `/v1/ai/conversations/${CONVERSATION_ID}`),
    ).toBe(true);
  });

  it("orders instructions by sequence and sections by position", async () => {
    const { fetcher } = createFetcher(fullHandler);

    renderOverview(fetcher);

    await waitFor(() => {
      expect(screen.getByTestId("instructions")).toHaveTextContent(
        "First instruction|Second instruction",
      );
    });
    expect(screen.getByTestId("sections")).toHaveTextContent("1|2");
  });

  it("stays usable when the section outline was never prepared", async () => {
    const { fetcher } = createFetcher((path) => {
      if (path.includes("/m11-sections")) {
        throw new Error("not initialized");
      }
      return fullHandler(path);
    });

    renderOverview(fetcher);

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });
    expect(screen.getByTestId("initialized")).toHaveTextContent("no");
    expect(screen.getByTestId("sections")).toHaveTextContent("");
  });

  it("reports a fixed failure message and recovers on retry", async () => {
    let attempt = 0;
    const { fetcher } = createFetcher((path) => {
      if (path.includes("/messages")) {
        attempt += 1;
        if (attempt === 1) {
          throw new Error("network");
        }
      }
      return fullHandler(path);
    });

    const { controller } = renderOverview(fetcher);

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("error");
    });

    await act(async () => {
      controller().retry();
    });

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });
  });

  it("rejects a blank instruction without issuing a request", async () => {
    const { fetcher, calls } = createFetcher(fullHandler);

    const { controller } = renderOverview(fetcher);
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });
    const before = calls.length;

    let accepted = true;
    await act(async () => {
      accepted = await controller().addInstruction("   ");
    });

    expect(accepted).toBe(false);
    expect(calls).toHaveLength(before);
  });

  it("rejects an instruction over the character limit without a request", async () => {
    const { fetcher, calls } = createFetcher(fullHandler);

    const { controller } = renderOverview(fetcher);
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });
    const before = calls.length;

    let accepted = true;
    await act(async () => {
      accepted = await controller().addInstruction("x".repeat(4001));
    });

    expect(accepted).toBe(false);
    expect(calls).toHaveLength(before);
  });

  it("appends a saved instruction to the loaded list", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path.includes("/messages") && options?.method === "POST") {
        return message(3, "Third instruction");
      }
      return fullHandler(path);
    });

    const { controller } = renderOverview(fetcher);
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });

    await act(async () => {
      await controller().addInstruction("Third instruction");
    });

    expect(screen.getByTestId("instructions")).toHaveTextContent(
      "First instruction|Second instruction|Third instruction",
    );
    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "Instruction saved.",
    );
  });

  it("reports the fixed failure message when saving an instruction fails", async () => {
    const { fetcher } = createFetcher((path, options) => {
      if (path.includes("/messages") && options?.method === "POST") {
        throw new Error("network");
      }
      return fullHandler(path);
    });

    const { controller } = renderOverview(fetcher);
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });

    await act(async () => {
      await controller().addInstruction("Rejected instruction");
    });

    expect(screen.getByTestId("feedback")).toHaveTextContent(
      "Could not save the instruction. Please try again.",
    );
  });

  it("ignores a slow response for a protocol that is no longer selected", async () => {
    let release: (() => void) | null = null;
    const slow = new Promise<void>((resolve) => {
      release = resolve;
    });

    const { fetcher } = createFetcher(async (path) => {
      if (path === `/v1/ai/conversations/${CONVERSATION_ID}`) {
        await slow;
        return conversation({ title: "Stale protocol" });
      }
      if (path === "/v1/ai/conversations/other") {
        return conversation({ id: "other", title: "Current protocol" });
      }
      return fullHandler(path);
    });

    const { view, controller, capture } = renderOverview(fetcher);

    view.rerender(
      <Harness
        fetcher={fetcher}
        conversationId="other"
        onController={capture}
      />,
    );

    await act(async () => {
      release?.();
      await slow;
    });

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("ready");
    });
    expect(controller().conversation?.title).toBe("Current protocol");
  });
});
