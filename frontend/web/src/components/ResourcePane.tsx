import { useRef, useState, type FormEvent } from "react";

import type {
  DocumentKind,
  M11Section,
} from "../api/types";
import type { AuthoringWorkspaceController } from "../workspace/useAuthoringWorkspace";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "./AsyncState";

function readableBytes(byteSize: number): string {
  if (byteSize < 1024) {
    return `${byteSize} B`;
  }
  if (byteSize < 1024 * 1024) {
    return `${(byteSize / 1024).toFixed(1)} KB`;
  }
  return `${(byteSize / (1024 * 1024)).toFixed(1)} MB`;
}

/** Right-pane uploaded sources and ordered M11 section navigation. */
export function ResourcePane({
  workspace,
  onOpenSection,
}: {
  workspace: AuthoringWorkspaceController;
  onOpenSection: (section: M11Section, opener: HTMLElement) => void;
}) {
  const [kind, setKind] = useState<DocumentKind>("research_document");
  const [file, setFile] = useState<File | null>(null);
  const [uploadFeedback, setUploadFeedback] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const uploading = workspace.action === "uploading";

  const submitUpload = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (file === null) {
      return;
    }
    setUploadFeedback("Uploading document…");
    const filename = file.name;
    if (await workspace.upload(kind, file)) {
      setUploadFeedback(`${filename} uploaded successfully.`);
      setFile(null);
      if (fileInputRef.current !== null) {
        fileInputRef.current.value = "";
      }
    } else {
      setUploadFeedback("Upload failed. Check the file and try again.");
    }
  };

  return (
    <aside
      className="workspace-pane resource-pane"
      aria-labelledby="resources-title"
    >
      <div className="workspace-pane__header">
        <div>
          <p className="workspace-pane__eyebrow">Conversation resources</p>
          <h2 id="resources-title">Sources &amp; sections</h2>
        </div>
      </div>

      <section
        className="resource-group resource-group--documents"
        aria-labelledby="documents-title"
      >
        <div className="resource-group__header">
          <h3 id="documents-title">Documents</h3>
          <span>{workspace.documents.length}</span>
        </div>
        <form className="document-upload" onSubmit={submitUpload}>
          <label htmlFor="document-kind">Document kind</label>
          <select
            id="document-kind"
            value={kind}
            onChange={(event) => {
              setKind(event.target.value as DocumentKind);
              setFile(null);
              setUploadFeedback(null);
              if (fileInputRef.current !== null) {
                fileInputRef.current.value = "";
              }
            }}
            disabled={uploading}
          >
            <option value="research_document">Research document</option>
            <option value="trial_data">Trial JSON</option>
          </select>
          <label htmlFor="document-file">Choose file</label>
          <input
            ref={fileInputRef}
            id="document-file"
            type="file"
            accept={
              kind === "trial_data"
                ? ".json,application/json"
                : ".pdf,.txt,application/pdf,text/plain"
            }
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setUploadFeedback(null);
            }}
            disabled={uploading}
            required
          />
          <p className="chosen-file">
            {file === null ? "No file chosen" : file.name}
          </p>
          <button
            type="submit"
            className="button button--primary"
            disabled={
              file === null ||
              uploading ||
              workspace.selectedConversation === null
            }
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
          {uploadFeedback !== null && (
            <p
              className={
                uploadFeedback.startsWith("Upload failed")
                  ? "upload-feedback upload-feedback--error"
                  : "upload-feedback"
              }
              role={
                uploadFeedback.startsWith("Upload failed")
                  ? "alert"
                  : "status"
              }
            >
              {uploadFeedback}
            </p>
          )}
        </form>

        <div
          className="pane-scroll document-list"
          tabIndex={0}
          aria-label="Uploaded documents"
        >
          {workspace.selectedConversation !== null &&
            workspace.workspaceStatus === "loading" && (
              <LoadingState label="Loading documents…" />
            )}
          {workspace.selectedConversation !== null &&
            workspace.workspaceStatus === "error" && (
              <ErrorState
                message="Could not load documents."
                onRetry={workspace.retryWorkspace}
              />
            )}
          {workspace.workspaceStatus === "ready" &&
            workspace.documents.length === 0 && (
              <EmptyState
                title="No documents"
                description="Upload trial JSON or a research document."
              />
            )}
          {workspace.documents.length > 0 && (
            <ul>
              {workspace.documents.map((document) => (
                <li key={document.id} className="document-item">
                  <span className="document-item__name">
                    {document.filename}
                  </span>
                  <span className="document-item__meta">
                    {document.kind === "trial_data"
                      ? "Trial data"
                      : "Research"}{" "}
                    · {readableBytes(document.byte_size)}
                  </span>
                  <span
                    className={`document-status document-status--${document.status}`}
                  >
                    {document.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <section
        className="resource-group resource-group--sections"
        aria-labelledby="sections-title"
      >
        <div className="resource-group__header">
          <h3 id="sections-title">M11 sections</h3>
          <span>{workspace.sections.length}</span>
        </div>
        <div
          className="pane-scroll section-list"
          tabIndex={0}
          aria-label="M11 section titles"
        >
          {workspace.selectedConversation !== null &&
            workspace.workspaceStatus === "loading" && (
              <LoadingState label="Loading M11 sections…" />
            )}
          {workspace.selectedConversation !== null &&
            workspace.workspaceStatus === "error" && (
              <ErrorState
                message="Could not load M11 sections."
                onRetry={workspace.retryWorkspace}
              />
            )}
          {workspace.workspaceStatus === "ready" &&
            workspace.sections.length === 0 && (
              <EmptyState
                title="No M11 sections"
                description="Retry to initialize this conversation's workspace."
              />
            )}
          {workspace.sections.length > 0 && (
            <ol>
              {workspace.sections.map((section) => {
                const selected =
                  section.section_number ===
                  workspace.selectedSectionNumber;
                return (
                  <li
                    key={section.id}
                    className={
                      selected
                        ? "section-list__item section-list__item--selected"
                        : "section-list__item"
                    }
                  >
                    <button
                      type="button"
                      className="section-select"
                      aria-pressed={selected}
                      onClick={() =>
                        workspace.selectSection(section.section_number)
                      }
                    >
                      <span className="section-select__number">
                        {section.section_number}
                      </span>
                      <span className="section-select__title">
                        {section.title}
                      </span>
                      <span
                        className={
                          section.status === "done"
                            ? "section-select__state section-select__state--done"
                            : "section-select__state"
                        }
                      >
                        {section.status}
                      </span>
                    </button>
                    <button
                      type="button"
                      className="section-open"
                      onClick={(event) =>
                        onOpenSection(section, event.currentTarget)
                      }
                    >
                      Open full section
                    </button>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </section>
    </aside>
  );
}
