import { useEffect, useId, useRef, useState } from "react";

import type { OrganizationRole } from "../api/types";
import { PROTOCOL_TITLE_LIMIT } from "../workspace/useProtocolLibrary";

const FOCUSABLE =
  'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const COUNTER_FROM = 160;

const ROLE_LABELS: Record<OrganizationRole, string> = {
  owner: "Owner",
  admin: "Admin",
  member: "Member",
};

const STEPS = [
  "The 14-section ICH M11 outline is prepared.",
  "Add trial JSON and research documents.",
  "Write manually or generate selected section drafts.",
] as const;

const BLANK_TITLE = "Enter a protocol title.";
const LONG_TITLE = `Protocol titles must be ${PROTOCOL_TITLE_LIMIT} characters or fewer.`;

/** Focused creation flow: a centred dialog on wide screens, a full sheet on phones. */
export function CreateProtocolDialog({
  open,
  organizationName,
  organizationRole,
  pending,
  error,
  returnFocusTo,
  onCreate,
  onClose,
}: {
  open: boolean;
  organizationName: string;
  organizationRole: OrganizationRole | null;
  pending: boolean;
  error: string | null;
  returnFocusTo?: HTMLElement | null;
  onCreate: (title: string) => void | Promise<void>;
  onClose: () => void;
}) {
  const [title, setTitle] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const wasOpen = useRef(false);
  const titleId = useId();
  const fieldId = useId();
  const helpId = useId();
  const alertId = useId();

  useEffect(() => {
    if (!open) {
      return;
    }
    setTitle("");
    setLocalError(null);
    inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending) {
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
  }, [onClose, open, pending]);

  // Focus returns to the opener only after the dialog has actually been open,
  // so a closed dialog never pulls focus while the page is first rendering.
  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      return;
    }
    if (!wasOpen.current) {
      return;
    }
    wasOpen.current = false;
    returnFocusTo?.focus();
  }, [open, returnFocusTo]);

  if (!open) {
    return null;
  }

  const message = localError ?? error;

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (pending) {
      return;
    }
    const normalized = title.trim();
    if (normalized === "") {
      setLocalError(BLANK_TITLE);
      inputRef.current?.focus();
      return;
    }
    if (normalized.length > PROTOCOL_TITLE_LIMIT) {
      setLocalError(LONG_TITLE);
      inputRef.current?.focus();
      return;
    }
    setLocalError(null);
    void onCreate(normalized);
  };

  return (
    <div className="create-protocol" role="presentation">
      <div
        className="create-protocol__panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={panelRef}
      >
        <header className="create-protocol__header">
          <div>
            <p className="create-protocol__eyebrow">New workspace</p>
            <h2 id={titleId}>Create a protocol workspace</h2>
          </div>
          <button
            type="button"
            className="create-protocol__close"
            aria-label="Close"
            onClick={onClose}
            disabled={pending}
          >
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path
                d="m5.5 5.5 9 9M14.5 5.5l-9 9"
                stroke="currentColor"
                strokeWidth="1.6"
                strokeLinecap="round"
              />
            </svg>
          </button>
        </header>

        <form className="create-protocol__body" onSubmit={submit} noValidate>
          <p className="create-protocol__description">
            Start with a title. Trial data, research documents, and the ICH M11
            section outline are added inside the workspace.
          </p>

          <div className="create-protocol__field">
            <label htmlFor={fieldId}>Protocol title</label>
            <input
              id={fieldId}
              ref={inputRef}
              value={title}
              disabled={pending}
              autoComplete="off"
              aria-describedby={
                message === null ? helpId : `${helpId} ${alertId}`
              }
              aria-invalid={message === null ? undefined : true}
              placeholder="AURORA-301 — Phase III"
              onChange={(event) => {
                setTitle(event.target.value);
                setLocalError(null);
              }}
            />
            <p className="create-protocol__help" id={helpId}>
              Use the study name, identifier, or the title your team will
              recognize.
            </p>
            {title.length >= COUNTER_FROM && (
              <p className="create-protocol__counter" aria-live="polite">
                {title.length} of {PROTOCOL_TITLE_LIMIT} characters
              </p>
            )}
          </div>

          <div className="create-protocol__organization">
            <span className="create-protocol__organization-label">
              Organization
            </span>
            <span className="create-protocol__organization-name">
              {organizationName}
            </span>
            {organizationRole !== null && (
              <span className="create-protocol__organization-role">
                {ROLE_LABELS[organizationRole]}
              </span>
            )}
          </div>

          <div className="create-protocol__steps">
            <h3>What happens next</h3>
            <ol>
              {STEPS.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
          </div>

          {message !== null && (
            <p className="create-protocol__alert" id={alertId} role="alert">
              {message}
            </p>
          )}

          <footer className="create-protocol__footer">
            <button
              type="button"
              className="create-protocol__cancel"
              onClick={onClose}
              disabled={pending}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="create-protocol__submit"
              disabled={pending}
            >
              {pending ? "Creating workspace…" : "Create workspace"}
            </button>
          </footer>
        </form>
      </div>
    </div>
  );
}
