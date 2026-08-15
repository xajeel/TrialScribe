import { useCallback, useEffect, useRef, useState } from "react";

import {
  GENERATE_JOB_POLL_MS,
  GENERATE_SECTIONS_JOB_KIND,
  createJob,
  getJob,
  listRewriteOptions,
} from "../api/jobs";
import { reviseM11Section } from "../api/m11Sections";
import type {
  JobRecord,
  M11Section,
  RewriteOptionRecord,
} from "../api/types";
import type { AuthorizedFetch } from "../auth/AuthContext";
import { isJobInFlight } from "./useGenerationJob";

const START_FAILURE = "Could not start the rewrite. Please try again.";
const APPLY_FAILURE = "Could not apply the rewrite. Please try again.";
const JOB_FAILURE = "Could not rewrite this section. Please try again.";

export interface RewriteStartInput {
  instruction: string;
  keepCitations: boolean;
  useSources: boolean;
  selectionStart?: number;
  selectionEnd?: number;
}

export interface SectionRewriteController {
  job: JobRecord | null;
  options: RewriteOptionRecord[];
  pending: boolean;
  error: string | null;
  start: (input: RewriteStartInput) => Promise<void>;
  useOption: (id: string) => Promise<boolean>;
  keepOriginal: () => void;
}

function rewriteParameters(
  section: M11Section,
  input: RewriteStartInput,
): Record<string, unknown> {
  const parameters: Record<string, unknown> = {
    mode: "rewrite",
    section_numbers: [section.section_number],
    expected_revisions: {
      [section.section_number]: section.current_revision,
    },
    rewrite_instruction: input.instruction,
    keep_citations: input.keepCitations,
    use_sources: input.useSources,
  };
  if (
    input.selectionStart !== undefined &&
    input.selectionEnd !== undefined &&
    input.selectionStart < input.selectionEnd
  ) {
    parameters.selection_start = input.selectionStart;
    parameters.selection_end = input.selectionEnd;
  }
  return parameters;
}

/** Start, poll, and apply a single-section rewrite job. */
export function useSectionRewrite({
  organizationId,
  conversationId,
  section,
  fetcher,
  enabled,
}: {
  organizationId: string | null;
  conversationId: string | null;
  section: M11Section | null;
  fetcher: AuthorizedFetch;
  enabled: boolean;
}): SectionRewriteController {
  const [job, setJob] = useState<JobRecord | null>(null);
  const [options, setOptions] = useState<RewriteOptionRecord[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sectionRef = useRef(section);
  sectionRef.current = section;
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const jobRef = useRef<JobRecord | null>(null);
  jobRef.current = job;
  const intervalRef = useRef<number | null>(null);
  const generationRef = useRef(0);
  const sourceRevisionRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopPolling();
    generationRef.current += 1;
    jobRef.current = null;
    sourceRevisionRef.current = null;
    setJob(null);
    setOptions([]);
    setError(null);
    setPending(false);
  }, [stopPolling]);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    reset();
  }, [
    conversationId,
    enabled,
    organizationId,
    reset,
    section?.content,
    section?.current_revision,
    section?.id,
  ]);

  const start = useCallback(
    async (input: RewriteStartInput) => {
      const current = sectionRef.current;
      if (
        !enabled ||
        organizationId === null ||
        conversationId === null ||
        current === null ||
        current.status === "done" ||
        pending ||
        isJobInFlight(jobRef.current?.status)
      ) {
        return;
      }
      stopPolling();
      const expected = generationRef.current + 1;
      generationRef.current = expected;
      sourceRevisionRef.current = current.current_revision;
      setPending(true);
      setError(null);
      setOptions([]);
      try {
        const created = await createJob(
          fetcherRef.current,
          organizationId,
          GENERATE_SECTIONS_JOB_KIND,
          conversationId,
          rewriteParameters(current, input),
        );
        if (generationRef.current !== expected) {
          return;
        }
        jobRef.current = created;
        setJob(created);
        const orgId = organizationId;

        const refresh = async (): Promise<JobRecord | null> => {
          const next = await getJob(fetcherRef.current, orgId, created.id);
          if (generationRef.current !== expected) {
            return null;
          }
          jobRef.current = next;
          setJob(next);
          if (isJobInFlight(next.status)) {
            return next;
          }
          stopPolling();
          if (next.status === "succeeded") {
            const page = await listRewriteOptions(
              fetcherRef.current,
              orgId,
              next.id,
            );
            if (generationRef.current === expected) {
              setOptions(page.items);
            }
          } else {
            setError(JOB_FAILURE);
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
        }
      } catch {
        if (generationRef.current === expected) {
          setError(START_FAILURE);
        }
      } finally {
        if (generationRef.current === expected) {
          setPending(false);
        }
      }
    },
    [conversationId, enabled, organizationId, pending, stopPolling],
  );

  const useOption = useCallback(
    async (id: string): Promise<boolean> => {
      const current = sectionRef.current;
      if (
        !enabled ||
        organizationId === null ||
        conversationId === null ||
        current === null ||
        current.status === "done"
      ) {
        return false;
      }
      const option =
        options.find((item) => item.id === id) ??
        (id === "alternative-2" ? options[1] : options[0]);
      const expectedRevision = sourceRevisionRef.current;
      if (option === undefined || expectedRevision === null) {
        return false;
      }
      if (current.current_revision !== expectedRevision) {
        reset();
        return false;
      }
      setPending(true);
      setError(null);
      try {
        await reviseM11Section(
          fetcherRef.current,
          organizationId,
          conversationId,
          current.section_number,
          expectedRevision,
          current.instructions,
          option.text,
        );
        reset();
        return true;
      } catch {
        setError(APPLY_FAILURE);
        return false;
      } finally {
        setPending(false);
      }
    },
    [conversationId, enabled, options, organizationId, reset],
  );

  const keepOriginal = useCallback(() => {
    reset();
  }, [reset]);

  return { job, options, pending, error, start, useOption, keepOriginal };
}
