import type {
  Conversation,
  ConversationMessage,
  DocumentRecord,
  M11Section,
} from "../api/types";
import type { ProtocolOverviewController } from "../workspace/useProtocolOverview";

/** Sample workspace data used only by the development review routes. */

const ORGANIZATION_ID = "00000000-0000-4000-8000-0000000000aa";
const OWNER_ID = "00000000-0000-4000-8000-0000000000bb";
const TEAMMATE_ID = "00000000-0000-4000-8000-0000000000cc";
const CONVERSATION_ID = "review-aurora";

export type InstructionsReview = "populated" | "empty";
export type ProgressReview = "populated" | "complete" | "attention" | "not-started";

export const REVIEW_WORKSPACE_ORGANIZATION = {
  id: ORGANIZATION_ID,
  name: "Northstar Clinical Research",
  role: "owner",
  created_at: "2026-07-01T09:00:00Z",
  owner_account_id: OWNER_ID,
} as const;

export const REVIEW_CONVERSATION: Conversation = {
  id: CONVERSATION_ID,
  organization_id: ORGANIZATION_ID,
  owner_account_id: OWNER_ID,
  title: "AURORA-301 — Phase III",
  status: "active",
  collaborator_account_ids: [TEAMMATE_ID],
  created_at: "2026-07-01T09:00:00Z",
  updated_at: "2026-07-31T14:32:00Z",
  last_activity_at: "2026-07-31T14:32:00Z",
  archived_at: null,
};

function otherConversation(
  id: string,
  title: string,
  lastActivity: string,
): Conversation {
  return {
    ...REVIEW_CONVERSATION,
    id,
    title,
    last_activity_at: lastActivity,
    updated_at: lastActivity,
  };
}

/** Four protocols, so the workbench rail is reviewable as a list. */
export const REVIEW_CONVERSATIONS: Conversation[] = [
  REVIEW_CONVERSATION,
  otherConversation("review-zephyr", "ZEPHYR-102 — Phase II", "2026-07-30T11:00:00Z"),
  otherConversation("review-titan", "TITAN-Global — Registry", "2026-07-21T09:30:00Z"),
  otherConversation("review-lunar", "LUNAR-5 — Phase I", "2026-07-18T16:20:00Z"),
];

function instruction(
  sequence: number,
  authorId: string,
  createdAt: string,
  content: string,
): ConversationMessage {
  return {
    id: `review-instruction-${sequence}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    author_account_id: authorId,
    role: "user",
    content,
    sequence,
    created_at: createdAt,
  };
}

const INSTRUCTIONS: ConversationMessage[] = [
  instruction(
    1,
    OWNER_ID,
    "2026-07-29T09:12:00Z",
    "Use protocol synopsis v3 as the design authority when documents disagree.",
  ),
  instruction(
    2,
    TEAMMATE_ID,
    "2026-07-29T10:45:00Z",
    "Keep eligibility criteria aligned with section 5.2 and cite the investigator brochure for safety exclusions.",
  ),
  instruction(
    3,
    OWNER_ID,
    "2026-07-29T13:58:00Z",
    "Use concise language suitable for regulatory review.\nAvoid repeating rationale from the Introduction, and keep every endpoint definition in a single paragraph so reviewers can compare them against the statistical analysis plan without scrolling between pages.",
  ),
];

const SECTION_TITLES = [
  "Protocol Summary",
  "Introduction",
  "Trial Objectives and Endpoints",
  "Trial Design",
  "Trial Population",
  "Trial Intervention",
  "Discontinuation",
  "Trial Assessments and Procedures",
  "Statistical Considerations",
  "General Considerations",
  "Oversight",
  "Supporting Documentation",
  "Appendices",
  "References",
] as const;

const DRAFTED_BODY = `Participants must meet all of the following inclusion criteria to be eligible for enrollment into the study. This population is selected to represent patients with moderate-to-severe plaque psoriasis who have failed at least one systemic therapy.

Male or female participants, aged 18 to 75 years inclusive at the time of signing the informed consent. Participants must have a documented diagnosis of chronic plaque psoriasis for at least 6 months prior to Screening.

A Psoriasis Area and Severity Index (PASI) score of at least 12 and Body Surface Area (BSA) involvement of at least 10% is required at both Screening and Baseline. For female participants of childbearing potential, a highly effective method of contraception must be used throughout the duration of the trial and for at least 90 days following the final dose.`;

function reviewSection(
  index: number,
  state: "done" | "drafted" | "empty",
): M11Section {
  const number = String(index + 1);
  return {
    id: `review-section-${number}`,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    catalog_version: "2025.1",
    section_number: number,
    title: SECTION_TITLES[index],
    position: index + 1,
    instructions: "",
    content: state === "empty" ? "" : DRAFTED_BODY,
    status: state === "done" ? "done" : "draft",
    current_revision: state === "empty" ? 0 : 3,
    completed_at: state === "done" ? "2026-07-30T17:05:00Z" : null,
    completed_by_account_id: state === "done" ? OWNER_ID : null,
    created_at: "2026-07-01T09:00:00Z",
    updated_at:
      state === "empty" ? "2026-07-01T09:00:00Z" : "2026-07-31T11:20:00Z",
  };
}

/** Eight done, three drafted, three untouched — the mixed mid-authoring state. */
export const MIXED_SECTIONS: M11Section[] = SECTION_TITLES.map((_, index) =>
  reviewSection(index, index < 8 ? "done" : index < 11 ? "drafted" : "empty"),
);

const COMPLETE_SECTIONS: M11Section[] = SECTION_TITLES.map((_, index) =>
  reviewSection(index, "done"),
);

function document(
  id: string,
  filename: string,
  kind: DocumentRecord["kind"],
  status: DocumentRecord["status"],
  byteSize: number,
  error: string | null = null,
): DocumentRecord {
  return {
    id,
    conversation_id: CONVERSATION_ID,
    organization_id: ORGANIZATION_ID,
    uploaded_by_account_id: OWNER_ID,
    kind,
    filename,
    content_type:
      kind === "trial_data" ? "application/json" : "application/pdf",
    byte_size: byteSize,
    status,
    error,
    created_at: "2026-07-29T09:00:00Z",
    updated_at: "2026-07-31T11:00:00Z",
  };
}

export const READY_DOCUMENTS: DocumentRecord[] = [
  document(
    "review-doc-1",
    "Investigator_Brochure_v4.pdf",
    "research_document",
    "ready",
    4_404_019,
  ),
  document(
    "review-doc-2",
    "Cohort_Analysis_Alpha.xlsx",
    "research_document",
    "ready",
    1_153_433,
  ),
  document(
    "review-doc-3",
    "aurora-301-trial-data.json",
    "trial_data",
    "ready",
    88_402,
  ),
];

export const ATTENTION_DOCUMENTS: DocumentRecord[] = [
  ...READY_DOCUMENTS,
  document(
    "review-doc-4",
    "Safety_Guidelines_2024_long_filename_for_wrapping.pdf",
    "research_document",
    "failed",
    6_882_110,
    "unsupported",
  ),
  document(
    "review-doc-5",
    "Phase_II_Interim_Report.pdf",
    "research_document",
    "pending",
    2_204_881,
  ),
];

function controller(
  instructions: ConversationMessage[],
  documents: DocumentRecord[],
  sections: M11Section[],
): ProtocolOverviewController {
  return {
    status: "ready",
    conversation: REVIEW_CONVERSATION,
    instructions,
    documents,
    sections,
    sectionsInitialized: sections.length > 0,
    action: "idle",
    feedback: null,
    retry: () => undefined,
    addInstruction: () => Promise.resolve(false),
    dismissFeedback: () => undefined,
  };
}

/** Fixture controller for the instruction review routes. */
export function reviewOverview(
  review: InstructionsReview,
): ProtocolOverviewController {
  return controller(
    review === "empty" ? [] : INSTRUCTIONS,
    READY_DOCUMENTS,
    MIXED_SECTIONS,
  );
}

/** Fixture controller for the progress review routes. */
export function reviewProgress(
  review: ProgressReview,
): ProtocolOverviewController {
  if (review === "complete") {
    return controller(INSTRUCTIONS, READY_DOCUMENTS, COMPLETE_SECTIONS);
  }
  if (review === "attention") {
    return controller(INSTRUCTIONS, ATTENTION_DOCUMENTS, MIXED_SECTIONS);
  }
  if (review === "not-started") {
    return controller(INSTRUCTIONS, [], []);
  }
  return controller(INSTRUCTIONS, READY_DOCUMENTS, MIXED_SECTIONS);
}
