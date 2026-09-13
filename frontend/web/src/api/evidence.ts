import type { AuthorizedFetch } from "../auth/AuthContext";
import { organizationHeaders } from "./client";
import type { EvidenceChunkList } from "./types";

function evidencePath(conversationId: string, ids: string[]): string {
  const query = new URLSearchParams();
  for (const id of ids) {
    query.append("ids", id);
  }
  return `/v1/ai/conversations/${encodeURIComponent(conversationId)}/evidence-chunks?${query.toString()}`;
}

/** Load stored passages for citation inspection, in request order. */
export function listEvidenceChunks(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  ids: string[],
): Promise<EvidenceChunkList> {
  return fetcher<EvidenceChunkList>(evidencePath(conversationId, ids), {
    headers: organizationHeaders(organizationId),
  });
}
