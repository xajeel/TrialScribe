import type { DocumentKind, DocumentRecord } from "../api/types";

const STATUS_LABELS: Record<DocumentRecord["status"], string> = {
  ready: "Ready",
  pending: "Processing",
  failed: "Failed",
};

const GROUPS: { kind: DocumentKind; title: string }[] = [
  { kind: "trial_data", title: "Trial data" },
  { kind: "research_document", title: "Research documents" },
];

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

/** Upload date in the stable form used across the workspace surfaces. */
export function formatUploaded(isoDate: string): string {
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown date";
  }
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/** Split sources into the two kinds the backend stores, preserving order. */
export function groupSources(
  documents: DocumentRecord[],
): Record<DocumentKind, DocumentRecord[]> {
  return {
    trial_data: documents.filter((item) => item.kind === "trial_data"),
    research_document: documents.filter(
      (item) => item.kind === "research_document",
    ),
  };
}

function SourceRow({
  record,
  busy,
  onRemove,
}: {
  record: DocumentRecord;
  busy: boolean;
  onRemove: ((record: DocumentRecord, opener: HTMLElement) => void) | undefined;
}) {
  return (
    <li className="source-row">
      <div className="source-row__identity">
        <span className="source-row__name">{record.filename}</span>
        <span className="source-row__meta">
          {formatSize(record.byte_size)} · {formatUploaded(record.created_at)}
        </span>
      </div>
      <span className={`source-row__status source-row__status--${record.status}`}>
        {STATUS_LABELS[record.status]}
      </span>
      {onRemove !== undefined && (
        <button
          type="button"
          className="source-row__remove"
          aria-label={`Remove ${record.filename}`}
          disabled={busy}
          onClick={(event) => onRemove(record, event.currentTarget)}
        >
          Remove
        </button>
      )}
    </li>
  );
}

/** Uploaded sources grouped by kind, with their real processing state. */
export function SourceList({
  documents,
  busy = false,
  onRemove,
}: {
  documents: DocumentRecord[];
  busy?: boolean;
  onRemove?: (record: DocumentRecord, opener: HTMLElement) => void;
}) {
  const grouped = groupSources(documents);

  return (
    <div className="source-groups">
      {GROUPS.map(({ kind, title }) => {
        const items = grouped[kind];
        return (
          <section className="source-group" key={kind}>
            <div className="source-group__header">
              <h3>{title}</h3>
              <span className="source-group__count">
                {items.length} {items.length === 1 ? "item" : "items"}
              </span>
            </div>
            {items.length === 0 ? (
              <p className="source-group__empty">
                {kind === "trial_data"
                  ? "No trial data added."
                  : "No research documents added."}
              </p>
            ) : (
              <ul className="source-group__list" aria-label={title}>
                {items.map((record) => (
                  <SourceRow
                    key={record.id}
                    record={record}
                    busy={busy}
                    onRemove={onRemove}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
