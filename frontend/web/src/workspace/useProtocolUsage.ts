import { useCallback, useEffect, useRef, useState } from "react";

import { getUsage } from "../api/jobs";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  usageViewFromApi,
  type UsageView,
} from "../product/deliveryAuditReviewFixtures";

export const USAGE_LOAD_ERROR = "Could not load usage for this workspace.";

export interface ProtocolUsageController {
  view: UsageView | null;
  loading: boolean;
  error: boolean;
  retry: () => void;
}

/** Load stored provider usage for one protocol workspace. Never starts a job. */
export function useProtocolUsage({
  organizationId,
  conversationId,
  fetcher,
  enabled,
}: {
  organizationId: string | null;
  conversationId: string | null;
  fetcher: AuthorizedFetch;
  enabled: boolean;
}): ProtocolUsageController {
  const [view, setView] = useState<UsageView | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [reload, setReload] = useState(0);
  const generation = useRef(0);

  useEffect(() => {
    generation.current += 1;
    const expected = generation.current;
    setView(null);
    setError(false);

    if (
      !enabled ||
      organizationId === null ||
      conversationId === null
    ) {
      setLoading(false);
      return;
    }

    setLoading(true);
    void getUsage(fetcher, organizationId, conversationId)
      .then((record) => {
        if (generation.current !== expected) {
          return;
        }
        setView(usageViewFromApi(record));
        setLoading(false);
      })
      .catch(() => {
        if (generation.current === expected) {
          setError(true);
          setLoading(false);
        }
      });
  }, [conversationId, enabled, fetcher, organizationId, reload]);

  const retry = useCallback(() => {
    setReload((value) => value + 1);
  }, []);

  return { view, loading, error, retry };
}
