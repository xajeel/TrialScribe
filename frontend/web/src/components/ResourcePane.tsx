import { useState } from "react";
import { Link } from "react-router-dom";

import type { M11Section } from "../api/types";
import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import { ErrorState, LoadingState } from "./AsyncState";
import { formatSize } from "./SourceList";

type InspectorTab = "outline" | "sources";

const TABS: { key: InspectorTab; label: string }[] = [
  { key: "outline", label: "Outline" },
  { key: "sources", label: "Sources" },
];

const STATUS_LABELS = {
  ready: "Ready",
  pending: "Processing",
  failed: "Failed",
} as const;

/** Right inspector: the ICH M11 outline and the sources backing this protocol. */
export function ResourcePane({
  workspace,
  onOpenSection,
}: {
  workspace: AuthoringWorkspaceController;
  onOpenSection: (section: M11Section, opener: HTMLElement) => void;
}) {
  const [tab, setTab] = useState<InspectorTab>("outline");
  const conversationId = workspace.selectedConversationId;
  const total = workspace.sections.length;
  const complete = workspace.sections.filter(
    (item) => item.status === "done",
  ).length;
  const loading =
    workspace.selectedConversation !== null &&
    workspace.workspaceStatus === "loading";
  const failed =
    workspace.selectedConversation !== null &&
    workspace.workspaceStatus === "error";

  return (
    <aside className="workbench-inspector" aria-labelledby="resources-title">
      <h2 className="visually-hidden" id="resources-title">
        Sources and sections
      </h2>

      <div className="workbench-inspector__tabs" role="tablist">
        {TABS.map((option) => (
          <button
            key={option.key}
            type="button"
            role="tab"
            aria-selected={tab === option.key}
            className={
              tab === option.key
                ? "workbench-inspector__tab workbench-inspector__tab--current"
                : "workbench-inspector__tab"
            }
            onClick={() => setTab(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="workbench-inspector__body">
        {loading && <LoadingState label="Loading…" />}
        {failed && (
          <ErrorState
            message="Could not load this workspace."
            onRetry={workspace.retryWorkspace}
          />
        )}

        {tab === "outline" && !loading && !failed && (
          <>
            <p className="workbench-inspector__label">ICH M11 framework</p>
            {total === 0 ? (
              <p className="workbench-inspector__empty">
                This protocol&apos;s 14-section outline has not been prepared
                yet.
              </p>
            ) : (
              <ol className="workbench-outline">
                {workspace.sections.map((section) => {
                  const selected =
                    section.section_number === workspace.selectedSectionNumber;
                  const sectionDone = section.status === "done";
                  const started = section.content.trim() !== "";
                  return (
                    <li
                      key={section.id}
                      className={
                        selected
                          ? "workbench-outline__item workbench-outline__item--current"
                          : "workbench-outline__item"
                      }
                    >
                      <button
                        type="button"
                        className="workbench-outline__select"
                        aria-current={selected ? "true" : undefined}
                        onClick={() =>
                          workspace.selectSection(section.section_number)
                        }
                      >
                        <span className="workbench-outline__number">
                          {section.section_number}
                        </span>
                        <span className="workbench-outline__title">
                          {section.title}
                        </span>
                        <span
                          className={`workbench-outline__state workbench-outline__state--${
                            sectionDone ? "done" : started ? "draft" : "empty"
                          }`}
                        >
                          {sectionDone ? "✓" : started ? "Draft" : "—"}
                        </span>
                      </button>
                      <button
                        type="button"
                        className="workbench-outline__read"
                        aria-label={`Read ${section.title}`}
                        onClick={(event) =>
                          onOpenSection(section, event.currentTarget)
                        }
                      >
                        Read
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </>
        )}

        {tab === "sources" && !loading && !failed && (
          <>
            <div className="workbench-inspector__label-row">
              <p className="workbench-inspector__label">Trial data</p>
              {conversationId !== null && (
                <Link
                  className="workbench-inspector__link"
                  to={`/workspace/${encodeURIComponent(conversationId)}/sources`}
                >
                  Manage
                </Link>
              )}
            </div>
            <SourceGroup
              documents={workspace.documents.filter(
                (item) => item.kind === "trial_data",
              )}
              emptyLabel="No trial data added."
            />
            <p className="workbench-inspector__label">Research documents</p>
            <SourceGroup
              documents={workspace.documents.filter(
                (item) => item.kind === "research_document",
              )}
              emptyLabel="No research documents added."
            />
          </>
        )}
      </div>

      <footer className="workbench-inspector__foot">
        <span>Sections complete</span>
        <strong>
          {complete} of {total}
        </strong>
      </footer>
    </aside>
  );
}

function SourceGroup({
  documents,
  emptyLabel,
}: {
  documents: AuthoringWorkspaceController["documents"];
  emptyLabel: string;
}) {
  if (documents.length === 0) {
    return <p className="workbench-inspector__empty">{emptyLabel}</p>;
  }
  return (
    <ul className="workbench-sources">
      {documents.map((record) => (
        <li key={record.id}>
          <span className="workbench-sources__name">{record.filename}</span>
          <span className="workbench-sources__meta">
            {formatSize(record.byte_size)}
          </span>
          <span
            className={`workbench-sources__status workbench-sources__status--${record.status}`}
          >
            {STATUS_LABELS[record.status]}
          </span>
        </li>
      ))}
    </ul>
  );
}
