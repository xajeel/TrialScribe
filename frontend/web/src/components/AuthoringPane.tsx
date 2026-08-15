import { useEffect, useState, type FormEvent, type SyntheticEvent } from "react";

import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import { EmptyState, ErrorState, LoadingState } from "./AsyncState";

type CentreView = "document" | "instructions";

const VIEWS: { key: CentreView; label: string }[] = [
  { key: "document", label: "Document" },
  { key: "instructions", label: "Instructions" },
];

function relativeTime(isoDate: string): string {
  const parsed = new Date(isoDate);
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const minutes = Math.round((Date.now() - parsed.getTime()) / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  return `${Math.round(hours / 24)}d ago`;
}

/**
 * The centre of the workbench: one M11 section presented as a document on
 * paper. The prose itself is the editor, so the surface a reader sees and the
 * surface an author types into are the same thing.
 */
export function AuthoringPane({
  workspace,
  onRewrite,
  rewriteBusy = false,
}: {
  workspace: AuthoringWorkspaceController;
  onRewrite?: (selection: { start: number; end: number } | null) => void;
  rewriteBusy?: boolean;
}) {
  const [view, setView] = useState<CentreView>("document");
  const [instruction, setInstruction] = useState("");
  const [sectionInstructions, setSectionInstructions] = useState("");
  const [sectionContent, setSectionContent] = useState("");
  const [selection, setSelection] = useState({ start: 0, end: 0 });
  const section = workspace.selectedSection;

  useEffect(() => {
    setSectionInstructions(section?.instructions ?? "");
    setSectionContent(section?.content ?? "");
    setSelection({ start: 0, end: 0 });
  }, [
    section?.current_revision,
    section?.id,
    section?.instructions,
    section?.content,
  ]);

  const submitInstruction = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = instruction.trim();
    if (content === "") {
      return;
    }
    if (await workspace.appendInstruction(content)) {
      setInstruction("");
    }
  };

  const sectionChanged =
    section !== null &&
    (sectionInstructions !== section.instructions ||
      sectionContent !== section.content);
  const busy = workspace.action !== "idle" || rewriteBusy;
  const done = section?.status === "done";
  const total = workspace.sections.length;
  const complete = workspace.sections.filter(
    (item) => item.status === "done",
  ).length;
  const percent = total === 0 ? 0 : Math.round((complete / total) * 100);

  if (
    workspace.conversationStatus === "ready" &&
    workspace.conversations.length === 0
  ) {
    return (
      <section className="workbench-centre" aria-label="Section editor">
        <div className="workbench-centre__state">
          <EmptyState
            title="Create a protocol"
            description="Your durable instructions, sources, and M11 sections will appear here."
          />
        </div>
      </section>
    );
  }

  if (workspace.selectedConversation === null) {
    return <section className="workbench-centre" aria-label="Section editor" />;
  }

  if (workspace.workspaceStatus === "loading") {
    return (
      <section className="workbench-centre" aria-label="Section editor">
        <div className="workbench-centre__state">
          <LoadingState label="Loading this authoring workspace…" />
        </div>
      </section>
    );
  }

  if (workspace.workspaceStatus === "error") {
    return (
      <section className="workbench-centre" aria-label="Section editor">
        <div className="workbench-centre__state">
          <ErrorState
            message="Could not load this authoring workspace."
            onRetry={workspace.retryWorkspace}
          />
        </div>
      </section>
    );
  }

  return (
    <section className="workbench-centre" aria-label="Section editor">
      <header className="workbench-centre__head">
        <div className="workbench-centre__head-row">
          <div className="workbench-centre__title">
            <h1>
              {section === null
                ? "No section selected"
                : `${section.section_number} · ${section.title}`}
            </h1>
            {section !== null && (
              <span
                className={
                  done
                    ? "workbench-badge workbench-badge--done"
                    : "workbench-badge"
                }
              >
                {done ? "Done" : "Draft"}
              </span>
            )}
          </div>
          <nav className="workbench-segmented" aria-label="Centre pane view">
            {VIEWS.map((option) => (
              <button
                key={option.key}
                type="button"
                aria-pressed={view === option.key}
                className={
                  view === option.key
                    ? "workbench-segmented__item workbench-segmented__item--current"
                    : "workbench-segmented__item"
                }
                onClick={() => setView(option.key)}
              >
                {option.label}
              </button>
            ))}
          </nav>
        </div>
        <p className="workbench-centre__meta">
          <span>
            {complete} of {total} sections complete
          </span>
          {section !== null && (
            <span>Last edited {relativeTime(section.updated_at)}</span>
          )}
        </p>
        <div
          className="workbench-rule"
          role="img"
          aria-label={`${percent}% of sections complete`}
        >
          <span style={{ width: `${percent}%` }} />
        </div>
      </header>

      {workspace.feedback !== null && (
        <div
          className={`workbench-feedback workbench-feedback--${workspace.feedback.kind}`}
          role={workspace.feedback.kind === "error" ? "alert" : "status"}
        >
          <span>{workspace.feedback.message}</span>
          <button
            type="button"
            onClick={workspace.dismissFeedback}
            aria-label="Dismiss message"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="workbench-centre__canvas">
        <article className="workbench-paper">
          {view === "document" && section !== null && (
            <>
              <div className="workbench-paper__meta">
                <div>
                  <p className="workbench-paper__label">Schema</p>
                  <p className="workbench-paper__schema">
                    ICH M11 Clinical Electronic Structured Harmonised Protocol
                  </p>
                </div>
                <div className="workbench-paper__meta-right">
                  <p>
                    Section {section.section_number} of {total}
                  </p>
                  <span className="workbench-chip">
                    Revision {section.current_revision}
                  </span>
                </div>
              </div>

              {/* Repeats the sticky header's h1 as the document's own title,
                  so it is presentational rather than a second heading. */}
              <p className="workbench-paper__title" aria-hidden="true">
                {section.section_number} · {section.title}
              </p>

              <label
                className="workbench-paper__field-label"
                htmlFor="section-instructions"
              >
                Section instructions
              </label>
              <textarea
                id="section-instructions"
                className="workbench-paper__note"
                value={sectionInstructions}
                onChange={(event) => setSectionInstructions(event.target.value)}
                rows={2}
                disabled={busy || done}
                placeholder="Add section-specific writing guidance…"
              />

              <label
                className="workbench-paper__field-label"
                htmlFor="section-content"
              >
                Section content
              </label>
              <textarea
                id="section-content"
                className="workbench-paper__prose"
                value={sectionContent}
                onChange={(event) => setSectionContent(event.target.value)}
                onSelect={(event: SyntheticEvent<HTMLTextAreaElement>) => {
                  if (document.activeElement !== event.currentTarget) {
                    return;
                  }
                  setSelection({
                    start: event.currentTarget.selectionStart,
                    end: event.currentTarget.selectionEnd,
                  });
                }}
                rows={16}
                disabled={busy || done}
                placeholder="Draft the complete section here…"
              />

              <p className="workbench-paper__end">
                End of section {section.section_number}
              </p>
            </>
          )}

          {view === "document" && section === null && (
            <EmptyState
              title="No M11 sections"
              description="This protocol's 14-section outline has not been prepared yet."
            />
          )}

          {view === "instructions" && (
            <>
              <div className="workbench-paper__meta">
                <div>
                  <p className="workbench-paper__label">Workspace context</p>
                  <p className="workbench-paper__schema">
                    Instructions apply to every section in this protocol
                  </p>
                </div>
              </div>

              {workspace.messages.length === 0 ? (
                <EmptyState
                  title="No instructions yet"
                  description="Add context or a writing request for this protocol."
                />
              ) : (
                <ol className="workbench-instructions">
                  {workspace.messages.map((message) => (
                    <li key={message.id}>
                      <span className="workbench-instructions__author">
                        {message.role === "user" ? "You" : "TrialScribe"}
                      </span>
                      <p>{message.content}</p>
                    </li>
                  ))}
                </ol>
              )}

              <form
                className="workbench-composer"
                onSubmit={submitInstruction}
              >
                <label htmlFor="conversation-instruction">
                  Add an instruction
                </label>
                <textarea
                  id="conversation-instruction"
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  placeholder="Describe what this protocol needs…"
                  rows={3}
                  disabled={busy}
                  required
                />
                <button
                  type="submit"
                  className="workbench-button workbench-button--primary"
                  disabled={instruction.trim() === "" || busy}
                >
                  {workspace.action === "sending"
                    ? "Saving instruction…"
                    : "Save instruction"}
                </button>
              </form>
            </>
          )}
        </article>
      </div>

      {view === "document" && section !== null && (
        <footer className="workbench-actionbar">
          <p className="workbench-actionbar__hint" role="status">
            {sectionChanged
              ? "Unsaved changes"
              : done
                ? "Marked done"
                : "All changes saved"}
          </p>
          <div className="workbench-actionbar__actions">
            {!done && (
              <>
                <button
                  type="button"
                  className="workbench-button workbench-button--quiet"
                  disabled={!sectionChanged || busy}
                  onClick={() => {
                    setSectionInstructions(section.instructions);
                    setSectionContent(section.content);
                  }}
                >
                  Discard draft
                </button>
                <button
                  type="button"
                  className="workbench-button"
                  disabled={!sectionChanged || busy}
                  onClick={() =>
                    void workspace.saveSection(
                      sectionInstructions,
                      sectionContent,
                    )
                  }
                >
                  {workspace.action === "saving" ? "Saving…" : "Save section"}
                </button>
                {onRewrite !== undefined && (
                  <button
                    type="button"
                    className="workbench-button"
                    aria-label="Rewrite section"
                    disabled={sectionChanged || busy}
                    title={
                      sectionChanged
                        ? "Save changes before rewriting"
                        : undefined
                    }
                    onClick={() =>
                      onRewrite(
                        selection.end > selection.start ? selection : null,
                      )
                    }
                  >
                    Rewrite
                  </button>
                )}
                <button
                  type="button"
                  className="workbench-button workbench-button--primary"
                  disabled={sectionChanged || busy}
                  title={
                    sectionChanged
                      ? "Save changes before marking this section done"
                      : undefined
                  }
                  onClick={() => void workspace.markDone()}
                >
                  {workspace.action === "transitioning"
                    ? "Updating…"
                    : "Mark done"}
                </button>
              </>
            )}
            {done && (
              <button
                type="button"
                className="workbench-button"
                disabled={busy}
                onClick={() => void workspace.reopen()}
              >
                {workspace.action === "transitioning"
                  ? "Reopening…"
                  : "Reopen section"}
              </button>
            )}
          </div>
        </footer>
      )}
    </section>
  );
}
