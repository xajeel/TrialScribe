import type { AuthorizedFetch } from "../auth/AuthContext";
import { organizationHeaders } from "./client";
import type { M11Section, M11SectionWorkspace } from "./types";

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
