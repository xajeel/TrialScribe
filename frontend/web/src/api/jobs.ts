import type { AuthorizedFetch } from "../auth/AuthContext";
import { organizationHeaders } from "./client";
import type {
  GenerationAttemptList,
  JobList,
  JobRecord,
  ReadinessRecord,
  RewriteOptionList,
} from "./types";

export const GENERATE_SECTIONS_JOB_KIND = "generate_sections";
export const VALIDATE_READINESS_JOB_KIND = "validate_readiness";
export const GENERATE_JOB_POLL_MS = 1000;

const JOBS_PATH = "/v1/jobs";

function jobPath(jobId: string): string {
  return `${JOBS_PATH}/${encodeURIComponent(jobId)}`;
}

/** Ask the worker to run one piece of background work. */
export function createJob(
  fetcher: AuthorizedFetch,
  organizationId: string,
  kind: string,
  conversationId: string,
  parameters: Record<string, unknown>,
): Promise<JobRecord> {
  return fetcher<JobRecord>(JOBS_PATH, {
    method: "POST",
    headers: organizationHeaders(organizationId),
    json: {
      kind,
      conversation_id: conversationId,
      parameters,
    },
  });
}

/** Read one job ticket, including live progress. */
export function getJob(
  fetcher: AuthorizedFetch,
  organizationId: string,
  jobId: string,
): Promise<JobRecord> {
  return fetcher<JobRecord>(jobPath(jobId), {
    headers: organizationHeaders(organizationId),
  });
}

/** Ask a queued or running job to stop. */
export function cancelJob(
  fetcher: AuthorizedFetch,
  organizationId: string,
  jobId: string,
): Promise<JobRecord> {
  return fetcher<JobRecord>(`${jobPath(jobId)}/cancel`, {
    method: "POST",
    headers: organizationHeaders(organizationId),
  });
}

/** List the newest jobs for one conversation, optionally filtered by kind. */
export function listJobs(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  kind: string,
  limit: number,
): Promise<JobList> {
  const query = new URLSearchParams({
    conversation_id: conversationId,
    kind,
    limit: String(limit),
  });
  return fetcher<JobList>(`${JOBS_PATH}?${query.toString()}`, {
    headers: organizationHeaders(organizationId),
  });
}

/** Read the latest per-section generation attempt for one job. */
export function listJobAttempts(
  fetcher: AuthorizedFetch,
  organizationId: string,
  jobId: string,
): Promise<GenerationAttemptList> {
  return fetcher<GenerationAttemptList>(`${jobPath(jobId)}/attempts`, {
    headers: organizationHeaders(organizationId),
  });
}

/** Read rewrite option texts for one succeeded rewrite job. */
export function listRewriteOptions(
  fetcher: AuthorizedFetch,
  organizationId: string,
  jobId: string,
): Promise<RewriteOptionList> {
  return fetcher<RewriteOptionList>(`${jobPath(jobId)}/rewrite-options`, {
    headers: organizationHeaders(organizationId),
  });
}

/** Read the newest stored protocol readiness snapshot for one conversation. */
export function getReadiness(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<ReadinessRecord> {
  const query = new URLSearchParams({ conversation_id: conversationId });
  return fetcher<ReadinessRecord>(`${JOBS_PATH}/readiness?${query.toString()}`, {
    headers: organizationHeaders(organizationId),
  });
}
