import type { Conversation, M11Section, M11SectionStatus, UsageRecord } from "../api/types";
import {
  MIXED_SECTIONS,
  REVIEW_CONVERSATION,
} from "./workspaceReviewFixtures";

/** Presentation contracts and deterministic development data for Pages 16–17. */

export type ExportScope = "done-only" | "include-drafts";
export type ExportReviewState =
  | "configuration"
  | "drafts"
  | "building"
  | "ready"
  | "failed"
  | "empty";

export interface ExportManifestItem {
  id: string;
  sectionNumber: string;
  title: string;
  position: number;
  status: M11SectionStatus;
  words: number;
  revision: number;
  updatedAt: string;
}

export interface ExportView {
  protocolId: string;
  protocolTitle: string;
  catalogVersion: string | null;
  currentStatus: "Draft" | "Ready";
  sections: ReadonlyArray<ExportManifestItem>;
  doneSections: number;
  draftSections: number;
  citations?: number;
  references?: number;
  requester?: string;
  fixtureNote?: string;
}

export type ExportStageState = "complete" | "current" | "upcoming";

export interface ExportStage {
  id: "queued" | "assembling" | "citations" | "document";
  label: string;
  detail: string;
  state: ExportStageState;
}

export interface ExportFileView {
  exportId: string;
  filename: string;
  byteSize: number;
  sections: number;
  createdAt: string;
  requester: string;
  scope: ExportScope;
}

export interface ExportJobView {
  stages: ReadonlyArray<ExportStage>;
  readyFile: ExportFileView;
  recentExports: ReadonlyArray<ExportFileView>;
}

export type UsageOutcome =
  | "complete"
  | "issue"
  | "failed"
  | "cancelled"
  | "running";

export interface ProviderCallView {
  id: string;
  stage: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  result: string;
  costMicros: number | null;
}

export interface GenerationUsageView {
  id: string;
  jobId: string;
  scope: string;
  sectionNumbers: ReadonlyArray<string>;
  requester: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number | null;
  outcome: UsageOutcome;
  costMicros: number | null;
  pricingVersion: string;
  startedAt: string;
  completedAt: string | null;
  providerCalls: ReadonlyArray<ProviderCallView>;
}

export interface UsageSummaryView {
  totalCostMicros: number;
  inputTokens: number;
  outputTokens: number;
  successfulJobs: number;
  failedOrCancelled: number;
  generationCount: number;
  pricingBasis: string;
  updatedAt: string | null;
}

export interface UsageView {
  protocolId: string;
  protocolTitle: string;
  summary: UsageSummaryView;
  generations: ReadonlyArray<GenerationUsageView>;
  fixtureNote?: string;
}

function wordCount(content: string): number {
  const trimmed = content.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

/** Derive an export manifest without inventing document-production metadata. */
export function exportViewFromWorkspace(
  conversation: Conversation,
  sections: ReadonlyArray<M11Section>,
): ExportView {
  const ordered = [...sections].sort(
    (left, right) => left.position - right.position,
  );
  const doneSections = ordered.filter(
    (section) => section.status === "done",
  ).length;
  const catalogVersions = new Set(
    ordered.map((section) => section.catalog_version),
  );

  return {
    protocolId: conversation.id,
    protocolTitle: conversation.title,
    catalogVersion:
      catalogVersions.size === 1
        ? (catalogVersions.values().next().value ?? null)
        : null,
    currentStatus:
      ordered.length > 0 && doneSections === ordered.length ? "Ready" : "Draft",
    sections: ordered.map((section) => ({
      id: section.id,
      sectionNumber: section.section_number,
      title: section.title,
      position: section.position,
      status: section.status,
      words: wordCount(section.content),
      revision: section.current_revision,
      updatedAt: section.updated_at,
    })),
    doneSections,
    draftSections: ordered.length - doneSections,
  };
}

/** Convert integer currency micros into an exact, compact dollar value. */
export function formatCostMicros(value: number): string {
  const amount = (Math.max(0, value) / 1_000_000).toFixed(6);
  const compact = amount.replace(/0+$/, "").replace(/\.$/, "");
  const [whole, fraction = ""] = compact.split(".");
  return `$${whole}.${fraction.padEnd(2, "0")}`;
}

const exportBase = exportViewFromWorkspace(
  REVIEW_CONVERSATION,
  MIXED_SECTIONS,
);
export const REVIEW_EXPORT_VIEW: ExportView = {
  ...exportBase,
  catalogVersion: "ICH M11 Step 4",
  citations: 24,
  references: 11,
  requester: "Maya Chen",
  fixtureNote:
    "Development review data — export actions do not create or download a document.",
};

export const REVIEW_EXPORT_EMPTY: ExportView = {
  ...REVIEW_EXPORT_VIEW,
  sections: REVIEW_EXPORT_VIEW.sections.map((section) => ({
    ...section,
    status: "draft",
  })),
  doneSections: 0,
  draftSections: REVIEW_EXPORT_VIEW.sections.length,
  currentStatus: "Draft",
};

const READY_EXPORT: ExportFileView = {
  exportId: "EXP-00418",
  filename: "NSCR-AURORA-301_protocol_2026-07-29.docx",
  byteSize: 2_400_000,
  sections: 8,
  createdAt: "2026-07-29T14:38:00Z",
  requester: "Maya Chen",
  scope: "done-only",
};

export const REVIEW_EXPORT_JOB: ExportJobView = {
  stages: [
    {
      id: "queued",
      label: "Queued",
      detail: "Export request accepted",
      state: "complete",
    },
    {
      id: "assembling",
      label: "Assembling sections",
      detail: "Placing included sections in ICH M11 order",
      state: "current",
    },
    {
      id: "citations",
      label: "Resolving citations",
      detail: "Upcoming",
      state: "upcoming",
    },
    {
      id: "document",
      label: "Building document",
      detail: "Upcoming",
      state: "upcoming",
    },
  ],
  readyFile: READY_EXPORT,
  recentExports: [
    READY_EXPORT,
    {
      exportId: "EXP-00412",
      filename: "NSCR-AURORA-301_protocol_2026-07-28.docx",
      byteSize: 2_670_000,
      sections: 14,
      createdAt: "2026-07-28T17:06:00Z",
      requester: "Omar Shah",
      scope: "include-drafts",
    },
  ],
};

const GENERATION_RECORDS: ReadonlyArray<GenerationUsageView> = [
  {
    id: "usage-generation-1",
    jobId: "JOB-7729-X",
    scope: "Sections 5–6",
    sectionNumbers: ["5", "6"],
    requester: "Maya Chen",
    model: "DeepSeek V4 Pro",
    inputTokens: 88_420,
    outputTokens: 6_180,
    latencyMs: 14_200,
    outcome: "complete",
    costMicros: 840_000,
    pricingVersion: "DSP-2026-07",
    startedAt: "2026-07-29T14:31:42Z",
    completedAt: "2026-07-29T14:32:04Z",
    providerCalls: [
      {
        id: "provider-call-1",
        stage: "Drafting",
        model: "DeepSeek V4 Pro",
        inputTokens: 53_200,
        outputTokens: 4_812,
        latencyMs: 8_400,
        result: "Complete",
        costMicros: 510_000,
      },
      {
        id: "provider-call-2",
        stage: "Citation check",
        model: "DeepSeek V4 Pro",
        inputTokens: 35_220,
        outputTokens: 1_368,
        latencyMs: 5_800,
        result: "Complete",
        costMicros: 330_000,
      },
    ],
  },
  {
    id: "usage-generation-2",
    jobId: "JOB-7718-Q",
    scope: "Section 10",
    sectionNumbers: ["10"],
    requester: "Omar Shah",
    model: "DeepSeek V4 Pro",
    inputTokens: 57_840,
    outputTokens: 3_360,
    latencyMs: 11_600,
    outcome: "complete",
    costMicros: 570_000,
    pricingVersion: "DSP-2026-07",
    startedAt: "2026-07-29T11:07:38Z",
    completedAt: "2026-07-29T11:08:01Z",
    providerCalls: [],
  },
  {
    id: "usage-generation-3",
    jobId: "JOB-7694-M",
    scope: "Section 9",
    sectionNumbers: ["9"],
    requester: "Maya Chen",
    model: "DeepSeek V4 Pro",
    inputTokens: 44_210,
    outputTokens: 3_690,
    latencyMs: 12_400,
    outcome: "issue",
    costMicros: 390_000,
    pricingVersion: "DSP-2026-07",
    startedAt: "2026-07-28T17:43:27Z",
    completedAt: "2026-07-28T17:44:02Z",
    providerCalls: [],
  },
  {
    id: "usage-generation-running",
    jobId: "JOB-7740-R",
    scope: "Section 12",
    sectionNumbers: ["12"],
    requester: "Maya Chen",
    model: "DeepSeek V4 Pro",
    inputTokens: 0,
    outputTokens: 0,
    latencyMs: null,
    outcome: "running",
    costMicros: null,
    pricingVersion: "DSP-2026-07",
    startedAt: "2026-07-29T14:40:00Z",
    completedAt: null,
    providerCalls: [],
  },
];

export const REVIEW_USAGE_VIEW: UsageView = {
  protocolId: REVIEW_CONVERSATION.id,
  protocolTitle: REVIEW_CONVERSATION.title,
  summary: {
    totalCostMicros: 12_460_000,
    inputTokens: 1_284_620,
    outputTokens: 74_890,
    successfulJobs: 17,
    failedOrCancelled: 1,
    generationCount: 18,
    pricingBasis: "Versioned provider pricing",
    updatedAt: "2026-07-29T14:32:00Z",
  },
  generations: GENERATION_RECORDS.slice(0, 3),
  fixtureNote:
    "Development review data — costs and provider calls are illustrative and not persisted.",
};

export const REVIEW_USAGE_RUNNING: UsageView = {
  ...REVIEW_USAGE_VIEW,
  generations: [GENERATION_RECORDS[3], ...REVIEW_USAGE_VIEW.generations],
};

export function emptyUsageView(
  protocolId: string,
  protocolTitle: string,
  fixtureNote?: string,
): UsageView {
  return {
    protocolId,
    protocolTitle,
    summary: {
      totalCostMicros: 0,
      inputTokens: 0,
      outputTokens: 0,
      successfulJobs: 0,
      failedOrCancelled: 0,
      generationCount: 0,
      pricingBasis: "Versioned provider pricing",
      updatedAt: null,
    },
    generations: [],
    fixtureNote,
  };
}

export const REVIEW_USAGE_EMPTY = emptyUsageView(
  REVIEW_CONVERSATION.id,
  REVIEW_CONVERSATION.title,
  "Development review data — no stored usage was read.",
);

const USAGE_OUTCOMES: ReadonlySet<UsageOutcome> = new Set([
  "complete",
  "issue",
  "failed",
  "cancelled",
  "running",
]);

function usageOutcome(value: string): UsageOutcome {
  return USAGE_OUTCOMES.has(value as UsageOutcome)
    ? (value as UsageOutcome)
    : "running";
}

/** Map a stored usage snapshot into the Usage sheet view. */
export function usageViewFromApi(record: UsageRecord): UsageView {
  return {
    protocolId: record.protocol_id,
    protocolTitle: record.protocol_title,
    summary: {
      totalCostMicros: record.summary.total_cost_micros,
      inputTokens: record.summary.input_tokens,
      outputTokens: record.summary.output_tokens,
      successfulJobs: record.summary.successful_jobs,
      failedOrCancelled: record.summary.failed_or_cancelled,
      generationCount: record.summary.generation_count,
      pricingBasis: record.summary.pricing_basis,
      updatedAt: record.summary.updated_at,
    },
    generations: record.generations.map((item) => ({
      id: item.id,
      jobId: item.job_id,
      scope: item.scope,
      sectionNumbers: item.section_numbers,
      requester: item.requester,
      model: item.model,
      inputTokens: item.input_tokens,
      outputTokens: item.output_tokens,
      latencyMs: item.latency_ms,
      outcome: usageOutcome(item.outcome),
      costMicros: item.cost_micros,
      pricingVersion: item.pricing_version,
      startedAt: item.started_at ?? "",
      completedAt: item.completed_at,
      providerCalls: item.provider_calls.map((call) => ({
        id: call.id,
        stage: call.stage,
        model: call.model,
        inputTokens: call.input_tokens,
        outputTokens: call.output_tokens,
        latencyMs: call.latency_ms,
        result: call.result,
        costMicros: call.cost_micros,
      })),
    })),
  };
}
