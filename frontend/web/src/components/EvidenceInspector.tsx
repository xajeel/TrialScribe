import { useId, useState } from "react";

import type {
  EvidenceReviewKind,
  EvidenceReviewRecord,
} from "../product/evidenceRewriteReviewFixtures";

const EVIDENCE_TABS: ReadonlyArray<{
  kind: Exclude<EvidenceReviewKind, "section">;
  label: string;
}> = [
  { kind: "pdf", label: "PDF" },
  { kind: "json", label: "JSON" },
  { kind: "web", label: "Web" },
];

export interface EvidenceInspectorProps {
  evidence: EvidenceReviewRecord;
  active: EvidenceReviewKind;
  onSelectKind: (kind: Exclude<EvidenceReviewKind, "section">) => void;
  onClose: () => void;
}

function PdfDetails({
  evidence,
}: {
  evidence: Extract<EvidenceReviewRecord, { kind: "pdf" | "section" }>;
}) {
  return (
    <dl className="evidence-inspector__facts">
      <div>
        <dt>Document type</dt>
        <dd>{evidence.documentType}</dd>
      </div>
      <div>
        <dt>Page</dt>
        <dd>{evidence.page}</dd>
      </div>
      <div>
        <dt>Paragraph</dt>
        <dd>{evidence.paragraph}</dd>
      </div>
      {evidence.kind === "section" && (
        <div>
          <dt>Reference</dt>
          <dd>{evidence.referenceId}</dd>
        </div>
      )}
    </dl>
  );
}

function JsonDetails({
  evidence,
}: {
  evidence: Extract<EvidenceReviewRecord, { kind: "json" }>;
}) {
  return (
    <div className="evidence-inspector__json">
      <p className="evidence-inspector__label">Selected node</p>
      <code>{evidence.node}</code>
      <dl className="evidence-inspector__fields">
        {evidence.fields.map((field) => (
          <div key={field.label}>
            <dt>{field.label}</dt>
            <dd>{field.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function WebDetails({
  evidence,
}: {
  evidence: Extract<EvidenceReviewRecord, { kind: "web" }>;
}) {
  return (
    <dl className="evidence-inspector__facts evidence-inspector__facts--web">
      <div>
        <dt>Publication</dt>
        <dd>{evidence.publication}</dd>
      </div>
      <div>
        <dt>Domain</dt>
        <dd>{evidence.domain}</dd>
      </div>
      <div>
        <dt>Accessed</dt>
        <dd>{evidence.accessed}</dd>
      </div>
      <div>
        <dt>Article</dt>
        <dd>{evidence.articleTitle}</dd>
      </div>
    </dl>
  );
}

/**
 * Adaptive Page 12 inspector. It consumes a future-facing provenance contract
 * but performs no fetch, mutation, external navigation, or clipboard write.
 */
export function EvidenceInspector({
  evidence,
  active,
  onSelectKind,
  onClose,
}: EvidenceInspectorProps) {
  const [copyStatus, setCopyStatus] = useState("");
  const titleId = useId();
  const activeTab = active === "section" ? "pdf" : active;

  return (
    <aside className="evidence-inspector" aria-labelledby={titleId}>
      <header className="evidence-inspector__header">
        <div>
          <p className="evidence-inspector__eyebrow">Citation reference</p>
          <h2 id={titleId}>Evidence inspector</h2>
        </div>
        <button
          type="button"
          className="evidence-inspector__close"
          onClick={onClose}
          aria-label="Close evidence inspector"
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>

      <div className="evidence-inspector__tabs" role="tablist" aria-label="Evidence type">
        {EVIDENCE_TABS.map((tab) => (
          <button
            key={tab.kind}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.kind}
            onClick={() => onSelectKind(tab.kind)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="evidence-inspector__scroll">
        <section className="evidence-inspector__source" aria-labelledby={`${titleId}-source`}>
          <p className="evidence-inspector__label">Source</p>
          <h3 id={`${titleId}-source`}>{evidence.sourceTitle}</h3>
          <p>{evidence.sourceLabel}</p>
          <span>{evidence.locator}</span>
        </section>

        <section className="evidence-inspector__passage" aria-labelledby={`${titleId}-passage`}>
          <p className="evidence-inspector__label" id={`${titleId}-passage`}>
            Cited passage
          </p>
          <blockquote>{evidence.passage}</blockquote>
          <p className="evidence-inspector__citation">{evidence.citation}</p>
        </section>

        {evidence.kind === "json" ? (
          <JsonDetails evidence={evidence} />
        ) : evidence.kind === "web" ? (
          <WebDetails evidence={evidence} />
        ) : (
          <PdfDetails evidence={evidence} />
        )}

        <section className="evidence-inspector__support" aria-labelledby={`${titleId}-support`}>
          <p className="evidence-inspector__label" id={`${titleId}-support`}>
            Support for this section
          </p>
          <p>{evidence.support}</p>
        </section>

        {evidence.kind === "section" && (
          <section className="evidence-inspector__annotation" aria-labelledby={`${titleId}-annotation`}>
            <p className="evidence-inspector__label" id={`${titleId}-annotation`}>
              Annotation note
            </p>
            <p>{evidence.annotation}</p>
          </section>
        )}
      </div>

      <footer className="evidence-inspector__footer">
        <button
          type="button"
          onClick={() => setCopyStatus("Citation copied in this review demonstration.")}
        >
          Copy citation
        </button>
        <p className="evidence-inspector__fixture-note">
          Review fixture — no source or record is changed.
        </p>
        <p className="visually-hidden" role="status">
          {copyStatus}
        </p>
      </footer>
    </aside>
  );
}
