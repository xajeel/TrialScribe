import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { Conversation } from "../api/types";
import type {
  LibraryScope,
  ProtocolDetail,
} from "../workspace/useProtocolLibrary";

const SECTION_TOTAL = 14;

/** Absolute date plus a short relative phrase, both from the same timestamp. */
export function formatActivity(timestamp: string, now = new Date()): string {
  const value = new Date(timestamp);
  if (Number.isNaN(value.getTime())) {
    return "Unknown";
  }
  const absolute = value.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const minutes = Math.floor((now.getTime() - value.getTime()) / 60000);
  if (minutes < 1) {
    return `${absolute} · just now`;
  }
  if (minutes < 60) {
    return `${absolute} · ${minutes} min ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${absolute} · ${hours} h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days === 1) {
    return `${absolute} · yesterday`;
  }
  return `${absolute} · ${days} days ago`;
}

function ProgressRule({ done, total }: { done: number; total: number }) {
  const segments = Math.max(total, 1);
  return (
    <span className="protocol-progress" aria-hidden="true">
      {Array.from({ length: segments }, (_, index) => (
        <span
          key={index}
          className={
            index < done
              ? "protocol-progress__segment protocol-progress__segment--done"
              : "protocol-progress__segment"
          }
        />
      ))}
    </span>
  );
}

function StatusLabel({ scope }: { scope: LibraryScope }) {
  return (
    <span
      className={
        scope === "archived"
          ? "protocol-status protocol-status--archived"
          : "protocol-status protocol-status--active"
      }
    >
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        {scope === "archived" ? (
          <path
            d="M2.5 4.5h11v2h-11zM3.5 6.5h9v7h-9zM6.5 9h3"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : (
          <>
            <circle cx="8" cy="8" r="5.4" stroke="currentColor" strokeWidth="1.4" />
            <path
              d="M8 5.2V8l1.9 1.4"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
            />
          </>
        )}
      </svg>
      {scope === "archived" ? "Archived" : "Active"}
    </span>
  );
}

function RowMenu({
  protocol,
  scope,
  onRename,
  onArchive,
  onRestore,
}: {
  protocol: Conversation;
  scope: LibraryScope;
  onRename: () => void;
  onArchive: (opener: HTMLElement) => void;
  onRestore: (opener: HTMLElement) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (
        rootRef.current !== null &&
        !rootRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="protocol-row-menu" ref={rootRef}>
      <button
        type="button"
        className="protocol-row-menu__trigger"
        aria-label={`Actions for ${protocol.title}`}
        aria-haspopup="true"
        aria-expanded={open}
        ref={triggerRef}
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <circle cx="10" cy="4.2" r="1.5" />
          <circle cx="10" cy="10" r="1.5" />
          <circle cx="10" cy="15.8" r="1.5" />
        </svg>
      </button>
      {open && (
        <div className="protocol-row-menu__popover">
          <Link
            className="protocol-row-menu__item"
            to={`/workspace/${protocol.id}`}
            onClick={() => setOpen(false)}
          >
            Open workspace
          </Link>
          <Link
            className="protocol-row-menu__item"
            to={`/workspace/${protocol.id}/instructions`}
            onClick={() => setOpen(false)}
          >
            Writing instructions
          </Link>
          <button
            type="button"
            className="protocol-row-menu__item"
            onClick={() => {
              setOpen(false);
              onRename();
            }}
          >
            Rename
          </button>
          {scope === "archived" ? (
            <button
              type="button"
              className="protocol-row-menu__item"
              onClick={(event) => {
                setOpen(false);
                onRestore(event.currentTarget);
              }}
            >
              Restore
            </button>
          ) : (
            <button
              type="button"
              className="protocol-row-menu__item protocol-row-menu__item--danger"
              onClick={(event) => {
                setOpen(false);
                onArchive(event.currentTarget);
              }}
            >
              Archive
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function RenameForm({
  protocol,
  pending,
  onSubmit,
  onCancel,
}: {
  protocol: Conversation;
  pending: boolean;
  onSubmit: (title: string) => void;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(protocol.title);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  return (
    <form
      className="protocol-rename"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(title);
      }}
    >
      <label htmlFor={`rename-${protocol.id}`}>Protocol title</label>
      <input
        id={`rename-${protocol.id}`}
        value={title}
        maxLength={200}
        disabled={pending}
        ref={inputRef}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
      />
      <div className="protocol-rename__actions">
        <button type="submit" disabled={pending}>
          {pending ? "Saving…" : "Save title"}
        </button>
        <button type="button" onClick={onCancel} disabled={pending}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 3 }, (_, index) => (
        <tr className="protocol-table__row protocol-table__row--skeleton" key={index} role="row">
          <td role="cell" colSpan={6}>
            <span className="protocol-skeleton" />
          </td>
        </tr>
      ))}
    </>
  );
}

/** Protocol rows: a dense table on wide screens, stacked cards on narrow ones. */
export function ProtocolTable({
  protocols,
  details,
  scope,
  loading,
  renamingId,
  renamePending,
  onRenameStart,
  onRenameSubmit,
  onRenameCancel,
  onArchive,
  onRestore,
}: {
  protocols: Conversation[];
  details: Record<string, ProtocolDetail>;
  scope: LibraryScope;
  loading: boolean;
  renamingId: string | null;
  renamePending: boolean;
  onRenameStart: (conversationId: string) => void;
  onRenameSubmit: (conversationId: string, title: string) => void;
  onRenameCancel: () => void;
  onArchive: (protocol: Conversation, opener: HTMLElement) => void;
  onRestore: (protocol: Conversation, opener: HTMLElement) => void;
}) {
  return (
    <div className="protocol-table">
      <table role="table">
        <caption className="visually-hidden">
          {scope === "archived"
            ? "Archived protocol workspaces"
            : "Active protocol workspaces"}
        </caption>
        <thead role="rowgroup">
          <tr role="row">
            <th role="columnheader" scope="col">
              Protocol
            </th>
            <th role="columnheader" scope="col">
              Status
            </th>
            <th role="columnheader" scope="col">
              Sections
            </th>
            <th role="columnheader" scope="col">
              Sources
            </th>
            <th role="columnheader" scope="col">
              Last activity
            </th>
            <th role="columnheader" scope="col">
              <span className="visually-hidden">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {loading && <SkeletonRows />}
          {!loading &&
            protocols.map((protocol) => {
              const detail = details[protocol.id];
              const done = detail?.sections?.done ?? null;
              const total = detail?.sections?.total ?? SECTION_TOTAL;
              const sources = detail?.sources ?? null;
              return (
                <tr className="protocol-table__row" key={protocol.id} role="row">
                  <td role="cell" data-label="Protocol">
                    {renamingId === protocol.id ? (
                      <RenameForm
                        protocol={protocol}
                        pending={renamePending}
                        onSubmit={(title) => onRenameSubmit(protocol.id, title)}
                        onCancel={onRenameCancel}
                      />
                    ) : (
                      <>
                        <Link
                          className="protocol-table__title"
                          to={`/workspace/${protocol.id}`}
                        >
                          {protocol.title}
                        </Link>
                        {(detail?.failed ?? 0) > 0 && (
                          <span className="protocol-table__attention">
                            Source processing failed
                          </span>
                        )}
                      </>
                    )}
                  </td>
                  <td role="cell" data-label="Status">
                    <StatusLabel scope={scope} />
                  </td>
                  <td role="cell" data-label="Sections">
                    {done === null ? (
                      <span className="protocol-table__pending">Loading…</span>
                    ) : (
                      <span className="protocol-table__sections">
                        <span className="protocol-table__count">
                          {done} of {total} complete
                        </span>
                        <ProgressRule done={done} total={total} />
                      </span>
                    )}
                  </td>
                  <td role="cell" data-label="Sources">
                    {sources === null ? (
                      <span className="protocol-table__pending">Loading…</span>
                    ) : sources === 0 ? (
                      <span className="protocol-table__muted">No sources</span>
                    ) : (
                      <span className="protocol-table__count">
                        {sources} {sources === 1 ? "source" : "sources"}
                      </span>
                    )}
                  </td>
                  <td role="cell" data-label="Last activity">
                    <span className="protocol-table__count">
                      {formatActivity(protocol.last_activity_at)}
                    </span>
                  </td>
                  <td role="cell" className="protocol-table__actions">
                    <RowMenu
                      protocol={protocol}
                      scope={scope}
                      onRename={() => onRenameStart(protocol.id)}
                      onArchive={(opener) => onArchive(protocol, opener)}
                      onRestore={(opener) => onRestore(protocol, opener)}
                    />
                  </td>
                </tr>
              );
            })}
        </tbody>
      </table>
    </div>
  );
}
