import { useCallback, useEffect, useRef, useState } from "react";

import {
  GENERATE_SECTIONS_JOB_KIND,
  createJob,
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
import { useJobRun } from "./useJobRun";

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
  const sourceRevisionRef = useRef<number | null>(null);
  const run = useJobRun(fetcher);

  const reset = useCallback(() => {
    run.claim();
    run.forget();
    sourceRevisionRef.current = null;
    setJob(null);
    setOptions([]);
    setError(null);
    setPending(false);
  }, [run]);

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
        isJobInFlight(run.latest()?.status)
      ) {
        return;
      }
      const token = run.claim();
      const orgId = organizationId;
      sourceRevisionRef.current = current.current_revision;
      setPending(true);
      setError(null);
      setOptions([]);
      try {
        const created = await createJob(
          fetcherRef.current,
          orgId,
          GENERATE_SECTIONS_JOB_KIND,
          conversationId,
          rewriteParameters(current, input),
        );
        if (!run.isCurrent(token)) {
          return;
        }
        run.adopt(created);
        setJob(created);
        await run.follow(token, orgId, created.id, {
          onUpdate: (next) => {
            setJob(next);
          },
          onSucceeded: async (next) => {
            const page = await listRewriteOptions(fetcherRef.current, orgId, next.id);
            if (run.isCurrent(token)) {
              setOptions(page.items);
            }
          },
          onFailed: () => {
            setError(JOB_FAILURE);
          },
        });
      } catch {
        if (run.isCurrent(token)) {
          setError(START_FAILURE);
        }
      } finally {
        if (run.isCurrent(token)) {
          setPending(false);
        }
      }
    },
    [conversationId, enabled, organizationId, pending, run],
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
