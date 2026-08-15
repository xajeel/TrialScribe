import type {
  Conversation,
  DocumentRecord,
  M11Section,
  M11SectionRevision,
  M11SectionStatus,
  OrganizationIdentitySummary,
} from "../api/types";
import {
  ATTENTION_DOCUMENTS,
  MIXED_SECTIONS,
  READY_DOCUMENTS,
  REVIEW_CONVERSATION,
} from "./workspaceReviewFixtures";

/**
 * Presentation contracts and deterministic development data for Pages 14 and
 * 15. Review fixtures are not API results and do not describe a real trial.
 */

export type RevisionDisplayAction =
  | "edited"
  | "generated"
  | "marked-done"
  | "reopened"
  | "restored";

export interface RevisionRowView {
  id: string;
  revisionNumber: number;
  action: RevisionDisplayAction;
  actionLabel: string;
  authorLabel: string;
  authorId: string | null;
  createdAt: string;
  summary: string;
  status: M11SectionStatus;
  current: boolean;
  words: number;
  wordDelta?: string;
  sourceSummary?: string;
  citationSummary?: string;
  content: string;
  instructions: string;
}

export type GovernanceDiffKind = "unchanged" | "added" | "removed";

export interface GovernanceDiffSegment {
  kind: GovernanceDiffKind;
  text: string;
}

export interface RevisionComparisonView {
  earlier: RevisionRowView;
  later: RevisionRowView;
  additions?: number;
  removals?: number;
  citationChanges?: number;
  earlierSegments?: ReadonlyArray<GovernanceDiffSegment>;
  laterSegments?: ReadonlyArray<GovernanceDiffSegment>;
}

export type ReadinessSeverity = "warning" | "error";
export type ReadinessAction =
  | "open-section"
  | "view-history"
  | "view-sources"
  | "review-citation"
  | "retry-demo";

export interface ReadinessIssueView {
  id: string;
  title: string;
  detail: string;
  severity: ReadinessSeverity;
  sectionNumber?: string;
  action?: ReadinessAction;
  actionLabel?: string;
  state?: "open" | "retrying" | "resolved";
}

export interface ReadinessSectionView {
  id: string;
  sectionNumber: string;
  title: string;
  position: number;
  status: M11SectionStatus;
  revision: number;
  words: number;
  updatedAt: string;
  content: string;
  issues: ReadonlyArray<ReadinessIssueView>;
  citations?: {
    resolved: number;
    needingReview: number;
  };
}

export interface ReadinessSummaryView {
  totalSections: number;
  doneSections: number;
  draftSections: number;
  readySources: number;
  pendingSources: number;
  failedSources: number;
  latestActivity: string | null;
  citations?: {
    resolved: number;
    needingReview: number;
  };
}

export interface ReadinessView {
  protocolTitle: string;
  protocolId: string;
  summary: ReadinessSummaryView;
  issues: ReadonlyArray<ReadinessIssueView>;
  sections: ReadonlyArray<ReadinessSectionView>;
  ready: boolean;
  fixtureNote?: string;
}

export type GovernanceReviewState =
  | "revisions-timeline"
  | "revisions-preview"
  | "revisions-empty"
  | "revisions-compare"
  | "revisions-restore"
  | "revisions-restored"
  | "readiness-incomplete"
  | "readiness-attention"
  | "readiness-filtered"
  | "readiness-ready"
  | "readiness-retry";

function wordCount(content: string): number {
  const trimmed = content.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

/** Convert an API revision without inventing a collaborator's name. */
export function revisionViewFromApi(
  revision: M11SectionRevision,
  currentRevision: number,
  accountId: string | null,
  identities: Readonly<Record<string, OrganizationIdentitySummary>>,
): RevisionRowView {
  const action =
    revision.action === "done"
      ? "marked-done"
      : revision.action === "reopened"
        ? "reopened"
        : revision.action === "generated"
          ? "generated"
          : revision.action === "restored"
            ? "restored"
            : "edited";
  const authorLabel =
    revision.author_account_id === null
      ? "System"
      : revision.author_account_id === accountId
        ? "You"
        : (identities[revision.author_account_id]?.email ??
          "Unavailable account");
  const summaries: Record<RevisionDisplayAction, string> = {
    edited: "Section wording updated",
    generated: "Generated section snapshot",
    "marked-done": "Section marked Done",
    reopened: "Section returned to Draft",
    restored: "Earlier snapshot copied into a new revision",
  };
  return {
    id: revision.id,
    revisionNumber: revision.revision_number,
    action,
    actionLabel:
      action === "marked-done"
        ? "Marked done"
        : action[0].toUpperCase() + action.slice(1),
    authorLabel,
    authorId: revision.author_account_id,
    createdAt: revision.created_at,
    summary: summaries[action],
    status: revision.status,
    current: revision.revision_number === currentRevision,
    words: wordCount(revision.content),
    content: revision.content,
    instructions: revision.instructions,
  };
}

function latestIso(values: ReadonlyArray<string>): string | null {
  if (values.length === 0) {
    return null;
  }
  return [...values].sort((left, right) => right.localeCompare(left))[0] ?? null;
}

/** Derive only readiness facts supported by current section/document records. */
export function readinessFromWorkspace(
  conversation: Conversation,
  sections: ReadonlyArray<M11Section>,
  documents: ReadonlyArray<DocumentRecord>,
): ReadinessView {
  const ordered = [...sections].sort(
    (left, right) => left.position - right.position,
  );
  const issues: ReadinessIssueView[] = [];

  for (const record of documents) {
    if (record.status === "failed") {
      issues.push({
        id: `source-failed-${record.id}`,
        title: "Source could not be prepared",
        detail: record.filename,
        severity: "error",
        action: "view-sources",
        actionLabel: "View sources",
      });
    } else if (record.status === "pending") {
      issues.push({
        id: `source-pending-${record.id}`,
        title: "Source processing is not complete",
        detail: record.filename,
        severity: "warning",
        action: "view-sources",
        actionLabel: "View sources",
      });
    }
  }

  const sectionViews = ordered.map((section): ReadinessSectionView => {
    const sectionIssues: ReadinessIssueView[] = [];
    if (section.status === "draft" && section.content.trim() === "") {
      const issue: ReadinessIssueView = {
        id: `empty-section-${section.id}`,
        title: "Section has no content",
        detail: `${section.section_number} · ${section.title}`,
        severity: "warning",
        sectionNumber: section.section_number,
        action: "open-section",
        actionLabel: "Open section",
      };
      sectionIssues.push(issue);
      issues.push(issue);
    }
    return {
      id: section.id,
      sectionNumber: section.section_number,
      title: section.title,
      position: section.position,
      status: section.status,
      revision: section.current_revision,
      words: wordCount(section.content),
      updatedAt: section.updated_at,
      content: section.content,
      issues: sectionIssues,
    };
  });

  const doneSections = ordered.filter(
    (section) => section.status === "done",
  ).length;
  const readySources = documents.filter(
    (record) => record.status === "ready",
  ).length;
  const pendingSources = documents.filter(
    (record) => record.status === "pending",
  ).length;
  const failedSources = documents.filter(
    (record) => record.status === "failed",
  ).length;
  const ready =
    ordered.length > 0 &&
    doneSections === ordered.length &&
    pendingSources === 0 &&
    failedSources === 0;

  return {
    protocolTitle: conversation.title,
    protocolId: conversation.id,
    summary: {
      totalSections: ordered.length,
      doneSections,
      draftSections: ordered.length - doneSections,
      readySources,
      pendingSources,
      failedSources,
      latestActivity: latestIso([
        conversation.last_activity_at,
        ...ordered.map((section) => section.updated_at),
        ...documents.map((record) => record.updated_at),
      ]),
    },
    issues,
    sections: sectionViews,
    ready,
  };
}

const REVISION_CONTENT_6 =
  "Participants must provide informed consent and have documented clinical stability before screening. Adults aged 18 to 75 years with ECOG performance status 0 or 1 may be enrolled.";
const REVISION_CONTENT_7 =
  "Participants must provide written informed consent and demonstrate documented clinical stability before screening. Adults aged 18 to 75 years with ECOG performance status 0 or 1 may be enrolled [S3, p. 14].";

function reviewRevision(
  revisionNumber: number,
  action: RevisionDisplayAction,
  overrides: Partial<RevisionRowView> = {},
): RevisionRowView {
  const labels: Record<RevisionDisplayAction, string> = {
    edited: "Edited",
    generated: "Generated draft",
    "marked-done": "Marked done",
    reopened: "Reopened",
    restored: "Restored",
  };
  return {
    id: `review-revision-${revisionNumber}`,
    revisionNumber,
    action,
    actionLabel: labels[action],
    authorLabel: action === "generated" ? "Requested by Maya Chen" : "Maya Chen",
    authorId: "review-account-maya",
    createdAt: `2026-07-${revisionNumber === 7 ? "29T14:32" : "28T17:05"}:00Z`,
    summary:
      action === "generated"
        ? "Section generated from six review sources"
        : action === "reopened"
          ? "Section returned to Draft"
          : action === "marked-done"
            ? "Section locked as completed"
            : "Eligibility wording refined",
    status: action === "marked-done" ? "done" : "draft",
    current: revisionNumber === 7,
    words: revisionNumber === 6 ? 1246 : 1284,
    content: revisionNumber === 6 ? REVISION_CONTENT_6 : REVISION_CONTENT_7,
    instructions: "Keep eligibility wording concise and evidence-linked.",
    ...overrides,
  };
}

export const REVISION_REVIEW_ROWS: ReadonlyArray<RevisionRowView> = [
  reviewRevision(7, "edited", {
    wordDelta: "+84 −27 words",
    citationSummary: "1 citation added",
  }),
  reviewRevision(6, "generated", {
    createdAt: "2026-07-29T14:12:00Z",
    sourceSummary: "6 sources",
  }),
  reviewRevision(5, "reopened", { createdAt: "2026-07-29T13:48:00Z" }),
  reviewRevision(4, "marked-done", { createdAt: "2026-07-28T17:05:00Z" }),
  reviewRevision(3, "edited", {
    createdAt: "2026-07-28T16:42:00Z",
    authorLabel: "Omar Shah",
    wordDelta: "+42 −18 words",
    summary: "Safety exclusions clarified",
  }),
];

export const REVISION_REVIEW_COMPARISON: RevisionComparisonView = {
  earlier: REVISION_REVIEW_ROWS[1],
  later: REVISION_REVIEW_ROWS[0],
  additions: 12,
  removals: 4,
  citationChanges: 1,
  earlierSegments: [
    { kind: "unchanged", text: "Participants must provide " },
    { kind: "removed", text: "informed consent" },
    { kind: "unchanged", text: " and have documented clinical stability before screening." },
  ],
  laterSegments: [
    { kind: "unchanged", text: "Participants must provide " },
    { kind: "added", text: "written informed consent" },
    { kind: "unchanged", text: " and demonstrate documented clinical stability before screening. " },
    { kind: "added", text: "Evidence reference [S3, p. 14] added." },
  ],
};

function readinessFixture(ready: boolean): ReadinessView {
  const sections = ready
    ? MIXED_SECTIONS.map((section) => ({
        ...section,
        status: "done" as const,
        completed_at: "2026-07-31T14:32:00Z",
        current_revision: Math.max(section.current_revision, 1),
      }))
    : MIXED_SECTIONS;
  const base = readinessFromWorkspace(
    REVIEW_CONVERSATION,
    sections,
    ready ? READY_DOCUMENTS : ATTENTION_DOCUMENTS,
  );
  if (ready) {
    return {
      ...base,
      summary: {
        ...base.summary,
        citations: { resolved: 28, needingReview: 0 },
      },
      ready: true,
      fixtureNote: "Development review data — no approval or export is performed.",
    };
  }

  const citationIssue: ReadinessIssueView = {
    id: "review-citation-s8",
    title: "Citation evidence unavailable",
    detail: "Section 9 · Citation [S8]",
    severity: "warning",
    sectionNumber: "9",
    action: "review-citation",
    actionLabel: "Open citation",
  };
  const retryIssue: ReadinessIssueView = {
    id: "review-generation-6",
    title: "Generation completed with an issue",
    detail: "6 · Trial Intervention",
    severity: "error",
    sectionNumber: "6",
    action: "retry-demo",
    actionLabel: "Retry demonstration",
    state: "open",
  };
  const issues = [citationIssue, ...base.issues.slice(0, 2), retryIssue];
  const rows = base.sections.map((section) =>
    section.sectionNumber === "9"
      ? {
          ...section,
          citations: { resolved: 5, needingReview: 1 },
          issues: [citationIssue],
        }
      : section.sectionNumber === "6"
        ? { ...section, issues: [retryIssue] }
        : section,
  );
  return {
    ...base,
    summary: {
      ...base.summary,
      citations: { resolved: 24, needingReview: 1 },
    },
    issues,
    sections: rows,
    ready: false,
    fixtureNote: "Development review data — actions do not change stored protocol content.",
  };
}

export const READINESS_REVIEW_INCOMPLETE = readinessFixture(false);
export const READINESS_REVIEW_READY = readinessFixture(true);

export function revisionRowsForReview(
  state: GovernanceReviewState,
): ReadonlyArray<RevisionRowView> {
  return state === "revisions-empty" ? [] : REVISION_REVIEW_ROWS;
}

export function readinessForReview(state: GovernanceReviewState): ReadinessView {
  if (state === "readiness-ready") {
    return READINESS_REVIEW_READY;
  }
  if (state === "readiness-retry") {
    return {
      ...READINESS_REVIEW_INCOMPLETE,
      issues: READINESS_REVIEW_INCOMPLETE.issues.map((issue) =>
        issue.action === "retry-demo" ? { ...issue, state: "retrying" } : issue,
      ),
    };
  }
  return READINESS_REVIEW_INCOMPLETE;
}
