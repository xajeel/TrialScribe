import type { ConversationMessage } from "../api/types";
import { formatActivity } from "./ProtocolTable";

const EXAMPLES = [
  {
    label: "Tone",
    text: "Maintain a strictly objective, academic tone for peer review.",
  },
  {
    label: "Compliance",
    text: "Reference ICH-GCP guidelines in all procedural sections.",
  },
  {
    label: "Terminology",
    text: "Prioritize CDISC standards for all data definitions.",
  },
] as const;

function initialsFor(label: string): string {
  return label
    .split(" ")
    .map((word) => word.charAt(0))
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/** The protocol's saved writing instructions, oldest first. */
export function InstructionTimeline({
  instructions,
  accountId,
}: {
  instructions: ConversationMessage[];
  accountId: string | null;
}) {
  if (instructions.length === 0) {
    return (
      <section
        className="instruction-empty"
        aria-labelledby="instruction-empty-title"
      >
        <span className="instruction-empty__mark" aria-hidden="true" />
        <h2 id="instruction-empty-title">No saved instructions</h2>
        <p>
          Add protocol context or a writing constraint before drafting. Your
          saved instructions will appear here.
        </p>
        <div className="instruction-empty__examples">
          <h3 id="instruction-example-title">Examples</h3>
          <ul aria-labelledby="instruction-example-title">
            {EXAMPLES.map((example) => (
              <li key={example.label}>
                <span className="instruction-empty__example-label">
                  {example.label}
                </span>
                <span className="instruction-empty__example-text">
                  {example.text}
                </span>
              </li>
            ))}
          </ul>
          <p className="instruction-empty__note">
            These are examples only. Nothing above is saved to this protocol.
          </p>
        </div>
      </section>
    );
  }

  return (
    <ol className="instruction-timeline" aria-label="Saved instructions">
      {instructions.map((entry) => {
        // The API exposes no display name for another member, so the author is
        // named only as precisely as the data allows.
        const mine =
          accountId !== null && entry.author_account_id === accountId;
        const author = mine ? "You" : "Team member";
        return (
          <li className="instruction-entry" key={entry.id}>
            <div className="instruction-entry__meta">
              <span className="instruction-entry__avatar" aria-hidden="true">
                {initialsFor(author)}
              </span>
              <span className="instruction-entry__author">{author}</span>
              <span className="instruction-entry__time">
                {formatActivity(entry.created_at)}
              </span>
            </div>
            <p className="instruction-entry__text">{entry.content}</p>
          </li>
        );
      })}
    </ol>
  );
}
