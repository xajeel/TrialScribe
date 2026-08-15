import type { AuthorizedFetch } from "../auth/AuthContext";
import { organizationHeaders } from "./client";
import type {
  M11Section,
  M11SectionRevisionPage,
  M11SectionWorkspace,
} from "./types";

function workspacePath(conversationId: string): string {
  return `/v1/ai/conversations/${encodeURIComponent(conversationId)}/m11-sections`;
}

function sectionPath(conversationId: string, sectionNumber: string): string {
  return `${workspacePath(conversationId)}/${encodeURIComponent(sectionNumber)}`;
}

/** Create the fixed M11 workspace when absent and return its persisted rows. */
export function initializeM11Workspace(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<M11SectionWorkspace> {
  return fetcher<M11SectionWorkspace>(workspacePath(conversationId), {
    method: "PUT",
    headers: organizationHeaders(organizationId),
  });
}

/** Read persisted M11 sections without creating them. */
export function listM11Sections(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<M11SectionWorkspace> {
  return fetcher<M11SectionWorkspace>(workspacePath(conversationId), {
    headers: organizationHeaders(organizationId),
  });
}

/** Save manual instructions and content with optimistic revision checking. */
export function reviseM11Section(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  sectionNumber: string,
  expectedRevision: number,
  instructions: string,
  content: string,
): Promise<M11Section> {
  return fetcher<M11Section>(sectionPath(conversationId, sectionNumber), {
    method: "PATCH",
    headers: organizationHeaders(organizationId),
    json: {
      expected_revision: expectedRevision,
      instructions,
      content,
    },
  });
}

/** Mark one section done at its current accepted revision. */
export function markM11SectionDone(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  sectionNumber: string,
  expectedRevision: number,
): Promise<M11Section> {
  return fetcher<M11Section>(
    `${sectionPath(conversationId, sectionNumber)}/done`,
    {
      method: "POST",
      headers: organizationHeaders(organizationId),
      json: { expected_revision: expectedRevision },
    },
  );
}

/** Reopen one completed section at its current accepted revision. */
export function reopenM11Section(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  sectionNumber: string,
  expectedRevision: number,
): Promise<M11Section> {
  return fetcher<M11Section>(
    `${sectionPath(conversationId, sectionNumber)}/reopen`,
    {
      method: "POST",
      headers: organizationHeaders(organizationId),
      json: { expected_revision: expectedRevision },
    },
  );
}

/** Copy a numbered snapshot onto the current draft. */
export function restoreM11Section(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  sectionNumber: string,
  expectedRevision: number,
  revisionNumber: number,
): Promise<M11Section> {
  return fetcher<M11Section>(
    `${sectionPath(conversationId, sectionNumber)}/restore`,
    {
      method: "POST",
      headers: organizationHeaders(organizationId),
      json: {
        expected_revision: expectedRevision,
        revision_number: revisionNumber,
      },
    },
  );
}

/** Read one section's immutable revision snapshots with cursor pagination. */
export function listM11SectionRevisions(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  sectionNumber: string,
  afterRevision: number,
  limit: number,
): Promise<M11SectionRevisionPage> {
  const query = new URLSearchParams({
    after_revision: String(afterRevision),
    limit: String(limit),
  });
  return fetcher<M11SectionRevisionPage>(
    `${sectionPath(conversationId, sectionNumber)}/revisions?${query.toString()}`,
    { headers: organizationHeaders(organizationId) },
  );
}
