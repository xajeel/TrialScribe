import { useState } from "react";

import type {
  ExportManifestItem,
  ExportScope,
} from "../product/deliveryAuditReviewFixtures";

function ManifestRow({
  item,
  included,
}: {
  item: ExportManifestItem;
  included: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailId = `export-manifest-detail-${item.id}`;
  return (
    <li className="section-manifest__row">
      <button
        type="button"
        className="section-manifest__toggle"
        aria-expanded={expanded}
        aria-controls={detailId}
        onClick={() => setExpanded((current) => !current)}
      >
        <span className="section-manifest__number">{item.sectionNumber}</span>
        <strong>{item.title}</strong>
        <span className="section-manifest__chevron" aria-hidden="true">
          {expanded ? "−" : "+"}
        </span>
      </button>
      <span
        className={`section-manifest__status section-manifest__status--${item.status}`}
      >
        {item.status === "done" ? "Done" : "Draft"}
      </span>
      <span
        className={
          included
            ? "section-manifest__inclusion section-manifest__inclusion--included"
            : "section-manifest__inclusion section-manifest__inclusion--excluded"
        }
      >
        {included ? "Included" : "Excluded"}
      </span>
      <span className="section-manifest__words">
        {item.words === 0 ? "—" : `${item.words.toLocaleString()} words`}
      </span>
      <div
        id={detailId}
        className={
          expanded
            ? "section-manifest__detail section-manifest__detail--open"
            : "section-manifest__detail"
        }
      >
        <span>Revision {item.revision}</span>
        <span>
          {item.words === 0 ? "No stored content" : `${item.words.toLocaleString()} words`}
        </span>
      </div>
    </li>
  );
}
export function SectionManifest({
  sections,
  scope,
}: {
  sections: ReadonlyArray<ExportManifestItem>;
  scope: ExportScope;
}) {
  return (
    <section className="section-manifest" aria-labelledby="section-manifest-title">
      <div className="section-manifest__heading">
        <h2 id="section-manifest-title">ICH M11 section manifest</h2>
        <span>{sections.length} fixed-order sections</span>
      </div>
      {sections.length === 0 ? (
        <p className="section-manifest__empty">No protocol sections are available.</p>
      ) : (
        <ol>
          {sections.map((item) => (
            <ManifestRow
              key={item.id}
              item={item}
              included={scope === "include-drafts" || item.status === "done"}
            />
          ))}
        </ol>
      )}
    </section>
  );
}
