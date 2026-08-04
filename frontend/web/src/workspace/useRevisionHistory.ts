import { useCallback, useEffect, useRef, useState } from "react";

import { listM11SectionRevisions } from "../api/m11Sections";
import type { M11SectionRevision } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

export type RevisionHistoryStatus = "idle" | "loading" | "ready" | "error";

export interface RevisionHistoryController {
  status: RevisionHistoryStatus;
  revisions: M11SectionRevision[];
  error: string | null;
  retry: () => void;
}

export const REVISION_HISTORY_FAILURE = "Could not load revision history.";
const REVISION_PAGE_LIMIT = 100;

/** Load every immutable snapshot for one section and expose newest first. */
export function useRevisionHistory(
  organizationId: string | null,
  conversationId: string | null,
  sectionNumber: string | null,
  fetcher: AuthorizedFetch,
): RevisionHistoryController {
  const [status, setStatus] = useState<RevisionHistoryStatus>("idle");
  const [revisions, setRevisions] = useState<M11SectionRevision[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    const expected = generation.current;
    setRevisions([]);
    setError(null);

    if (
      organizationId === null ||
      conversationId === null ||
      sectionNumber === null
    ) {
      setStatus("idle");
      return;
    }

    setStatus("loading");
    const load = async (): Promise<M11SectionRevision[]> => {
      const items: M11SectionRevision[] = [];
      let cursor = 0;
      while (true) {
        const page = await listM11SectionRevisions(
          fetcher,
          organizationId,
          conversationId,
          sectionNumber,
          cursor,
          REVISION_PAGE_LIMIT,
        );
        items.push(...page.items);
        if (page.next_after_revision === null) {
          break;
        }
        if (page.next_after_revision <= cursor) {
          throw new Error("Revision cursor did not advance");
        }
        cursor = page.next_after_revision;
      }
      return items.sort(
        (left, right) => right.revision_number - left.revision_number,
      );
    };

    void load()
      .then((items) => {
        if (generation.current !== expected) {
          return;
        }
        setRevisions(items);
        setStatus("ready");
      })
      .catch(() => {
        if (generation.current !== expected) {
          return;
        }
        setError(REVISION_HISTORY_FAILURE);
        setStatus("error");
      });
  }, [conversationId, fetcher, organizationId, reload, sectionNumber]);

  const retry = useCallback(() => {
    setReload((value) => value + 1);
  }, []);

  return { status, revisions, error, retry };
}
