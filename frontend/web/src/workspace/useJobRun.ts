import { useCallback, useEffect, useMemo, useRef } from "react";

import { GENERATE_JOB_POLL_MS, getJob } from "../api/jobs";
import type { JobRecord } from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { isJobInFlight } from "./useGenerationJob";

/**
 * What a screen wants to know while one background job runs.
 *
 * `onUpdate` fires on every reading, terminal or not, and is where progress
 * belongs. Exactly one of `onSucceeded` / `onFailed` fires, exactly once, and
 * only for the attempt that is still current.
 */
export interface JobRunHandlers {
  onUpdate?: (job: JobRecord) => void;
  onSucceeded: (job: JobRecord) => void | Promise<void>;
  onFailed: (job: JobRecord) => void;
}

export interface JobRun {
  /** The most recent ticket this run has seen, or null. */
  latest: () => JobRecord | null;
  /**
   * Abandon whatever is being followed and start a new attempt.
   *
   * Returns the token identifying that attempt. Anything that resolves later
   * must check `isCurrent(token)` before touching React state, so a reply from
   * an abandoned attempt cannot overwrite the screen.
   */
  claim: () => number;
  isCurrent: (token: number) => boolean;
  /** Stop polling without abandoning the attempt. */
  stop: () => void;
  /** Drop the remembered ticket, so nothing counts as in flight. */
  forget: () => void;
  /** Remember a ticket that was just created. */
  adopt: (job: JobRecord) => void;
  /**
   * Follow a ticket to a terminal status, polling while it runs.
   *
   * Resolves `true` when the job is still running and polling was scheduled,
   * and `false` when there is nothing left to wait for — either the job already
   * settled, or this attempt was abandoned while the first reading was in
   * flight.
   */
  follow: (
    token: number,
    organizationId: string,
    jobId: string,
    handlers: JobRunHandlers,
  ) => Promise<boolean>;
}

/**
 * Follow one background job at a time.
 *
 * Every screen that starts a job needs the same four things: an interval that
 * stops on unmount, a token that invalidates replies from an abandoned attempt,
 * a terminal check, and a place to hang the ticket it last saw. Written per
 * screen those four drift apart; written once they cannot.
 */
export function useJobRun(fetcher: AuthorizedFetch): JobRun {
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const jobRef = useRef<JobRecord | null>(null);
  const intervalRef = useRef<number | null>(null);
  const tokenRef = useRef(0);

  const stop = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  const claim = useCallback(() => {
    stop();
    tokenRef.current += 1;
    return tokenRef.current;
  }, [stop]);

  const isCurrent = useCallback((token: number) => tokenRef.current === token, []);
  const latest = useCallback(() => jobRef.current, []);
  const forget = useCallback(() => {
    jobRef.current = null;
  }, []);
  const adopt = useCallback((job: JobRecord) => {
    jobRef.current = job;
  }, []);

  const follow = useCallback(
    async (
      token: number,
      organizationId: string,
      jobId: string,
      handlers: JobRunHandlers,
    ): Promise<boolean> => {
      const refresh = async (): Promise<JobRecord | null> => {
        const next = await getJob(fetcherRef.current, organizationId, jobId);
        if (!isCurrent(token)) {
          return null;
        }
        jobRef.current = next;
        handlers.onUpdate?.(next);
        if (isJobInFlight(next.status)) {
          return next;
        }
        stop();
        if (next.status === "succeeded") {
          await handlers.onSucceeded(next);
        } else {
          handlers.onFailed(next);
        }
        return next;
      };

      const first = await refresh();
      if (first === null || !isCurrent(token) || !isJobInFlight(first.status)) {
        return false;
      }
      intervalRef.current = window.setInterval(() => {
        void refresh().catch(() => undefined);
      }, GENERATE_JOB_POLL_MS);
      return true;
    },
    [isCurrent, stop],
  );

  // Stable identity: every member is a stable callback, so a caller may list
  // the run itself in an effect's dependencies without re-running that effect
  // on each render.
  return useMemo(
    () => ({ latest, claim, isCurrent, stop, forget, adopt, follow }),
    [adopt, claim, follow, forget, isCurrent, latest, stop],
  );
}
