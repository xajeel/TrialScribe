import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  archiveConversation,
  createConversation,
  listConversations,
  renameConversation,
  restoreConversation,
} from "../api/conversations";
import { listDocuments } from "../api/documents";
import { listM11Sections } from "../api/m11Sections";
import type { Conversation } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

export type LibraryStatus = "idle" | "loading" | "ready" | "error";
export type LibraryScope = "active" | "archived";
export type LibrarySort = "activity" | "title";
export type LibraryAction =
  | "idle"
  | "creating"
  | "renaming"
  | "archiving"
  | "restoring";

export interface ProtocolFeedback {
  kind: "success" | "error";
  message: string;
}

export interface ProtocolDetail {
  sections: { done: number; total: number } | null;
  sources: number | null;
  processing: number;
  failed: number;
}

export interface ProtocolLibraryController {
  status: LibraryStatus;
  protocols: Conversation[];
  visible: Conversation[];
  details: Record<string, ProtocolDetail>;
  scope: LibraryScope;
  search: string;
  sort: LibrarySort;
  nextCursor: string | null;
  loadingMore: boolean;
  action: LibraryAction;
  feedback: ProtocolFeedback | null;
  setScope: (scope: LibraryScope) => void;
  setSearch: (search: string) => void;
  setSort: (sort: LibrarySort) => void;
  retry: () => void;
  loadMore: () => void;
  dismissFeedback: () => void;
  create: (title: string) => Promise<Conversation | null>;
  rename: (conversationId: string, title: string) => Promise<boolean>;
  archive: (conversationId: string) => Promise<boolean>;
  restore: (conversationId: string) => Promise<boolean>;
}

export const PROTOCOL_TITLE_LIMIT = 200;

const PUBLIC_FAILURES = {
  load: "Could not load protocol workspaces.",
  create: "Could not create the protocol workspace. Please try again.",
  rename: "Could not rename the protocol workspace. Please try again.",
  archive: "Could not archive the protocol workspace. Please try again.",
  restore: "Could not restore the protocol workspace. Please try again.",
} as const;

const BLANK_TITLE = "Enter a protocol title.";
const LONG_TITLE = `Protocol titles must be ${PROTOCOL_TITLE_LIMIT} characters or fewer.`;
const PAGE_LIMIT = 50;
const ENRICH_CONCURRENCY = 4;

/** Run `worker` over `items` with at most `limit` requests in flight. */
async function inBatches<T>(
  items: T[],
  limit: number,
  worker: (item: T) => Promise<void>,
): Promise<void> {
  let cursor = 0;
  const runners = Array.from(
    { length: Math.min(limit, items.length) },
    async () => {
      while (cursor < items.length) {
        const item = items[cursor];
        cursor += 1;
        await worker(item);
      }
    },
  );
  await Promise.all(runners);
}

/** Coordinate the organization-scoped protocol library list and its mutations. */
export function useProtocolLibrary(
  organizationId: string | null,
  fetcher: AuthorizedFetch,
): ProtocolLibraryController {
  const [status, setStatus] = useState<LibraryStatus>("idle");
  const [protocols, setProtocols] = useState<Conversation[]>([]);
  const [details, setDetails] = useState<Record<string, ProtocolDetail>>({});
  const [scope, setScopeState] = useState<LibraryScope>("active");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<LibrarySort>("activity");
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [action, setAction] = useState<LibraryAction>("idle");
  const [feedback, setFeedback] = useState<ProtocolFeedback | null>(null);
  const [reload, setReload] = useState(0);

  const generation = useRef(0);
  const actionInFlight = useRef(false);

  const enrich = useCallback(
    async (
      items: Conversation[],
      expected: number,
      expectedOrganization: string,
    ) => {
      await inBatches(items, ENRICH_CONCURRENCY, async (item) => {
        if (generation.current !== expected) {
          return;
        }
        const [workspace, documents] = await Promise.all([
          listM11Sections(fetcher, expectedOrganization, item.id).catch(
            () => null,
          ),
          listDocuments(fetcher, expectedOrganization, item.id).catch(
            () => null,
          ),
        ]);
        if (generation.current !== expected) {
          return;
        }
        const sections =
          workspace === null
            ? null
            : {
                done: workspace.items.filter((row) => row.status === "done")
                  .length,
                total: workspace.items.length,
              };
        setDetails((current) => ({
          ...current,
          [item.id]: {
            sections,
            sources: documents === null ? null : documents.items.length,
            processing:
              documents === null
                ? 0
                : documents.items.filter((row) => row.status === "pending")
                    .length,
            failed:
              documents === null
                ? 0
                : documents.items.filter((row) => row.status === "failed")
                    .length,
          },
        }));
      });
    },
    [fetcher],
  );

  useEffect(() => {
    const expected = ++generation.current;
    setProtocols([]);
    setDetails({});
    setNextCursor(null);
    setLoadingMore(false);
    setFeedback(null);
    setAction("idle");
    actionInFlight.current = false;

    if (organizationId === null) {
      setStatus("idle");
      return;
    }

    const expectedOrganization = organizationId;
    setStatus("loading");
    void listConversations(fetcher, expectedOrganization, {
      archived: scope === "archived",
      limit: PAGE_LIMIT,
    })
      .then((page) => {
        if (generation.current !== expected) {
          return;
        }
        setProtocols(page.items);
        setNextCursor(page.next_cursor);
        setStatus("ready");
        return enrich(page.items, expected, expectedOrganization);
      })
      .catch(() => {
        if (generation.current === expected) {
          setStatus("error");
        }
      });
  }, [enrich, fetcher, organizationId, reload, scope]);

  const setScope = useCallback((next: LibraryScope) => {
    setScopeState(next);
  }, []);

  const retry = useCallback(() => {
    setReload((value) => value + 1);
  }, []);

  const loadMore = useCallback(() => {
    if (organizationId === null || nextCursor === null || loadingMore) {
      return;
    }
    const expected = generation.current;
    const expectedOrganization = organizationId;
    const cursor = nextCursor;
    setLoadingMore(true);
    void listConversations(fetcher, expectedOrganization, {
      archived: scope === "archived",
      cursor,
      limit: PAGE_LIMIT,
    })
      .then((page) => {
        if (generation.current !== expected) {
          return;
        }
        setProtocols((current) => {
          const seen = new Set(current.map((item) => item.id));
          return [...current, ...page.items.filter((item) => !seen.has(item.id))];
        });
        setNextCursor(page.next_cursor);
        setLoadingMore(false);
        return enrich(page.items, expected, expectedOrganization);
      })
      .catch(() => {
        if (generation.current === expected) {
          setLoadingMore(false);
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.load });
        }
      });
  }, [enrich, fetcher, loadingMore, nextCursor, organizationId, scope]);

  const dismissFeedback = useCallback(() => {
    setFeedback(null);
  }, []);

  const validateTitle = useCallback((title: string): string | null => {
    const normalized = title.trim();
    if (normalized === "") {
      return BLANK_TITLE;
    }
    if (normalized.length > PROTOCOL_TITLE_LIMIT) {
      return LONG_TITLE;
    }
    return null;
  }, []);

  const create = useCallback(
    async (title: string): Promise<Conversation | null> => {
      if (organizationId === null || actionInFlight.current) {
        return null;
      }
      const invalid = validateTitle(title);
      if (invalid !== null) {
        setFeedback({ kind: "error", message: invalid });
        return null;
      }
      const expected = generation.current;
      const expectedOrganization = organizationId;
      actionInFlight.current = true;
      setAction("creating");
      setFeedback(null);
      try {
        const created = await createConversation(
          fetcher,
          expectedOrganization,
          title.trim(),
        );
        if (generation.current === expected) {
          setProtocols((current) => [
            created,
            ...current.filter((item) => item.id !== created.id),
          ]);
          setFeedback({
            kind: "success",
            message: `${created.title} created. Opening the workspace…`,
          });
        }
        return created;
      } catch {
        if (generation.current === expected) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.create });
        }
        return null;
      } finally {
        actionInFlight.current = false;
        if (generation.current === expected) {
          setAction("idle");
        }
      }
    },
    [fetcher, organizationId, validateTitle],
  );

  const rename = useCallback(
    async (conversationId: string, title: string): Promise<boolean> => {
      if (organizationId === null || actionInFlight.current) {
        return false;
      }
      const invalid = validateTitle(title);
      if (invalid !== null) {
        setFeedback({ kind: "error", message: invalid });
        return false;
      }
      const expected = generation.current;
      const expectedOrganization = organizationId;
      actionInFlight.current = true;
      setAction("renaming");
      setFeedback(null);
      try {
        const renamed = await renameConversation(
          fetcher,
          expectedOrganization,
          conversationId,
          title.trim(),
        );
        if (generation.current === expected) {
          setProtocols((current) =>
            current.map((item) =>
              item.id === conversationId ? renamed : item,
            ),
          );
          setFeedback({
            kind: "success",
            message: `Renamed to ${renamed.title}.`,
          });
        }
        return true;
      } catch {
        if (generation.current === expected) {
          setFeedback({ kind: "error", message: PUBLIC_FAILURES.rename });
        }
        return false;
      } finally {
        actionInFlight.current = false;
        if (generation.current === expected) {
          setAction("idle");
        }
      }
    },
    [fetcher, organizationId, validateTitle],
  );

  const move = useCallback(
    async (
      conversationId: string,
      kind: "archive" | "restore",
    ): Promise<boolean> => {
      if (organizationId === null || actionInFlight.current) {
        return false;
      }
      const expected = generation.current;
      const expectedOrganization = organizationId;
      actionInFlight.current = true;
      setAction(kind === "archive" ? "archiving" : "restoring");
      setFeedback(null);
      try {
        const moved =
          kind === "archive"
            ? await archiveConversation(
                fetcher,
                expectedOrganization,
                conversationId,
              )
            : await restoreConversation(
                fetcher,
                expectedOrganization,
                conversationId,
              );
        if (generation.current === expected) {
          setProtocols((current) =>
            current.filter((item) => item.id !== conversationId),
          );
          setFeedback({
            kind: "success",
            message:
              kind === "archive"
                ? `${moved.title} archived.`
                : `${moved.title} restored.`,
          });
        }
        return true;
      } catch {
        if (generation.current === expected) {
          setFeedback({
            kind: "error",
            message:
              kind === "archive"
                ? PUBLIC_FAILURES.archive
                : PUBLIC_FAILURES.restore,
          });
        }
        return false;
      } finally {
        actionInFlight.current = false;
        if (generation.current === expected) {
          setAction("idle");
        }
      }
    },
    [fetcher, organizationId],
  );

  const archive = useCallback(
    (conversationId: string) => move(conversationId, "archive"),
    [move],
  );

  const restore = useCallback(
    (conversationId: string) => move(conversationId, "restore"),
    [move],
  );

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    const matched =
      term === ""
        ? [...protocols]
        : protocols.filter((item) =>
            item.title.toLowerCase().includes(term),
          );
    matched.sort((left, right) =>
      sort === "title"
        ? left.title.localeCompare(right.title)
        : right.last_activity_at.localeCompare(left.last_activity_at),
    );
    return matched;
  }, [protocols, search, sort]);

  return {
    status,
    protocols,
    visible,
    details,
    scope,
    search,
    sort,
    nextCursor,
    loadingMore,
    action,
    feedback,
    setScope,
    setSearch,
    setSort,
    retry,
    loadMore,
    dismissFeedback,
    create,
    rename,
    archive,
    restore,
  };
}
