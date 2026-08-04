import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { RequestOptions } from "../api/client";
import type { M11SectionRevision, M11SectionRevisionPage } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  REVISION_HISTORY_FAILURE,
  useRevisionHistory,
  type RevisionHistoryController,
} from "./useRevisionHistory";

const ORGANIZATION_ID = "org-1";
const CONVERSATION_ID = "conversation-1";

function revision(number: number): M11SectionRevision {
  return {
    id: `revision-${number}`,
    section_id: "section-5",
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    revision_number: number,
    action: number === 2 ? "done" : "revised",
    instructions: "",
    content: `Revision ${number} content`,
    status: number === 2 ? "done" : "draft",
    author_account_id: "account-1",
    created_at: `2026-07-2${number}T12:00:00Z`,
  };
}

function Harness({
  fetcher,
  organizationId = ORGANIZATION_ID,
  conversationId = CONVERSATION_ID,
  sectionNumber = "5",
  capture,
}: {
  fetcher: AuthorizedFetch;
  organizationId?: string | null;
  conversationId?: string | null;
  sectionNumber?: string | null;
  capture: (controller: RevisionHistoryController) => void;
}) {
  const controller = useRevisionHistory(
    organizationId,
    conversationId,
    sectionNumber,
    fetcher,
  );
  capture(controller);
  return (
    <div>
      <span data-testid="status">{controller.status}</span>
      <span data-testid="numbers">
        {controller.revisions.map((item) => item.revision_number).join(",")}
      </span>
      <span data-testid="error">{controller.error}</span>
    </div>
  );
}

function renderHistory(
  fetcher: AuthorizedFetch,
  options: {
    organizationId?: string | null;
    conversationId?: string | null;
    sectionNumber?: string | null;
  } = {},
) {
  let current: RevisionHistoryController | null = null;
  const view = render(
    <Harness
      fetcher={fetcher}
      {...options}
      capture={(controller) => {
        current = controller;
      }}
    />,
  );
  return {
    ...view,
    controller: () => {
      if (current === null) {
        throw new Error("Controller was not captured");
      }
      return current;
    },
  };
}

describe("useRevisionHistory", () => {
  it("loads every cursor page and presents newest first", async () => {
    const paths: string[] = [];
    const fetcher: AuthorizedFetch = async <T,>(
      path: string,
      options?: RequestOptions,
    ): Promise<T> => {
      paths.push(path);
      expect(options?.headers).toEqual({ "X-Organization-ID": ORGANIZATION_ID });
      const page: M11SectionRevisionPage = path.includes("after_revision=0")
        ? { items: [revision(1), revision(2)], next_after_revision: 2 }
        : { items: [revision(3)], next_after_revision: null };
      return page as T;
    };

    renderHistory(fetcher);

    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("numbers")).toHaveTextContent("3,2,1");
    expect(paths).toEqual([
      "/v1/ai/conversations/conversation-1/m11-sections/5/revisions?after_revision=0&limit=100",
      "/v1/ai/conversations/conversation-1/m11-sections/5/revisions?after_revision=2&limit=100",
    ]);
  });

  it("supports an empty history", async () => {
    const fetcher: AuthorizedFetch = async <T,>(): Promise<T> =>
      ({ items: [], next_after_revision: null }) as T;
    renderHistory(fetcher);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("numbers")).toBeEmptyDOMElement();
  });

  it("shows a fixed failure and retries", async () => {
    let attempts = 0;
    const fetcher: AuthorizedFetch = async <T,>(): Promise<T> => {
      attempts += 1;
      if (attempts === 1) {
        throw new Error("revision database password");
      }
      return { items: [revision(1)], next_after_revision: null } as T;
    };
    const history = renderHistory(fetcher);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));
    expect(screen.getByTestId("error")).toHaveTextContent(REVISION_HISTORY_FAILURE);
    expect(screen.queryByText(/database password/i)).not.toBeInTheDocument();

    act(() => history.controller().retry());
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(attempts).toBe(2);
  });

  it("stays idle when any scope input is missing", () => {
    let called = false;
    const fetcher: AuthorizedFetch = async <T,>(): Promise<T> => {
      called = true;
      return { items: [], next_after_revision: null } as T;
    };
    renderHistory(fetcher, { organizationId: null });
    expect(screen.getByTestId("status")).toHaveTextContent("idle");
    expect(called).toBe(false);
  });

  it("ignores a slow result after the selected section changes", async () => {
    let resolveSlow: ((page: M11SectionRevisionPage) => void) | null = null;
    const slow = new Promise<M11SectionRevisionPage>((resolve) => {
      resolveSlow = resolve;
    });
    const fetcher: AuthorizedFetch = async <T,>(path: string): Promise<T> => {
      if (path.includes("m11-sections/5/")) {
        return (await slow) as T;
      }
      return { items: [revision(3)], next_after_revision: null } as T;
    };
    const history = renderHistory(fetcher);
    history.rerender(
      <Harness
        fetcher={fetcher}
        sectionNumber="6"
        capture={() => undefined}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("numbers")).toHaveTextContent("3"));

    act(() => {
      resolveSlow?.({ items: [revision(1)], next_after_revision: null });
    });
    await act(async () => Promise.resolve());
    expect(screen.getByTestId("numbers")).toHaveTextContent("3");
  });

  it("fails safely when the server repeats a cursor", async () => {
    const fetcher: AuthorizedFetch = async <T,>(): Promise<T> =>
      ({ items: [revision(1)], next_after_revision: 0 }) as T;
    renderHistory(fetcher);
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));
    expect(screen.getByTestId("error")).toHaveTextContent(REVISION_HISTORY_FAILURE);
  });
});
