import { useCallback, useEffect, useRef, useState } from "react";

import {
  GENERATE_JOB_POLL_MS,
  GENERATE_SECTIONS_JOB_KIND,
  cancelJob,
  createJob,
  getJob,
  listJobAttempts,
  listJobs,
} from "../api/jobs";
import type {
  GenerationAttemptRecord,
  JobRecord,
  JobStatus,
  M11Section,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";

const IN_FLIGHT: ReadonlySet<JobStatus> = new Set([
  "queued",
  "running",
  "retrying",
]);

const START_FAILURE = "Could not start generation. Please try again.";
const CANCEL_FAILURE = "Could not cancel generation. Please try again.";

export function isJobInFlight(status: JobStatus | undefined): boolean {
  return status !== undefined && IN_FLIGHT.has(status);
}

/** Draft sections that still have no stored content. */
export function emptyDraftSections(sections: M11Section[]): M11Section[] {
  return sections.filter(
    (section) => section.status === "draft" && section.content.trim() === "",
  );
}

export interface GenerationJobController {
  job: JobRecord | null;
  attempts: GenerationAttemptRecord[];
  pending: boolean;
  error: string | null;
  start: () => Promise<void>;
  cancel: () => Promise<void>;
  retryFailed: (sectionNumber?: string) => Promise<void>;
}

function expectedRevisions(
  sections: M11Section[],
  numbers: string[],
): Record<string, number> {
  const wanted = new Set(numbers);
  const revisions: Record<string, number> = {};
  for (const section of sections) {
    if (wanted.has(section.section_number)) {
      revisions[section.section_number] = section.current_revision;
    }
  }
  return revisions;
}

/** Resume, poll, start, cancel, and retry empty-draft section generation. */
export function useGenerationJob({
  organizationId,
  conversationId,
  sections,
  fetcher,
  enabled,
  onTerminal,
}: {
  organizationId: string | null;
  conversationId: string | null;
  sections: M11Section[];
  fetcher: AuthorizedFetch;
  enabled: boolean;
  onTerminal?: () => void;
}): GenerationJobController {
  const [job, setJob] = useState<JobRecord | null>(null);
  const [attempts, setAttempts] = useState<GenerationAttemptRecord[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);

  const sectionsRef = useRef(sections);
  sectionsRef.current = sections;
  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled || organizationId === null || conversationId === null) {
      return;
    }

    let cancelled = false;
    let intervalId: number | null = null;
    const orgId = organizationId;
    const conversation = conversationId;

    function stopPolling() {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    }

    async function loadAttempts(jobId: string): Promise<GenerationAttemptRecord[]> {
      const page = await listJobAttempts(fetcherRef.current, orgId, jobId);
      return page.items;
    }

    async function refresh(jobId: string, notifyTerminal: boolean) {
      const next = await getJob(fetcherRef.current, orgId, jobId);
      const nextAttempts = await loadAttempts(jobId);
      if (cancelled) {
        return;
      }
      setJob(next);
      setAttempts(nextAttempts);
      if (notifyTerminal && !isJobInFlight(next.status)) {
        stopPolling();
        onTerminalRef.current?.();
      }
    }

    function startPolling(jobId: string) {
      stopPolling();
      intervalId = window.setInterval(() => {
        void refresh(jobId, true).catch(() => undefined);
      }, GENERATE_JOB_POLL_MS);
    }

    async function resume() {
      const listed = await listJobs(
        fetcherRef.current,
        orgId,
        conversation,
        GENERATE_SECTIONS_JOB_KIND,
        1,
      );
      if (cancelled) {
        return;
      }
      const latest = listed.items[0] ?? null;
      setJob(latest);
      if (latest === null) {
        setAttempts([]);
        return;
      }
      const nextAttempts = await loadAttempts(latest.id);
      if (cancelled) {
        return;
      }
      setAttempts(nextAttempts);
      if (isJobInFlight(latest.status)) {
        startPolling(latest.id);
      }
    }

    void resume().catch(() => undefined);
    return () => {
      cancelled = true;
      stopPolling();
    };
  }, [conversationId, enabled, epoch, organizationId]);

  const requestGeneration = useCallback(async (numbers: string[]) => {
    if (
      organizationId === null ||
      conversationId === null ||
      numbers.length === 0
    ) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      await createJob(
        fetcherRef.current,
        organizationId,
        GENERATE_SECTIONS_JOB_KIND,
        conversationId,
        {
          section_numbers: numbers,
          expected_revisions: expectedRevisions(sectionsRef.current, numbers),
        },
      );
      setEpoch((value) => value + 1);
    } catch {
      setError(START_FAILURE);
    } finally {
      setPending(false);
    }
  }, [conversationId, organizationId]);

  const start = useCallback(async () => {
    await requestGeneration(
      emptyDraftSections(sectionsRef.current).map((section) => section.section_number),
    );
  }, [requestGeneration]);

  const retryFailed = useCallback(
    async (sectionNumber?: string) => {
      const failed = attempts
        .filter((attempt) => attempt.status === "failed")
        .map((attempt) => attempt.section_number);
      const numbers =
        sectionNumber === undefined
          ? failed
          : failed.filter((number) => number === sectionNumber);
      await requestGeneration(numbers);
    },
    [attempts, requestGeneration],
  );

  const cancel = useCallback(async () => {
    if (organizationId === null || job === null || !isJobInFlight(job.status)) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      await cancelJob(fetcherRef.current, organizationId, job.id);
      setEpoch((value) => value + 1);
    } catch {
      setError(CANCEL_FAILURE);
    } finally {
      setPending(false);
    }
  }, [job, organizationId]);

  return { job, attempts, pending, error, start, cancel, retryFailed };
}
