import { useCallback, useEffect, useRef, useState } from "react";

import {
  VALIDATE_READINESS_JOB_KIND,
  createJob,
  getReadiness,
} from "../api/jobs";
import type { ReadinessRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  readinessViewFromApi,
  type ReadinessView,
} from "../product/governanceReviewFixtures";
import { isJobInFlight } from "./useGenerationJob";
import { useJobRun } from "./useJobRun";

const LOAD_FAILURE = "Could not load protocol readiness.";
const START_FAILURE = "Could not start the readiness check. Please try again.";
const JOB_FAILURE = "Could not complete the readiness check. Please try again.";

export interface ProtocolReadinessController {
  record: ReadinessRecord | null;
  view: ReadinessView | null;
  pending: boolean;
  loading: boolean;
  error: string | null;
  start: () => Promise<void>;
  retry: () => void;
}

/** Load the stored snapshot and run another check without editing chapters. */
export function useProtocolReadiness({
  organizationId,
  conversationId,
  fetcher,
  enabled,
}: {
  organizationId: string | null;
  conversationId: string | null;
  fetcher: AuthorizedFetch;
  enabled: boolean;
}): ProtocolReadinessController {
  const [record, setRecord] = useState<ReadinessRecord | null>(null);
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const run = useJobRun(fetcher);

  useEffect(() => {
    run.forget();
    const token = run.claim();
    setRecord(null);
    setPending(false);
    setError(null);

    if (!enabled || organizationId === null || conversationId === null) {
      setLoading(false);
      return;
    }

    setLoading(true);
    void getReadiness(fetcherRef.current, organizationId, conversationId)
      .then((next) => {
        if (!run.isCurrent(token)) {
          return;
        }
        setRecord(next);
        setLoading(false);
      })
      .catch(() => {
        if (!run.isCurrent(token)) {
          return;
        }
        setError(LOAD_FAILURE);
        setLoading(false);
      });
  }, [conversationId, enabled, organizationId, reload, run]);

  const retry = useCallback(() => {
    setReload((current) => current + 1);
  }, []);

  const start = useCallback(async () => {
    if (
      !enabled ||
      organizationId === null ||
      conversationId === null ||
      pending ||
      isJobInFlight(run.latest()?.status)
    ) {
      return;
    }
    const token = run.claim();
    const orgId = organizationId;
    const conversation = conversationId;
    setPending(true);
    setError(null);
    try {
      const created = await createJob(
        fetcherRef.current,
        orgId,
        VALIDATE_READINESS_JOB_KIND,
        conversation,
        {},
      );
      if (!run.isCurrent(token)) {
        return;
      }
      run.adopt(created);
      const running = await run.follow(token, orgId, created.id, {
        onSucceeded: async () => {
          const snapshot = await getReadiness(
            fetcherRef.current,
            orgId,
            conversation,
          );
          if (run.isCurrent(token)) {
            setRecord(snapshot);
            setPending(false);
          }
        },
        onFailed: () => {
          setError(JOB_FAILURE);
          setPending(false);
        },
      });
      if (!running && run.isCurrent(token)) {
        setPending(false);
      }
    } catch {
      if (run.isCurrent(token)) {
        setError(START_FAILURE);
        setPending(false);
      }
    }
  }, [conversationId, enabled, organizationId, pending, run]);

  return {
    record,
    view: record === null ? null : readinessViewFromApi(record),
    pending,
    loading,
    error,
    start,
    retry,
  };
}
