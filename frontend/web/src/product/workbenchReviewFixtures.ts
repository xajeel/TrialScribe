import type { DocumentRecord, M11Section } from "../api/types";
import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import {
  ATTENTION_DOCUMENTS,
  MIXED_SECTIONS,
  READY_DOCUMENTS,
  REVIEW_CONVERSATION,
  REVIEW_CONVERSATIONS,
} from "./workspaceReviewFixtures";

/** Sample workbench data used only by the development review routes. */

export type WorkbenchReview = "populated" | "empty";
export type SourcesReview = "populated" | "empty";
export type ReaderReview = "draft" | "done" | "empty";

/** The section each reader review route opens. */
export function reviewReaderSection(review: ReaderReview): M11Section {
  if (review === "done") {
    return MIXED_SECTIONS[0];
  }
  if (review === "empty") {
    return MIXED_SECTIONS[13];
  }
  return MIXED_SECTIONS[8];
}

/**
 * The workbench review route opens on a section being written, since the
 * editing controls are the point of the screen. Trial Population is therefore
 * a draft here, with eight other sections done.
 */
const WORKBENCH_SECTIONS: M11Section[] = MIXED_SECTIONS.map((section, index) =>
  index === 4
    ? { ...section, status: "draft", completed_at: null, completed_by_account_id: null }
    : index === 11
      ? { ...section, status: "done", completed_at: "2026-07-30T17:05:00Z" }
      : section,
);

function controller(
  documents: DocumentRecord[],
  sections: M11Section[],
): AuthoringWorkspaceController {
  const selected = sections[4] ?? null;
  return {
    conversationStatus: "ready",
    workspaceStatus: "ready",
    conversations: REVIEW_CONVERSATIONS,
    selectedConversationId: REVIEW_CONVERSATION.id,
    selectedConversation: REVIEW_CONVERSATION,
    messages: [],
    documents,
    sections,
    selectedSectionNumber: selected?.section_number ?? null,
    selectedSection: selected,
    action: "idle",
    feedback: null,
    selectConversation: () => undefined,
    selectSection: () => undefined,
    retryConversations: () => undefined,
    retryWorkspace: () => undefined,
    dismissFeedback: () => undefined,
    create: () => Promise.resolve(false),
    rename: () => Promise.resolve(false),
    appendInstruction: () => Promise.resolve(false),
    upload: () => Promise.resolve(false),
    removeDocument: () => Promise.resolve(false),
    saveSection: () => Promise.resolve(false),
    markDone: () => Promise.resolve(false),
    reopen: () => Promise.resolve(false),
  };
}

/** Fixture controller for the workbench review routes. */
export function reviewWorkbench(
  review: WorkbenchReview,
): AuthoringWorkspaceController {
  if (review === "empty") {
    return controller([], WORKBENCH_SECTIONS);
  }
  return controller(READY_DOCUMENTS, WORKBENCH_SECTIONS);
}

/** Fixture controller for the source library review routes. */
export function reviewSources(
  review: SourcesReview,
): AuthoringWorkspaceController {
  if (review === "empty") {
    return controller([], WORKBENCH_SECTIONS);
  }
  return controller(ATTENTION_DOCUMENTS, WORKBENCH_SECTIONS);
}
