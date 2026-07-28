import { useEffect, useState, type FormEvent } from "react";

import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "./AsyncState";

/** Center-pane durable conversation history and manual M11 section editor. */
export function AuthoringPane({
  workspace,
}: {
  workspace: AuthoringWorkspaceController;
}) {
  const [instruction, setInstruction] = useState("");
  const [sectionInstructions, setSectionInstructions] = useState("");
  const [sectionContent, setSectionContent] = useState("");
  const section = workspace.selectedSection;

  useEffect(() => {
    setSectionInstructions(section?.instructions ?? "");
    setSectionContent(section?.content ?? "");
  }, [section?.current_revision, section?.id, section?.instructions, section?.content]);

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

  const submitSection = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await workspace.saveSection(sectionInstructions, sectionContent);
  };

  const sectionChanged =
    section !== null &&
    (sectionInstructions !== section.instructions ||
      sectionContent !== section.content);
  const busy = workspace.action !== "idle";

  return (
    <section
      className="workspace-pane authoring-pane"
      aria-labelledby="authoring-pane-title"
    >
      <div className="workspace-pane__header authoring-pane__header">
        <div>
          <p className="workspace-pane__eyebrow">Current workspace</p>
          <h2 id="authoring-pane-title">
            {workspace.selectedConversation?.title ?? "Authoring"}
          </h2>
        </div>
        {section !== null && (
          <span
            className={
              section.status === "done"
                ? "section-status section-status--done"
                : "section-status"
            }
          >
            {section.status}
          </span>
        )}
      </div>

      {workspace.feedback !== null && (
        <div
          className={`workspace-feedback workspace-feedback--${workspace.feedback.kind}`}
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

      {workspace.conversationStatus === "ready" &&
        workspace.conversations.length === 0 && (
          <EmptyState
            title="Create a conversation"
            description="Your durable messages, documents, and M11 sections will appear here."
          />
        )}

      {workspace.selectedConversation !== null &&
        workspace.workspaceStatus === "loading" && (
          <LoadingState label="Loading this authoring workspace…" />
        )}

      {workspace.selectedConversation !== null &&
        workspace.workspaceStatus === "error" && (
          <ErrorState
            message="Could not load this authoring workspace."
            onRetry={workspace.retryWorkspace}
          />
        )}

      {workspace.selectedConversation !== null &&
        workspace.workspaceStatus === "ready" && (
          <div className="authoring-pane__body">
            <section
              className="conversation-thread"
              aria-labelledby="conversation-thread-title"
            >
              <div className="authoring-section-heading">
                <div>
                  <p className="workspace-pane__eyebrow">Conversation</p>
                  <h3 id="conversation-thread-title">Instructions</h3>
                </div>
                <span className="generation-cue">
                  Generation arrives in a later feature
                </span>
              </div>
              <div
                className="pane-scroll message-list"
                tabIndex={0}
                aria-label="Conversation messages"
              >
                {workspace.messages.length === 0 ? (
                  <EmptyState
                    title="No instructions yet"
                    description="Add context or a writing request for this conversation."
                  />
                ) : (
                  <ol>
                    {workspace.messages.map((message) => (
                      <li
                        key={message.id}
                        className={`message message--${message.role}`}
                      >
                        <span className="message__role">
                          {message.role === "user" ? "You" : "TrialScribe"}
                        </span>
                        <p>{message.content}</p>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
              <form
                className="instruction-composer"
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
                  className="button button--primary"
                  disabled={instruction.trim() === "" || busy}
                >
                  {workspace.action === "sending"
                    ? "Saving instruction…"
                    : "Save instruction"}
                </button>
              </form>
            </section>

            <section
              className="section-editor"
              aria-labelledby="section-editor-title"
            >
              {section === null ? (
                <EmptyState
                  title="No M11 sections"
                  description="The section catalog could not provide an authoring section."
                />
              ) : (
                <>
                  <div className="authoring-section-heading">
                    <div>
                      <p className="workspace-pane__eyebrow">
                        Section {section.section_number}
                      </p>
                      <h3 id="section-editor-title">{section.title}</h3>
                    </div>
                    <span className="revision-label">
                      Revision {section.current_revision}
                    </span>
                  </div>
                  <form className="section-editor__form" onSubmit={submitSection}>
                    <label htmlFor="section-instructions">
                      Section instructions
                    </label>
                    <textarea
                      id="section-instructions"
                      value={sectionInstructions}
                      onChange={(event) =>
                        setSectionInstructions(event.target.value)
                      }
                      rows={3}
                      disabled={busy || section.status === "done"}
                      placeholder="Add section-specific writing guidance…"
                    />
                    <label htmlFor="section-content">Section content</label>
                    <textarea
                      id="section-content"
                      className="section-content-input"
                      value={sectionContent}
                      onChange={(event) => setSectionContent(event.target.value)}
                      rows={10}
                      disabled={busy || section.status === "done"}
                      placeholder="Draft the complete section here…"
                    />
                    <div className="section-editor__actions">
                      {section.status === "draft" && (
                        <>
                          <button
                            type="submit"
                            className="button button--primary"
                            disabled={!sectionChanged || busy}
                          >
                            {workspace.action === "saving"
                              ? "Saving section…"
                              : "Save section"}
                          </button>
                          <button
                            type="button"
                            className="button button--ghost"
                            onClick={() => void workspace.markDone()}
                            disabled={sectionChanged || busy}
                            title={
                              sectionChanged
                                ? "Save changes before marking this section done"
                                : undefined
                            }
                          >
                            {workspace.action === "transitioning"
                              ? "Updating…"
                              : "Mark done"}
                          </button>
                        </>
                      )}
                      {section.status === "done" && (
                        <button
                          type="button"
                          className="button button--ghost"
                          onClick={() => void workspace.reopen()}
                          disabled={busy}
                        >
                          {workspace.action === "transitioning"
                            ? "Reopening…"
                            : "Reopen section"}
                        </button>
                      )}
                    </div>
                    {sectionChanged && section.status === "draft" && (
                      <p className="editor-hint" role="status">
                        Save these changes before marking the section done.
                      </p>
                    )}
                  </form>
                </>
              )}
            </section>
          </div>
        )}
    </section>
  );
}
