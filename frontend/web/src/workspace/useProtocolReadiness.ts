import { useCallback, useEffect, useRef, useState } from "react";

import {
  GENERATE_JOB_POLL_MS,
  VALIDATE_READINESS_JOB_KIND,
  createJob,
  getJob,
  getReadiness,
} from "../api/jobs";
import type { JobRecord, ReadinessRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import {
  readinessViewFromApi,
  type ReadinessView,
} from "../product/governanceReviewFixtures";
import { isJobInFlight } from "./useGenerationJob";

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
  const jobRef = useRef<JobRecord | null>(null);
  const intervalRef = useRef<number | null>(null);
  const generationRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    stopPolling();
    jobRef.current = null;
    generationRef.current += 1;
    const expected = generationRef.current;
    setRecord(null);
    setPending(false);
    setError(null);

    if (
      !enabled ||
      organizationId === null ||
      conversationId === null
    ) {
      setLoading(false);
      return;
    }

    setLoading(true);
    void getReadiness(fetcherRef.current, organizationId, conversationId)
      .then((next) => {
        if (generationRef.current !== expected) {
          return;
        }
        setRecord(next);
        setLoading(false);
      })
      .catch(() => {
        if (generationRef.current !== expected) {
          return;
        }
        setError(LOAD_FAILURE);
        setLoading(false);
      });
  }, [conversationId, enabled, organizationId, reload, stopPolling]);

  const retry = useCallback(() => {
    setReload((current) => current + 1);
  }, []);

  const start = useCallback(async () => {
    if (
      !enabled ||
      organizationId === null ||
      conversationId === null ||
      pending ||
      isJobInFlight(jobRef.current?.status)
    ) {
      return;
    }
    stopPolling();
    const expected = generationRef.current + 1;
    generationRef.current = expected;
    setPending(true);
    setError(null);
    try {
      const created = await createJob(
        fetcherRef.current,
        organizationId,
        VALIDATE_READINESS_JOB_KIND,
        conversationId,
        {},
      );
      if (generationRef.current !== expected) {
        return;
      }
      jobRef.current = created;
      const orgId = organizationId;
      const conversation = conversationId;

      const refresh = async (): Promise<JobRecord | null> => {
        const next = await getJob(fetcherRef.current, orgId, created.id);
        if (generationRef.current !== expected) {
          return null;
        }
        jobRef.current = next;
        if (isJobInFlight(next.status)) {
          return next;
        }
        stopPolling();
        if (next.status === "succeeded") {
          const snapshot = await getReadiness(
            fetcherRef.current,
            orgId,
            conversation,
          );
          if (generationRef.current === expected) {
            setRecord(snapshot);
            setPending(false);
          }
        } else {
          setError(JOB_FAILURE);
          setPending(false);
        }
        return next;
      };

      const next = await refresh();
      if (
        generationRef.current === expected &&
        next !== null &&
        isJobInFlight(next.status)
      ) {
        intervalRef.current = window.setInterval(() => {
          void refresh().catch(() => undefined);
        }, GENERATE_JOB_POLL_MS);
      } else if (generationRef.current === expected) {
        setPending(false);
      }
    } catch {
      if (generationRef.current === expected) {
        setError(START_FAILURE);
        setPending(false);
      }
    }
  }, [
    conversationId,
    enabled,
    organizationId,
    pending,
    stopPolling,
  ]);

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
