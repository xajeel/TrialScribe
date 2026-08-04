import { useEffect, useState, type FormEvent } from "react";

import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import { ErrorState, LoadingState } from "./AsyncState";

const activityFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
});

/** Left rail: every protocol in the organization, with the open one marked. */
export function ConversationPane({
  workspace,
}: {
  workspace: AuthoringWorkspaceController;
}) {
  const [creating, setCreating] = useState(false);
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
      setCreating(false);
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

  const busy = workspace.action !== "idle";
  const total = workspace.sections.length;
  const complete = workspace.sections.filter(
    (item) => item.status === "done",
  ).length;
  const percent = total === 0 ? 0 : Math.round((complete / total) * 100);

  return (
    <nav className="workbench-rail" aria-labelledby="conversations-title">
      <div className="workbench-rail__head">
        <h2 id="conversations-title">Protocol workspaces</h2>
      </div>

      {creating ? (
        <form className="workbench-rail__create" onSubmit={submitNew}>
          <label htmlFor="new-conversation-title">New protocol title</label>
          <input
            id="new-conversation-title"
            type="text"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="Protocol title"
            disabled={busy}
            autoFocus
            required
          />
          <div className="workbench-rail__create-actions">
            <button
              type="submit"
              className="workbench-button workbench-button--primary"
              disabled={newTitle.trim() === "" || busy}
            >
              {workspace.action === "creating" ? "Creating…" : "Create"}
            </button>
            <button
              type="button"
              className="workbench-button workbench-button--quiet"
              onClick={() => {
                setCreating(false);
                setNewTitle("");
              }}
              disabled={busy}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          className="workbench-rail__new"
          onClick={() => setCreating(true)}
          disabled={busy}
        >
          <span aria-hidden="true">+</span> New protocol
        </button>
      )}

      <div className="workbench-rail__list" aria-label="Protocol list">
        {workspace.conversationStatus === "loading" && (
          <LoadingState label="Loading protocols…" />
        )}
        {workspace.conversationStatus === "error" && (
          <ErrorState
            message="Could not load protocols."
            onRetry={workspace.retryConversations}
          />
        )}
        {workspace.conversationStatus === "ready" &&
          workspace.conversations.length === 0 && (
            <p className="workbench-rail__empty">
              No protocols yet. Create one to begin authoring.
            </p>
          )}
        {workspace.conversations.length > 0 && (
          <ul>
            {workspace.conversations.map((conversation) => {
              const selected =
                conversation.id === workspace.selectedConversationId;
              return (
                <li
                  key={conversation.id}
                  className={
                    selected
                      ? "workbench-rail__item workbench-rail__item--current"
                      : "workbench-rail__item"
                  }
                >
                  <button
                    type="button"
                    className="workbench-rail__select"
                    aria-current={selected ? "page" : undefined}
                    onClick={() =>
                      workspace.selectConversation(conversation.id)
                    }
                  >
                    <span className="workbench-rail__title">
                      {conversation.title}
                    </span>
                    <span className="workbench-rail__sub">
                      {selected && total > 0
                        ? `${total} sections · active ${activityFormatter.format(new Date(conversation.last_activity_at))}`
                        : `Active ${activityFormatter.format(new Date(conversation.last_activity_at))}`}
                    </span>
                    {selected && total > 0 && (
                      <span className="workbench-rail__progress">
                        <span style={{ width: `${percent}%` }} />
                      </span>
                    )}
                  </button>

                  {selected && !renaming && (
                    <button
                      type="button"
                      className="workbench-rail__rename"
                      onClick={() => {
                        setRenameTitle(conversation.title);
                        setRenaming(true);
                      }}
                      disabled={busy}
                    >
                      Rename
                    </button>
                  )}
                  {selected && renaming && (
                    <form
                      className="workbench-rail__rename-form"
                      onSubmit={submitRename}
                    >
                      <label htmlFor={`rename-${conversation.id}`}>
                        Protocol title
                      </label>
                      <input
                        id={`rename-${conversation.id}`}
                        type="text"
                        value={renameTitle}
                        onChange={(event) => setRenameTitle(event.target.value)}
                        disabled={busy}
                        required
                        autoFocus
                      />
                      <div className="workbench-rail__create-actions">
                        <button
                          type="submit"
                          className="workbench-button workbench-button--primary"
                          disabled={renameTitle.trim() === "" || busy}
                        >
                          {workspace.action === "renaming" ? "Saving…" : "Save"}
                        </button>
                        <button
                          type="button"
                          className="workbench-button workbench-button--quiet"
                          onClick={() => setRenaming(false)}
                          disabled={busy}
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
