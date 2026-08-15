import { Link } from "react-router-dom";

import type { GenerationAttemptRecord, M11Section } from "../api/types";
import { formatActivity } from "./ProtocolTable";

export type SectionState = "done" | "drafted" | "empty";

/** A section is drafted once it holds content, and done once it is accepted. */
export function sectionStateOf(section: M11Section): SectionState {
  if (section.status === "done") {
    return "done";
  }
  return section.content.trim() === "" ? "empty" : "drafted";
}

/** Words in stored section content, counted on whitespace runs. */
export function wordCountOf(content: string): number {
  const trimmed = content.trim();
  return trimmed === "" ? 0 : trimmed.split(/\s+/).length;
}

const STATE_LABELS: Record<SectionState, string> = {
  done: "Done",
  drafted: "Drafted",
  empty: "Not started",
};

/** Per-section drafting state: a table on wide screens, cards on narrow ones. */
export function SectionProgressList({
  sections,
  conversationId,
  attempts = [],
  onRetrySection,
}: {
  sections: M11Section[];
  conversationId: string;
  attempts?: GenerationAttemptRecord[];
  onRetrySection?: (sectionNumber: string) => void;
}) {
  const failed = new Set(
    attempts
      .filter((item) => item.status === "failed")
      .map((item) => item.section_number),
  );
  return (
    <div className="section-progress">
      <table role="table">
        <caption className="visually-hidden">
          Drafting state of every ICH M11 section
        </caption>
        <thead role="rowgroup">
          <tr role="row">
            <th role="columnheader" scope="col">
              Section
            </th>
            <th role="columnheader" scope="col">
              State
            </th>
            <th role="columnheader" scope="col">
              Content
            </th>
            <th role="columnheader" scope="col">
              Last updated
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {sections.map((section) => {
            const state = sectionStateOf(section);
            const words = wordCountOf(section.content);
            return (
              <tr className="section-progress__row" key={section.id} role="row">
                <td role="cell" data-label="Section">
                  <Link
                    className="section-progress__title"
                    to={`/workspace/${encodeURIComponent(conversationId)}`}
                  >
                    <span className="section-progress__number">
                      {section.section_number}
                    </span>
                    {section.title}
                  </Link>
                </td>
                <td role="cell" data-label="State">
                  {failed.has(section.section_number) ? (
                    <span className="section-progress__retry">
                      <span className="section-progress__state section-progress__state--empty">
                        Needs retry
                      </span>
                      {onRetrySection !== undefined && (
                        <button
                          type="button"
                          className="section-progress__retry-button"
                          aria-label={`Retry section ${section.section_number}`}
                          onClick={() => onRetrySection(section.section_number)}
                        >
                          Retry
                        </button>
                      )}
                    </span>
                  ) : (
                    <span
                      className={`section-progress__state section-progress__state--${state}`}
                    >
                      {STATE_LABELS[state]}
                    </span>
                  )}
                </td>
                <td role="cell" data-label="Content">
                  {words === 0 ? (
                    <span className="section-progress__muted">
                      No content yet
                    </span>
                  ) : (
                    <span className="section-progress__count">
                      {words.toLocaleString()}{" "}
                      {words === 1 ? "word" : "words"}
                    </span>
                  )}
                </td>
                <td role="cell" data-label="Last updated">
                  <span className="section-progress__count">
                    {formatActivity(section.updated_at)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
