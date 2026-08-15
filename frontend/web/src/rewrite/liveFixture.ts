import type { M11Section, RewriteOptionRecord } from "../api/types";
import type {
  RewriteAlternative,
  RewriteReviewFixture,
} from "../product/evidenceRewriteReviewFixtures";
import { diffSegments } from "./diffSegments";

function wordCount(value: string): number {
  const trimmed = value.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

function counted(kind: "added" | "removed", original: string, next: string): number {
  return diffSegments(original, next)
    .filter((segment) => segment.kind === kind)
    .reduce((total, segment) => total + wordCount(segment.text), 0);
}

/** Build the existing rewrite panel contract from live options. */
export function liveRewriteFixture(
  section: M11Section,
  options: ReadonlyArray<RewriteOptionRecord>,
  originalContent: string,
): RewriteReviewFixture {
  const alternatives: RewriteAlternative[] = options.slice(0, 2).map(
    (option, index) => {
      const id: RewriteAlternative["id"] =
        index === 0 ? "alternative-1" : "alternative-2";
      return {
        id,
        label: `Alternative ${index + 1}`,
        text: option.text,
        recommended: index === 0,
        wordDelta: wordCount(option.text) - wordCount(originalContent),
        citations: [],
        segments: diffSegments(originalContent, option.text),
      };
    },
  );
  const first = alternatives[0];
  return {
    protocolTitle: "",
    sectionNumber: section.section_number,
    sectionTitle: section.title,
    currentRevision: section.current_revision,
    nextRevision: section.current_revision + 1,
    originalText: originalContent,
    selectedText: originalContent,
    instruction: "",
    wholeInstruction: "",
    alternatives,
    oldSegments: first
      ? diffSegments(originalContent, first.text).filter(
          (segment) => segment.kind !== "added",
        )
      : [{ kind: "unchanged", text: originalContent }],
    currentSegments: first?.segments ?? [{ kind: "unchanged", text: originalContent }],
    additions: first ? counted("added", originalContent, first.text) : 0,
    removals: first ? counted("removed", originalContent, first.text) : 0,
  };
}
