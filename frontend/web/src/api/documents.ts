import type { AuthorizedFetch } from "../auth/AuthContext";
import { organizationHeaders } from "./client";
import type { DocumentKind, DocumentPage, DocumentRecord } from "./types";

function documentsPath(conversationId: string): string {
  return `/v1/ai/conversations/${encodeURIComponent(conversationId)}/documents`;
}

/** List uploaded document metadata for one conversation. */
export function listDocuments(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<DocumentPage> {
  return fetcher<DocumentPage>(`${documentsPath(conversationId)}?limit=100`, {
    headers: organizationHeaders(organizationId),
  });
}

/** Remove one uploaded document and its stored content. */
export async function deleteDocument(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  documentId: string,
): Promise<void> {
  await fetcher<void>(
    `${documentsPath(conversationId)}/${encodeURIComponent(documentId)}`,
    { method: "DELETE", headers: organizationHeaders(organizationId) },
  );
}

/** Upload one trial-data or research file using browser-managed multipart data. */
export function uploadDocument(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  kind: DocumentKind,
  file: File,
): Promise<DocumentRecord> {
  const body = new FormData();
  body.append("kind", kind);
  body.append("file", file);
  return fetcher<DocumentRecord>(documentsPath(conversationId), {
    method: "POST",
    headers: organizationHeaders(organizationId),
    body,
  });
}
