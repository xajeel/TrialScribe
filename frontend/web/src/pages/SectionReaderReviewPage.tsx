import { useState } from "react";

import { SectionReader } from "../components/SectionReader";
import {
  reviewReaderSection,
  type ReaderReview,
} from "../product/workbenchReviewFixtures";

/**
 * Development-only host for the section reader, so each of its three states is
 * reviewable without a session or a populated workbench behind it.
 */
export function SectionReaderReviewPage({ review }: { review: ReaderReview }) {
  const [open, setOpen] = useState(true);
  const section = reviewReaderSection(review);

  return (
    <div className="protocol-workspace section-reader-review">
      <main className="protocol-workspace__main">
        <div className="protocol-workspace__page-header">
          <p className="protocol-workspace__page-eyebrow">Review harness</p>
          <h1>Section reader — {review}</h1>
          <p className="protocol-workspace__lede">
            {section.section_number} · {section.title}
          </p>
        </div>
        {!open && (
          <button
            type="button"
            className="source-library__add"
            onClick={() => setOpen(true)}
          >
            Reopen reader
          </button>
        )}
      </main>

      <SectionReader
        section={open ? section : null}
        returnFocusTo={null}
        onOpenInEditor={() => setOpen(false)}
        onAddInstruction={() => setOpen(false)}
        onClose={() => setOpen(false)}
      />
    </div>
  );
}
