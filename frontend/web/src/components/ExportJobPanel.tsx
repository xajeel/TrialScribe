import type {
  ExportFileView,
  ExportJobView,
} from "../product/deliveryAuditReviewFixtures";

export type ExportJobPanelState = "building" | "ready" | "failed";

function formatFileSize(value: number): string {
  return `${(value / 1_000_000).toFixed(1)} MB`;
}
function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function FileCard({
  file,
  onDownload,
  prominent = false,
}: {
  file: ExportFileView;
  onDownload: (file: ExportFileView) => void;
  prominent?: boolean;
}) {
  return (
    <article
      className={
        prominent
          ? "export-file export-file--prominent"
          : "export-file"
      }
    >
      <div>
        <strong>{file.filename}</strong>
        <span>
          {formatFileSize(file.byteSize)} · {file.sections} sections · Created{" "}
          {formatDate(file.createdAt)}
        </span>
        {!prominent && (
          <small>
            {file.requester} · {file.scope === "done-only" ? "Done only" : "Included drafts"}
          </small>
        )}
      </div>
      <button type="button" onClick={() => onDownload(file)}>
        {prominent ? "Download DOCX" : "Download"}
      </button>
    </article>
  );
}

export function ExportJobPanel({
  state,
  job,
  onClose,
  onRetry,
  onBack,
  onCreateAnother,
  onDownload,
}: {
  state: ExportJobPanelState;
  job: ExportJobView;
  onClose: () => void;
  onRetry: () => void;
  onBack: () => void;
  onCreateAnother: () => void;
  onDownload: (file: ExportFileView) => void;
}) {
  if (state === "building") {
    return (
      <section className="export-job export-job--building" aria-live="polite">
        <div className="export-job__intro">
          <p className="delivery-sheet__eyebrow">Document assembly</p>
          <h2>Preparing export</h2>
          <p>The document is being assembled in fixed ICH M11 order.</p>
        </div>
        <ol className="export-job__stages">
          {job.stages.map((stage) => (
            <li key={stage.id} className={`export-job__stage export-job__stage--${stage.state}`}>
              <span aria-hidden="true">
                {stage.state === "complete" ? "✓" : stage.state === "current" ? "•" : "○"}
              </span>
              <div>
                <strong>{stage.label}</strong>
                <small>{stage.detail}</small>
              </div>
            </li>
          ))}
        </ol>
        <p className="export-job__notice">
          You can close this panel. The export will remain available in this
          protocol workspace.
        </p>
        <footer className="export-job__footer">
          <button type="button" onClick={onClose}>Close panel</button>
        </footer>
      </section>
    );
  }

  if (state === "failed") {
    return (
      <section className="export-job export-job--failed" aria-live="polite">
        <div className="export-job__result-icon" aria-hidden="true">!</div>
        <h2>Export could not be completed</h2>
        <p>Your protocol content was not changed. Try the export again.</p>
        <footer className="export-job__footer">
          <button className="delivery-button--primary" type="button" onClick={onRetry}>Retry export</button>
          <button type="button" onClick={onBack}>Back to options</button>
        </footer>
      </section>
    );
  }

  return (
    <section className="export-job export-job--ready" aria-live="polite">
      <div className="export-job__result-icon" aria-hidden="true">✓</div>
      <h2>Protocol ready</h2>
      <p>Your document has been compiled and prepared for download.</p>
      <FileCard file={job.readyFile} onDownload={onDownload} prominent />
      <button className="export-job__another" type="button" onClick={onCreateAnother}>
        Create another export
      </button>
      <section className="recent-exports" aria-labelledby="recent-exports-title">
        <h3 id="recent-exports-title">Recent exports</h3>
        <div>
          {job.recentExports.map((file) => (
            <FileCard key={file.exportId} file={file} onDownload={onDownload} />
          ))}
        </div>
      </section>
      <p className="export-job__trace">
        Export ID {job.readyFile.exportId} · Current accepted revisions
      </p>
    </section>
  );
}
