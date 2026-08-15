/** Shared contracts returned by the API gateway. Mirror the backend schemas. */

export type OrganizationRole = "owner" | "admin" | "member";

export interface Account {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface Organization {
  id: string;
  name: string;
  role: OrganizationRole;
  created_at: string;
}

export interface OrganizationIdentitySummary {
  account_id: string;
  email: string;
  is_active: boolean;
}

export interface OrganizationMembership {
  id: string;
  organization_id: string;
  account_id: string;
  identity: OrganizationIdentitySummary;
  role: OrganizationRole;
  created_at: string;
}

export type InvitationRole = "admin" | "member";

export interface OrganizationInvitation {
  id: string;
  organization_id: string;
  email: string;
  role: InvitationRole;
  invited_by_account_id: string;
  invited_by: OrganizationIdentitySummary;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface CreatedOrganizationInvitation
  extends OrganizationInvitation {
  accept_url: string;
}

export type ConversationStatus = "active" | "archived";
export type MessageRole = "user" | "assistant";
export type DocumentKind = "trial_data" | "research_document";
export type DocumentStatus = "pending" | "ready" | "failed";
export type M11SectionStatus = "draft" | "done";
export type M11RevisionAction =
  | "revised"
  | "done"
  | "reopened"
  | "generated"
  | "restored";

export interface Conversation {
  id: string;
  organization_id: string;
  owner_account_id: string;
  title: string;
  status: ConversationStatus;
  collaborator_account_ids: string[];
  created_at: string;
  updated_at: string;
  last_activity_at: string;
  archived_at: string | null;
}

export interface ConversationPage {
  items: Conversation[];
  next_cursor: string | null;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  organization_id: string;
  author_account_id: string | null;
  role: MessageRole;
  content: string;
  sequence: number;
  created_at: string;
}

export interface ConversationMessagePage {
  items: ConversationMessage[];
  next_cursor: string | null;
}

export interface DocumentRecord {
  id: string;
  conversation_id: string;
  organization_id: string;
  uploaded_by_account_id: string | null;
  kind: DocumentKind;
  filename: string;
  content_type: string;
  byte_size: number;
  status: DocumentStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentPage {
  items: DocumentRecord[];
  next_cursor: string | null;
}

export interface M11Section {
  id: string;
  conversation_id: string;
  organization_id: string;
  catalog_version: string;
  section_number: string;
  title: string;
  position: number;
  instructions: string;
  content: string;
  status: M11SectionStatus;
  current_revision: number;
  completed_at: string | null;
  completed_by_account_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface M11SectionWorkspace {
  catalog_version: string;
  items: M11Section[];
}

export interface M11SectionRevision {
  id: string;
  section_id: string;
  conversation_id: string;
  organization_id: string;
  revision_number: number;
  action: M11RevisionAction;
  instructions: string;
  content: string;
  status: M11SectionStatus;
  author_account_id: string | null;
  created_at: string;
}

export interface M11SectionRevisionPage {
  items: M11SectionRevision[];
  next_after_revision: number | null;
}

export type JobStatus =
  | "queued"
  | "running"
  | "retrying"
  | "succeeded"
  | "failed"
  | "cancelled";

export interface JobRecord {
  id: string;
  organization_id: string;
  conversation_id: string | null;
  kind: string;
  status: JobStatus;
  progress: number;
  attempt: number;
  error_code: string | null;
  correlation_id: string;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  cancel_requested_at: string | null;
}

export interface JobList {
  items: JobRecord[];
}

export interface GenerationAttemptRecord {
  section_number: string;
  status: string;
  error_code: string | null;
  citation_ids: string[];
  attempt: number;
}

export interface GenerationAttemptList {
  items: GenerationAttemptRecord[];
}

export interface RewriteOptionRecord {
  id: string;
  text: string;
}

export interface RewriteOptionList {
  items: RewriteOptionRecord[];
}

export interface EvidenceChunkRecord {
  id: string;
  conversation_id: string;
  organization_id: string;
  source_kind: string;
  source_identity: string;
  page_number: number | null;
  start_char: number;
  end_char: number;
  text: string;
}

export interface EvidenceChunkList {
  items: EvidenceChunkRecord[];
}
