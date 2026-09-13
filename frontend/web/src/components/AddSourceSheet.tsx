import { useEffect, useId, useRef, useState, type DragEvent } from "react";

import type { DocumentKind } from "../api/types";
import { formatSize } from "./SourceList";

const FOCUSABLE =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Mirrors DEFAULT_DOCUMENT_MAX_SIZE_BYTES in the ingestion service. */
export const MAX_SOURCE_BYTES = 10_485_760;

const KINDS: { kind: DocumentKind; label: string }[] = [
  { kind: "trial_data", label: "Trial data" },
  { kind: "research_document", label: "Research document" },
];

const ACCEPT: Record<DocumentKind, string> = {
  trial_data: ".json,application/json",
  research_document:
    ".pdf,.txt,.md,application/pdf,text/plain,text/markdown",
};

const LIMITS: Record<DocumentKind, string> = {
  trial_data: "Trial data must be a JSON object. Maximum 10 MB.",
  research_document: "Supported formats: PDF, TXT, MD. Maximum 10 MB.",
};

/**
 * Client-side gate matching the ingestion service, so an oversized or
 * wrong-typed file is refused before a request is spent on it.
 */
export function validateSource(kind: DocumentKind, file: File): string | null {
  if (file.size === 0) {
    return "That file is empty. Choose a file with content.";
  }
  if (file.size > MAX_SOURCE_BYTES) {
    return `That file is ${formatSize(file.size)}. The maximum is 10 MB.`;
  }
  const name = file.name.toLowerCase();
  const allowed =
    kind === "trial_data"
      ? [".json"]
      : [".pdf", ".txt", ".md"];
  if (!allowed.some((suffix) => name.endsWith(suffix))) {
    return kind === "trial_data"
      ? "Trial data must be a .json file."
      : "Research documents must be a .pdf, .txt, or .md file.";
  }
  return null;
}

/** Add one trial-data or research source, stating the real upload limits. */
export function AddSourceSheet({
  open,
  pending,
  returnFocusTo,
  onUpload,
  onClose,
}: {
  open: boolean;
  pending: boolean;
  returnFocusTo?: HTMLElement | null;
  onUpload: (kind: DocumentKind, file: File) => Promise<boolean>;
  onClose: () => void;
}) {
  const [kind, setKind] = useState<DocumentKind>("research_document");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const wasOpen = useRef(false);
  const titleId = useId();
  const errorId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab" || panelRef.current === null) {
        return;
      }
      const targets = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      );
      if (targets.length === 0) {
        return;
      }
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      return;
    }
    if (!wasOpen.current) {
      return;
    }
    wasOpen.current = false;
    setFile(null);
    setError(null);
    setDragging(false);
    returnFocusTo?.focus();
  }, [open, returnFocusTo]);

  if (!open) {
    return null;
  }

  const accept = (candidate: File) => {
    const rejection = validateSource(kind, candidate);
    if (rejection !== null) {
      setFile(null);
      setError(rejection);
      return;
    }
    setFile(candidate);
    setError(null);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped !== undefined) {
      accept(dropped);
    }
  };

  const submit = async () => {
    if (file === null) {
      setError("Choose a file to upload.");
      return;
    }
    if (await onUpload(kind, file)) {
      onClose();
    }
  };

  return (
    <div className="source-sheet" role="presentation">
      <div
        className="source-sheet__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={panelRef}
      >
        <div className="source-sheet__header">
          <div>
            <h2 id={titleId}>Add source</h2>
            <p>Incorporate new evidence into this protocol.</p>
          </div>
          <button
            type="button"
            className="source-sheet__close"
            onClick={onClose}
            ref={closeRef}
          >
            Close
          </button>
        </div>

        <div className="source-sheet__body">
          <fieldset className="source-sheet__kinds">
            <legend>Source kind</legend>
            {KINDS.map((option) => (
              <label className="source-sheet__kind" key={option.kind}>
                <input
                  type="radio"
                  name="source-kind"
                  value={option.kind}
                  checked={kind === option.kind}
                  onChange={() => {
                    setKind(option.kind);
                    setFile(null);
                    setError(null);
                    if (fileInputRef.current !== null) {
                      fileInputRef.current.value = "";
                    }
                  }}
                  disabled={pending}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </fieldset>

          <div
            className={
              dragging
                ? "source-sheet__drop source-sheet__drop--active"
                : "source-sheet__drop"
            }
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <p className="source-sheet__drop-title">Drop a document here</p>
            <label className="source-sheet__choose" htmlFor="source-file">
              Choose file
            </label>
            <input
              id="source-file"
              ref={fileInputRef}
              type="file"
              accept={ACCEPT[kind]}
              disabled={pending}
              onChange={(event) => {
                const chosen = event.target.files?.[0];
                if (chosen !== undefined) {
                  accept(chosen);
                }
              }}
            />
            <p className="source-sheet__limits">{LIMITS[kind]}</p>
          </div>

          {file !== null && (
            <div className="source-sheet__queue">
              <h3>File in queue</h3>
              <div className="source-sheet__queued">
                <div>
                  <span className="source-sheet__queued-name">{file.name}</span>
                  <span className="source-sheet__queued-meta">
                    {formatSize(file.size)}
                  </span>
                </div>
                <button
                  type="button"
                  className="source-sheet__discard"
                  disabled={pending}
                  onClick={() => {
                    setFile(null);
                    if (fileInputRef.current !== null) {
                      fileInputRef.current.value = "";
                    }
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          )}

          {error !== null && (
            <p className="source-sheet__error" id={errorId} role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="source-sheet__actions">
          <button
            type="button"
            className="source-sheet__cancel"
            onClick={onClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="button"
            className="source-sheet__submit"
            onClick={() => void submit()}
            disabled={pending || file === null}
          >
            {pending ? "Uploading…" : "Upload source"}
          </button>
        </div>
      </div>
    </div>
  );
}
