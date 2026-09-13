import { Link } from "react-router-dom";

import type { DocumentRecord } from "../api/types";

const KIND_LABELS: Record<DocumentRecord["kind"], string> = {
  trial_data: "Trial data",
  research_document: "Research document",
};

const STATUS_LABELS: Record<DocumentRecord["status"], string> = {
  ready: "Ready",
  pending: "Processing",
  failed: "Failed",
};

/** Human-readable file size from the stored byte count. */
export function formatSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(0)} KB`;
  }
  return `${(kilobytes / 1024).toFixed(1)} MB`;
}

/** Uploaded sources and their real processing state. */
export function SourceProcessingList({
  documents,
  conversationId,
}: {
  documents: DocumentRecord[];
  conversationId: string;
}) {
  if (documents.length === 0) {
    return (
      <p className="source-list__empty">
        No sources uploaded yet.{" "}
        <Link to={`/workspace/${encodeURIComponent(conversationId)}`}>
          Add trial data and research documents
        </Link>{" "}
        in the workspace.
      </p>
    );
  }

  return (
    <ul className="source-list">
      {documents.map((record) => (
        <li className="source-list__item" key={record.id}>
          <div className="source-list__identity">
            <span className="source-list__name">{record.filename}</span>
            <span className="source-list__meta">
              {KIND_LABELS[record.kind]} · {formatSize(record.byte_size)}
            </span>
          </div>
          <span
            className={`source-list__status source-list__status--${record.status}`}
          >
            {STATUS_LABELS[record.status]}
          </span>
        </li>
      ))}
    </ul>
  );
}
