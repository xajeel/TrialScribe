import type {
  ExportScope,
  ExportView,
} from "../product/deliveryAuditReviewFixtures";

export function ExportProtocolSummary({ view }: { view: ExportView }) {
  return (
    <section
      className="export-protocol-summary"
      aria-labelledby="export-protocol-summary-title"
    >
      <div className="export-protocol-summary__heading">
        <h2 id="export-protocol-summary-title">Protocol summary</h2>
        <span>{view.currentStatus}</span>
      </div>
      <dl>
        <div>
          <dt>Protocol ID</dt>
          <dd>{view.protocolId}</dd>
        </div>
        <div>
          <dt>Catalog</dt>
          <dd>{view.catalogVersion ?? "Not available"}</dd>
        </div>
        <div>
          <dt>Completion</dt>
          <dd>
            {view.doneSections} of {view.sections.length} sections done
          </dd>
        </div>
        <div>
          <dt>Current status</dt>
          <dd>{view.currentStatus}</dd>
        </div>
      </dl>
    </section>
  );
}
export function ExportScopeSelector({
  view,
  scope,
  onScopeChange,
}: {
  view: ExportView;
  scope: ExportScope;
  onScopeChange: (scope: ExportScope) => void;
}) {
  return (
    <fieldset className="export-scope">
      <legend>Export scope</legend>
      <label
        className={
          scope === "done-only"
            ? "export-scope__choice export-scope__choice--selected"
            : "export-scope__choice"
        }
      >
        <input
          type="radio"
          name="export-scope"
          value="done-only"
          checked={scope === "done-only"}
          onChange={() => onScopeChange("done-only")}
        />
        <span>
          <strong>Done sections only</strong>
          <small>
            Includes {view.doneSections} completed sections. {view.draftSections}{" "}
            {view.draftSections === 1 ? "Draft section is" : "Draft sections are"}{" "}
            omitted.
          </small>
        </span>
      </label>
      <label
        className={
          scope === "include-drafts"
            ? "export-scope__choice export-scope__choice--selected"
            : "export-scope__choice"
        }
      >
        <input
          type="radio"
          name="export-scope"
          value="include-drafts"
          checked={scope === "include-drafts"}
          onChange={() => onScopeChange("include-drafts")}
        />
        <span>
          <strong>Include unfinished sections</strong>
          <small>
            Includes all {view.sections.length} sections. {view.draftSections}{" "}
            unfinished {view.draftSections === 1 ? "section" : "sections"} will
            carry a visible DRAFT label.
          </small>
        </span>
      </label>
      {scope === "include-drafts" && view.draftSections > 0 && (
        <p className="export-scope__warning" role="status">
          Unfinished content will be clearly marked as draft in the document.
        </p>
      )}
    </fieldset>
  );
}

export function ExportContentSummary({
  view,
  scope,
}: {
  view: ExportView;
  scope: ExportScope;
}) {
  const included =
    scope === "include-drafts" ? view.sections.length : view.doneSections;
  return (
    <section
      className="export-content-summary"
      aria-labelledby="export-content-summary-title"
    >
      <h2 id="export-content-summary-title">Document content</h2>
      <dl>
        <div>
          <dt>Format</dt>
          <dd>Microsoft Word (.docx)</dd>
        </div>
        <div>
          <dt>Sections</dt>
          <dd>{included} included</dd>
        </div>
        {view.citations !== undefined && (
          <div>
            <dt>Citations</dt>
            <dd>{view.citations}</dd>
          </div>
        )}
        {view.references !== undefined && (
          <div>
            <dt>References</dt>
            <dd>{view.references}</dd>
          </div>
        )}
        <div>
          <dt>Revision basis</dt>
          <dd>Current accepted section revisions</dd>
        </div>
        {view.requester !== undefined && (
          <div>
            <dt>Requested by</dt>
            <dd>{view.requester}</dd>
          </div>
        )}
      </dl>
      <p>
        Available headings, citations, references, and protocol metadata will be
        assembled into the exported file.
      </p>
    </section>
  );
}
