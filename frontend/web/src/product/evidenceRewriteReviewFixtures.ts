/**
 * Development review data for Pages 12 and 13. These records exercise the
 * presentation contract only; they are not API results or real trial data.
 */

export type EvidenceReviewKind = "pdf" | "json" | "web" | "section";

interface EvidenceReviewBase {
  kind: EvidenceReviewKind;
  sourceTitle: string;
  sourceLabel: string;
  passage: string;
  locator: string;
  support: string;
  citation: string;
}

export interface PdfEvidenceReviewRecord extends EvidenceReviewBase {
  kind: "pdf";
  page: number;
  paragraph: number;
  documentType: "Research document";
}

export interface JsonEvidenceReviewRecord extends EvidenceReviewBase {
  kind: "json";
  node: string;
  fields: ReadonlyArray<{
    label: string;
    value: string;
  }>;
  documentType: "Trial data";
}

export interface WebEvidenceReviewRecord extends EvidenceReviewBase {
  kind: "web";
  publication: string;
  domain: string;
  accessed: string;
  articleTitle: string;
  documentType: "Controlled web research";
}

export interface SectionEvidenceReviewRecord extends EvidenceReviewBase {
  kind: "section";
  page: number;
  paragraph: number;
  referenceId: string;
  documentType: "Research document";
  annotation: string;
}

export type EvidenceReviewRecord =
  | PdfEvidenceReviewRecord
  | JsonEvidenceReviewRecord
  | WebEvidenceReviewRecord
  | SectionEvidenceReviewRecord;

export type RewriteReviewStage =
  | "selection"
  | "whole"
  | "alternatives"
  | "confirm"
  | "compare";

export type DiffSegmentKind = "unchanged" | "added" | "removed";

export interface DiffSegment {
  kind: DiffSegmentKind;
  text: string;
}

export interface RewriteAlternative {
  id: "alternative-1" | "alternative-2";
  label: string;
  text: string;
  recommended: boolean;
  wordDelta: number;
  citations: ReadonlyArray<string>;
  segments: ReadonlyArray<DiffSegment>;
}

export interface RewriteReviewFixture {
  protocolTitle: string;
  sectionNumber: string;
  sectionTitle: string;
  currentRevision: number;
  nextRevision: number;
  originalText: string;
  selectedText: string;
  instruction: string;
  wholeInstruction: string;
  alternatives: ReadonlyArray<RewriteAlternative>;
  oldSegments: ReadonlyArray<DiffSegment>;
  currentSegments: ReadonlyArray<DiffSegment>;
  additions: number;
  removals: number;
}

export const EVIDENCE_REVIEW_FIXTURES: Record<
  EvidenceReviewKind,
  EvidenceReviewRecord
> = {
  pdf: {
    kind: "pdf",
    sourceTitle: "investigator_brochure_v8.pdf",
    sourceLabel: "Investigator brochure, edition 8",
    documentType: "Research document",
    passage:
      "Participants must demonstrate clinical stability and maintain an ECOG performance status of 0 or 1 throughout the induction phase.",
    locator: "Page 14, paragraph 3",
    support:
      "Directly supports the section requirement for ECOG performance status at screening.",
    citation: "[S3, p. 14]",
    page: 14,
    paragraph: 3,
  },
  json: {
    kind: "json",
    sourceTitle: "aurora_301_trial_data.json",
    sourceLabel: "AURORA-301 structured trial data",
    documentType: "Trial data",
    passage:
      "Eligibility criterion 3 requires ECOG performance status of 0 or 1 at screening.",
    locator: "eligibility.inclusion_criteria[2]",
    support:
      "The structured criterion aligns with the eligibility statement in this section.",
    citation: "[Trial data: eligibility.inclusion_criteria[2]]",
    node: "eligibility.inclusion_criteria[2]",
    fields: [
      { label: "Criterion", value: "ECOG performance status" },
      { label: "Condition", value: "0 or 1" },
      { label: "Timing", value: "At screening" },
    ],
  },
  web: {
    kind: "web",
    sourceTitle: "Stored research finding",
    sourceLabel: "Journal of Clinical Oncology (2024)",
    documentType: "Controlled web research",
    passage:
      "The validation study reported lower manual data-entry error rates while preserving traceable source links.",
    locator: "Stored passage accessed October 24, 2024",
    support:
      "Provides contextual support for the traceability statement in the protocol rationale.",
    citation: "[Web finding 1]",
    publication: "Journal of Clinical Oncology",
    domain: "ascopubs.org",
    accessed: "October 24, 2024",
    articleTitle:
      "AI-assisted documentation in high-volume clinical environments",
  },
  section: {
    kind: "section",
    sourceTitle: "Investigator's Brochure",
    sourceLabel: "TR-882 compound summary, edition 5",
    documentType: "Research document",
    passage:
      "Steady-state plasma levels in hepatic-impaired participants showed an average increase in exposure compared with healthy controls.",
    locator: "Page 14, paragraph 3",
    support:
      "Direct support for the selected pharmacokinetic statement in Section 4.2.",
    citation: "[S3, p. 14]",
    page: 14,
    paragraph: 3,
    referenceId: "REF-882-03",
    annotation:
      "Cross-reference this passage with the toxicology summary before final review.",
  },
};

const ORIGINAL_TEXT =
  "The primary objective is to evaluate the change from baseline in forced vital capacity at Week 52. Secondary endpoints include time to first acute exacerbation and quality-of-life assessments.";

const ALTERNATIVE_ONE =
  "Primary efficacy will be assessed by the mean change in forced vital capacity from baseline to Week 52. Secondary outcomes comprise acute exacerbations and changes in quality-of-life scores.";

const ALTERNATIVE_TWO =
  "The study evaluates change in forced vital capacity through Week 52, with acute exacerbations and quality-of-life measures serving as secondary clinical outcomes.";

export const REWRITE_REVIEW_FIXTURE: RewriteReviewFixture = {
  protocolTitle: "AURORA-301 — Phase III",
  sectionNumber: "5.1",
  sectionTitle: "Overall Study Design and Plan",
  currentRevision: 7,
  nextRevision: 8,
  originalText: ORIGINAL_TEXT,
  selectedText: ORIGINAL_TEXT,
  instruction:
    "Make the rationale more concise without changing the endpoints or removing citations.",
  wholeInstruction:
    "Refresh the section for regulatory clarity while preserving its evidence references.",
  alternatives: [
    {
      id: "alternative-1",
      label: "Alternative 1",
      text: ALTERNATIVE_ONE,
      recommended: true,
      wordDelta: -5,
      citations: ["Kept [S1]", "Added [S3, p. 14]"],
      segments: [
        { kind: "unchanged", text: "Primary efficacy will be assessed by " },
        { kind: "added", text: "the mean " },
        {
          kind: "unchanged",
          text: "change in forced vital capacity from baseline to Week 52. ",
        },
        {
          kind: "added",
          text: "Secondary outcomes comprise acute exacerbations and changes in quality-of-life scores.",
        },
      ],
    },
    {
      id: "alternative-2",
      label: "Alternative 2",
      text: ALTERNATIVE_TWO,
      recommended: false,
      wordDelta: -12,
      citations: ["Kept [S1]"],
      segments: [
        { kind: "unchanged", text: "The study evaluates " },
        { kind: "added", text: "change in forced vital capacity through " },
        { kind: "unchanged", text: "Week 52, " },
        {
          kind: "added",
          text: "with acute exacerbations and quality-of-life measures serving as secondary clinical outcomes.",
        },
      ],
    },
  ],
  oldSegments: [
    {
      kind: "unchanged",
      text: "The primary objective is to evaluate the change from baseline in forced vital capacity at Week 52. ",
    },
    {
      kind: "removed",
      text: "Secondary endpoints include time to first acute exacerbation and quality-of-life assessments.",
    },
  ],
  currentSegments: [
    {
      kind: "unchanged",
      text: "Primary efficacy will be assessed by the mean change in forced vital capacity from baseline to Week 52. ",
    },
    {
      kind: "added",
      text: "Secondary outcomes comprise acute exacerbations and changes in quality-of-life scores [S3, p. 14].",
    },
  ],
  additions: 12,
  removals: 4,
};
