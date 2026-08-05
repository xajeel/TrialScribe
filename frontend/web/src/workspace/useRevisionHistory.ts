import { useCallback, useEffect, useRef, useState } from "react";

import { listM11SectionRevisions } from "../api/m11Sections";
import { resolveOrganizationIdentities } from "../api/organizations";
import type {
  M11SectionRevision,
  OrganizationIdentitySummary,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

export type RevisionHistoryStatus = "idle" | "loading" | "ready" | "error";

export interface RevisionHistoryController {
  status: RevisionHistoryStatus;
  revisions: M11SectionRevision[];
  identities: Readonly<Record<string, OrganizationIdentitySummary>>;
  error: string | null;
  retry: () => void;
}

export const REVISION_HISTORY_FAILURE = "Could not load revision history.";
const REVISION_PAGE_LIMIT = 100;
const IDENTITY_RESOLUTION_LIMIT = 100;

/** Load every immutable snapshot for one section and expose newest first. */
export function useRevisionHistory(
  organizationId: string | null,
  conversationId: string | null,
  sectionNumber: string | null,
  fetcher: AuthorizedFetch,
): RevisionHistoryController {
  const [status, setStatus] = useState<RevisionHistoryStatus>("idle");
  const [revisions, setRevisions] = useState<M11SectionRevision[]>([]);
  const [identities, setIdentities] = useState<
    Readonly<Record<string, OrganizationIdentitySummary>>
  >({});
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    const expected = generation.current;
    setRevisions([]);
    setIdentities({});
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
    const load = async (): Promise<{
      revisions: M11SectionRevision[];
      identities: Readonly<Record<string, OrganizationIdentitySummary>>;
    }> => {
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
      const ordered = items.sort(
        (left, right) => right.revision_number - left.revision_number,
      );
      const authorIds = [
        ...new Set(
          ordered.flatMap((revision) =>
            revision.author_account_id === null
              ? []
              : [revision.author_account_id],
          ),
        ),
      ];
      const resolved: OrganizationIdentitySummary[] = [];
      for (
        let offset = 0;
        offset < authorIds.length;
        offset += IDENTITY_RESOLUTION_LIMIT
      ) {
        resolved.push(
          ...(await resolveOrganizationIdentities(
            fetcher,
            organizationId,
            authorIds.slice(offset, offset + IDENTITY_RESOLUTION_LIMIT),
          )),
        );
      }
      return {
        revisions: ordered,
        identities: Object.fromEntries(
          resolved.map((identity) => [identity.account_id, identity]),
        ),
      };
    };

    void load()
      .then((result) => {
        if (generation.current !== expected) {
          return;
        }
        setRevisions(result.revisions);
        setIdentities(result.identities);
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

  return { status, revisions, identities, error, retry };
}
