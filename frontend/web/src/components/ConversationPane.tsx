import { useEffect, useState, type FormEvent } from "react";

import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "./AsyncState";

const activityFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

/** Left-pane conversation navigation and reversible workspace actions. */
export function ConversationPane({
  workspace,
}: {
  workspace: AuthoringWorkspaceController;
}) {
  const [newTitle, setNewTitle] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [renameTitle, setRenameTitle] = useState("");

  useEffect(() => {
    setRenaming(false);
    setRenameTitle(workspace.selectedConversation?.title ?? "");
  }, [
    workspace.selectedConversation?.id,
    workspace.selectedConversation?.title,
  ]);

  const submitNew = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const title = newTitle.trim();
    if (title === "") {
      return;
    }
    if (await workspace.create(title)) {
      setNewTitle("");
    }
  };

  const submitRename = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const title = renameTitle.trim();
    if (title === "") {
      return;
    }
    if (await workspace.rename(title)) {
      setRenaming(false);
    }
  };

  return (
    <nav
      className="workspace-pane conversation-pane"
      aria-labelledby="conversations-title"
    >
      <div className="workspace-pane__header">
        <div>
          <p className="workspace-pane__eyebrow">Authoring</p>
          <h1 id="conversations-title">Conversations</h1>
        </div>
      </div>

      <form className="conversation-create" onSubmit={submitNew}>
        <label htmlFor="new-conversation-title">New conversation</label>
        <div className="conversation-create__controls">
          <input
            id="new-conversation-title"
            type="text"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="Protocol title"
            disabled={workspace.action !== "idle"}
            required
          />
          <button
            type="submit"
            className="button button--primary"
            disabled={
              newTitle.trim() === "" || workspace.action !== "idle"
            }
          >
            {workspace.action === "creating" ? "Creating…" : "Create"}
          </button>
        </div>
      </form>

      <div
        className="pane-scroll conversation-list"
        tabIndex={0}
        aria-label="Conversation list"
      >
        {workspace.conversationStatus === "loading" && (
          <LoadingState label="Loading conversations…" />
        )}
        {workspace.conversationStatus === "error" && (
          <ErrorState
            message="Could not load conversations."
            onRetry={workspace.retryConversations}
          />
        )}
        {workspace.conversationStatus === "ready" &&
          workspace.conversations.length === 0 && (
            <EmptyState
              title="No conversations yet"
              description="Create one to begin authoring a protocol."
            />
          )}
        {workspace.conversations.length > 0 && (
          <ul className="conversation-list__items">
            {workspace.conversations.map((conversation) => {
              const selected =
                conversation.id === workspace.selectedConversationId;
              return (
                <li
                  key={conversation.id}
                  className={
                    selected
                      ? "conversation-list__item conversation-list__item--selected"
                      : "conversation-list__item"
                  }
                >
                  <button
                    type="button"
                    className="conversation-select"
                    aria-current={selected ? "page" : undefined}
                    onClick={() =>
                      workspace.selectConversation(conversation.id)
                    }
                  >
                    <span className="conversation-select__title">
                      {conversation.title}
                    </span>
                    <span className="conversation-select__activity">
                      Active{" "}
                      {activityFormatter.format(
                        new Date(conversation.last_activity_at),
                      )}
                    </span>
                  </button>
                  {selected && !renaming && (
                    <button
                      type="button"
                      className="conversation-rename-trigger"
                      onClick={() => {
                        setRenameTitle(conversation.title);
                        setRenaming(true);
                      }}
                      disabled={workspace.action !== "idle"}
                    >
                      Rename
                    </button>
                  )}
                  {selected && renaming && (
                    <form
                      className="conversation-rename"
                      onSubmit={submitRename}
                    >
                      <label htmlFor={`rename-${conversation.id}`}>
                        Conversation title
                      </label>
                      <input
                        id={`rename-${conversation.id}`}
                        type="text"
                        value={renameTitle}
                        onChange={(event) =>
                          setRenameTitle(event.target.value)
                        }
                        disabled={workspace.action !== "idle"}
                        required
                        autoFocus
                      />
                      <div className="conversation-rename__actions">
                        <button
                          type="submit"
                          className="button button--primary"
                          disabled={
                            renameTitle.trim() === "" ||
                            workspace.action !== "idle"
                          }
                        >
                          {workspace.action === "renaming"
                            ? "Saving…"
                            : "Save"}
                        </button>
                        <button
                          type="button"
                          className="button button--ghost"
                          onClick={() => setRenaming(false)}
                          disabled={workspace.action !== "idle"}
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </nav>
  );
}
