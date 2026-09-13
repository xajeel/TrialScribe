import type { AuthorizedFetch } from "../auth/AuthContext";
import { organizationHeaders } from "./client";
import type {
  Conversation,
  ConversationMessage,
  ConversationMessagePage,
  ConversationPage,
} from "./types";

const CONVERSATIONS_PATH = "/v1/ai/conversations";

export interface ConversationListOptions {
  archived?: boolean;
  cursor?: string | null;
  limit?: number;
}

/** List active or archived conversations for the selected organization. */
export function listConversations(
  fetcher: AuthorizedFetch,
  organizationId: string,
  options: ConversationListOptions = {},
): Promise<ConversationPage> {
  const query = new URLSearchParams({
    limit: String(options.limit ?? 100),
  });
  if (options.archived === true) {
    query.set("archived", "true");
  }
  if (options.cursor !== undefined && options.cursor !== null) {
    query.set("cursor", options.cursor);
  }
  return fetcher<ConversationPage>(`${CONVERSATIONS_PATH}?${query.toString()}`, {
    headers: organizationHeaders(organizationId),
  });
}

/** Read one accessible conversation by identifier. */
export function getConversation(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<Conversation> {
  return fetcher<Conversation>(
    `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}`,
    { headers: organizationHeaders(organizationId) },
  );
}

/** Archive one conversation so authoring actions stop while content stays readable. */
export function archiveConversation(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<Conversation> {
  return fetcher<Conversation>(
    `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}`,
    {
      method: "DELETE",
      headers: organizationHeaders(organizationId),
    },
  );
}

/** Restore one archived conversation to the active library. */
export function restoreConversation(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<Conversation> {
  return fetcher<Conversation>(
    `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}/restore`,
    {
      method: "POST",
      headers: organizationHeaders(organizationId),
    },
  );
}

/** Create a durable conversation in the selected organization. */
export function createConversation(
  fetcher: AuthorizedFetch,
  organizationId: string,
  title: string,
): Promise<Conversation> {
  return fetcher<Conversation>(CONVERSATIONS_PATH, {
    method: "POST",
    headers: organizationHeaders(organizationId),
    json: { title },
  });
}

/** Rename one accessible conversation. */
export function renameConversation(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  title: string,
): Promise<Conversation> {
  return fetcher<Conversation>(
    `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}`,
    {
      method: "PATCH",
      headers: organizationHeaders(organizationId),
      json: { title },
    },
  );
}

/** List durable messages for one conversation. */
export function listConversationMessages(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
): Promise<ConversationMessagePage> {
  return fetcher<ConversationMessagePage>(
    `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}/messages?limit=100`,
    { headers: organizationHeaders(organizationId) },
  );
}

/** Append one user instruction to a conversation. */
export function appendConversationMessage(
  fetcher: AuthorizedFetch,
  organizationId: string,
  conversationId: string,
  content: string,
): Promise<ConversationMessage> {
  return fetcher<ConversationMessage>(
    `${CONVERSATIONS_PATH}/${encodeURIComponent(conversationId)}/messages`,
    {
      method: "POST",
      headers: organizationHeaders(organizationId),
      json: { content },
    },
  );
}
