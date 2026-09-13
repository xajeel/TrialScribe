/** Canonical `[cite:<uuid>]` markers, matching the worker's 8-4-4-4-12 hex form. */
export const CITE_MARKER =
  /\[cite:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]/g;

export type CitedPart =
  | { type: "text"; value: string }
  | { type: "cite"; id: string };

/** Split stored section content into plain text and citation markers. */
export function splitCitedText(content: string): CitedPart[] {
  const parts: CitedPart[] = [];
  let cursor = 0;
  const pattern = new RegExp(CITE_MARKER.source, "g");
  for (const match of content.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      parts.push({ type: "text", value: content.slice(cursor, start) });
    }
    parts.push({ type: "cite", id: match[1] ?? "" });
    cursor = start + match[0].length;
  }
  if (cursor < content.length) {
    parts.push({ type: "text", value: content.slice(cursor) });
  }
  return parts;
}

export function sourceKindLabel(kind: string): string {
  if (kind === "trial_data") {
    return "Trial data";
  }
  if (kind === "research_document") {
    return "Uploaded document";
  }
  if (kind === "web") {
    return "Internet source";
  }
  return "Other source";
}
