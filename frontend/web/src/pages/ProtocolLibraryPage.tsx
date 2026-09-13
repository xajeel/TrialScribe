import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { Conversation, Organization } from "../api/types";
import {
  REVIEW_DETAILS,
  REVIEW_ORGANIZATION,
  REVIEW_PROTOCOLS,
} from "../product/libraryReviewFixtures";
import { useAuth } from "../auth/useAuth";
import { AccountMenu } from "../components/AccountMenu";
import { ErrorState, LoadingState } from "../components/AsyncState";
import { BrandLogo } from "../components/BrandLogo";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { CreateProtocolDialog } from "../components/CreateProtocolDialog";
import {
  ProtocolAttention,
  attentionItemsFor,
} from "../components/ProtocolAttention";
import { OrganizationSwitcher } from "../components/OrganizationSwitcher";
import { ProtocolTable } from "../components/ProtocolTable";
import { ProtocolToolbar } from "../components/ProtocolToolbar";
import { useOrganization } from "../org/useOrganization";
import { useProtocolLibrary } from "../workspace/useProtocolLibrary";
import { OrganizationSetupPage } from "./OrganizationSetupPage";

const STEPS = [
  "Create workspace",
  "Add sources",
  "Draft sections",
] as const;

interface PendingMove {
  protocol: Conversation;
  kind: "archive" | "restore";
  opener: HTMLElement | null;
}

/** Authenticated home: the organization's protocol workspaces and their creation flow. */
export function ProtocolLibraryPage({
  review,
}: {
  review?: "populated" | "empty" | "create";
} = {}) {
  const { authorizedFetch } = useAuth();
  const org = useOrganization();
  const navigate = useNavigate();

  const reviewing = review !== undefined;
  const ready = reviewing || org.status === "ready";
  const memberOfOrg = reviewing || (ready && org.organizations.length > 0);
  const liveActive =
    !reviewing && org.status === "ready"
      ? (org.organizations.find((item) => item.id === org.activeId) ?? null)
      : null;
  const active: Organization | null = reviewing
    ? REVIEW_ORGANIZATION
    : liveActive;
  const library = useProtocolLibrary(
    reviewing ? null : (liveActive?.id ?? null),
    authorizedFetch,
  );

  const [createOpen, setCreateOpen] = useState(review === "create");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [pendingMove, setPendingMove] = useState<PendingMove | null>(null);
  const createTriggerRef = useRef<HTMLButtonElement | null>(null);

  // The review route renders sample protocols so the layout can be inspected
  // without a session; every live path keeps using the controller as loaded.
  const sample = useMemo(() => {
    if (review === undefined) {
      return null;
    }
    const source =
      review === "empty" || library.scope === "archived"
        ? []
        : REVIEW_PROTOCOLS;
    const term = library.search.trim().toLowerCase();
    const matched = source.filter((item) =>
      term === "" ? true : item.title.toLowerCase().includes(term),
    );
    const visible = [...matched].sort((left, right) =>
      library.sort === "title"
        ? left.title.localeCompare(right.title)
        : right.last_activity_at.localeCompare(left.last_activity_at),
    );
    return { protocols: source, visible, details: REVIEW_DETAILS };
  }, [library.scope, library.search, library.sort, review]);

  const status = sample === null ? library.status : "ready";
  const protocols = sample === null ? library.protocols : sample.protocols;
  const visible = sample === null ? library.visible : sample.visible;
  const details = sample === null ? library.details : sample.details;

  if (ready && !memberOfOrg) {
    return <OrganizationSetupPage />;
  }

  const attention = attentionItemsFor(protocols, details);
  const searching = library.search.trim() !== "";
  const noProtocols = status === "ready" && protocols.length === 0;
  // Only a genuinely empty library takes over the page. An empty Archived tab
  // keeps the toolbar so the filter that produced it stays one click away.
  const showEmpty = noProtocols && library.scope === "active";
  const showScopeEmpty = noProtocols && library.scope === "archived";
  const showNoMatches =
    status === "ready" && protocols.length > 0 && visible.length === 0;

  const openCreate = () => {
    library.dismissFeedback();
    setCreateOpen(true);
  };

  const submitCreate = async (title: string) => {
    const created = await library.create(title);
    if (created !== null) {
      setCreateOpen(false);
      navigate(`/workspace/${created.id}`);
    }
  };

  const confirmMove = async () => {
    if (pendingMove === null) {
      return;
    }
    const { protocol, kind } = pendingMove;
    const done =
      kind === "archive"
        ? await library.archive(protocol.id)
        : await library.restore(protocol.id);
    if (done) {
      setPendingMove(null);
    }
  };

  return (
    <div className="protocol-library">
      <a className="protocol-library__skip" href="#protocol-library-main">
        Skip to main content
      </a>

      <header className="protocol-library__header">
        <div className="protocol-library__header-inner">
          <BrandLogo
            className="protocol-library__brand"
            to="/protocols"
            ariaLabel="TrialScribe protocols"
          />
          <div className="protocol-library__header-actions">
            <OrganizationSwitcher
              organizations={active === null ? org.organizations : [active]}
              activeId={active?.id ?? org.activeId}
              onSelect={org.select}
            />
            {reviewing ? (
              <span className="avatar" aria-label="Review account MC">
                MC
              </span>
            ) : (
              <AccountMenu />
            )}
          </div>
        </div>
      </header>

      <main id="protocol-library-main" className="protocol-library__main">
        <div className="protocol-library__page-header">
          <div>
            <p className="protocol-library__eyebrow">{active?.name ?? ""}</p>
            <h1>Protocol workspaces</h1>
            <p className="protocol-library__lede">
              Resume authoring, review section status, or start a new ICH M11
              protocol.
            </p>
          </div>
          <button
            type="button"
            className="protocol-library__primary"
            ref={createTriggerRef}
            onClick={openCreate}
          >
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path
                d="M10 4.5v11M4.5 10h11"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinecap="round"
              />
            </svg>
            New protocol
          </button>
        </div>

        {!reviewing && org.status !== "ready" && (
          <section className="protocol-library__state" aria-label="Organizations">
            {org.status === "error" ? (
              <ErrorState
                message="Could not load your organizations."
                onRetry={org.reload}
              />
            ) : (
              <LoadingState label="Loading your organizations…" />
            )}
          </section>
        )}

        {library.feedback !== null && (
          <p
            className={
              library.feedback.kind === "error"
                ? "protocol-library__feedback protocol-library__feedback--error"
                : "protocol-library__feedback"
            }
            role={library.feedback.kind === "error" ? "alert" : "status"}
          >
            {library.feedback.message}
          </p>
        )}

        {active !== null && status === "error" && (
          <section className="protocol-library__state" aria-label="Protocols">
            <ErrorState
              message="Could not load protocol workspaces."
              onRetry={library.retry}
            />
          </section>
        )}

        {active !== null && status !== "error" && (
          <>
            <ProtocolAttention items={attention} />

            {!showEmpty && (
              <ProtocolToolbar
                search={library.search}
                scope={library.scope}
                sort={library.sort}
                onSearch={library.setSearch}
                onScope={library.setScope}
                onSort={library.setSort}
              />
            )}

            {showEmpty ? (
              <section
                className="protocol-library__empty"
                aria-labelledby="protocol-empty-title"
              >
                <h2 id="protocol-empty-title">
                  Create your first protocol workspace
                </h2>
                <p>
                  Give the protocol a title, add trial data and research
                  sources, then begin the ICH M11 outline.
                </p>
                <button
                  type="button"
                  className="protocol-library__primary"
                  onClick={openCreate}
                >
                  Create protocol
                </button>
                <ol className="protocol-library__steps">
                  {STEPS.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
              </section>
            ) : showScopeEmpty ? (
              <section
                className="protocol-library__scope-empty"
                aria-labelledby="protocol-scope-empty-title"
              >
                <h2 id="protocol-scope-empty-title">
                  No archived protocol workspaces
                </h2>
                <p>
                  Archived protocols stay readable and can be restored at any
                  time.
                </p>
              </section>
            ) : (
              <>
                <ProtocolTable
                  protocols={visible}
                  details={details}
                  scope={library.scope}
                  loading={status === "loading"}
                  renamingId={renamingId}
                  renamePending={library.action === "renaming"}
                  onRenameStart={setRenamingId}
                  onRenameSubmit={(conversationId, title) => {
                    void library.rename(conversationId, title).then((done) => {
                      if (done) {
                        setRenamingId(null);
                      }
                    });
                  }}
                  onRenameCancel={() => setRenamingId(null)}
                  onArchive={(protocol, opener) =>
                    setPendingMove({ protocol, kind: "archive", opener })
                  }
                  onRestore={(protocol, opener) =>
                    setPendingMove({ protocol, kind: "restore", opener })
                  }
                />

                {showNoMatches && (
                  <p className="protocol-library__no-matches" role="status">
                    {searching
                      ? "No protocols match your search."
                      : "No protocol workspaces to show."}
                  </p>
                )}

                {library.nextCursor !== null && (
                  <button
                    type="button"
                    className="protocol-library__load-more"
                    onClick={library.loadMore}
                    disabled={library.loadingMore}
                  >
                    {library.loadingMore
                      ? "Loading protocols…"
                      : "Load more protocols"}
                  </button>
                )}
              </>
            )}
          </>
        )}
      </main>

      <CreateProtocolDialog
        open={createOpen}
        organizationName={active?.name ?? ""}
        organizationRole={active?.role ?? null}
        pending={library.action === "creating"}
        error={
          library.feedback?.kind === "error" ? library.feedback.message : null
        }
        returnFocusTo={createTriggerRef.current}
        onCreate={submitCreate}
        onClose={() => {
          setCreateOpen(false);
          library.dismissFeedback();
        }}
      />

      <ConfirmDialog
        open={pendingMove !== null}
        title={
          pendingMove?.kind === "restore"
            ? `Restore ${pendingMove.protocol.title}?`
            : `Archive ${pendingMove?.protocol.title ?? ""}?`
        }
        description={
          pendingMove?.kind === "restore"
            ? "The protocol returns to the active library and authoring actions are enabled again."
            : "Existing content stays readable, but authoring actions are disabled."
        }
        confirmLabel={
          pendingMove?.kind === "restore" ? "Restore protocol" : "Archive protocol"
        }
        destructive={pendingMove?.kind !== "restore"}
        pending={
          library.action === "archiving" || library.action === "restoring"
        }
        returnFocusTo={pendingMove?.opener ?? null}
        onConfirm={() => void confirmMove()}
        onCancel={() => setPendingMove(null)}
      />
    </div>
  );
}
