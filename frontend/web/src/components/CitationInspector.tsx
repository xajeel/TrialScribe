import { useId } from "react";

import type { EvidenceChunkRecord } from "../api/types";
import { sourceKindLabel } from "../citations/citeMarkers";

const MISSING_COPY = "That source is not in this conversation.";

/** Side panel for one stored citation. Never copies or navigates away. */
export function CitationInspector({
  chunk,
  missing,
  onClose,
}: {
  chunk: EvidenceChunkRecord | null;
  missing: boolean;
  onClose: () => void;
}) {
  const titleId = useId();

  return (
    <aside className="citation-inspector" aria-labelledby={titleId}>
      <header className="citation-inspector__header">
        <h2 id={titleId}>Citation</h2>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </header>
      {missing || chunk === null ? (
        <p>{MISSING_COPY}</p>
      ) : (
        <dl className="citation-inspector__facts">
          <div>
            <dt>Source type</dt>
            <dd>{sourceKindLabel(chunk.source_kind)}</dd>
          </div>
          <div>
            <dt>Identity</dt>
            <dd>{chunk.source_identity}</dd>
          </div>
          <div>
            <dt>Page</dt>
            <dd>{chunk.page_number ?? "—"}</dd>
          </div>
          <div>
            <dt>Passage</dt>
            <dd>{chunk.text}</dd>
          </div>
        </dl>
      )}
    </aside>
  );
}
