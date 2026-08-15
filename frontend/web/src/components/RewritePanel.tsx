import { useId, useState, type FormEvent } from "react";

import type {
  RewriteAlternative,
  RewriteReviewFixture,
  RewriteReviewStage,
} from "../product/evidenceRewriteReviewFixtures";

const REWRITE_INSTRUCTION_LIMIT = 2000;

export interface RewritePanelProps {
  stage: Extract<RewriteReviewStage, "selection" | "whole" | "alternatives">;
  fixture: RewriteReviewFixture;
  instruction: string;
  keepCitations: boolean;
  useSources: boolean;
  selectedAlternativeId: RewriteAlternative["id"];
  onInstructionChange: (value: string) => void;
  onKeepCitationsChange: (value: boolean) => void;
  onUseSourcesChange: (value: boolean) => void;
  onReviewAlternatives: () => void;
  onSelectAlternative: (id: RewriteAlternative["id"]) => void;
  onCompare: (id: RewriteAlternative["id"]) => void;
  onUse: (id: RewriteAlternative["id"], opener: HTMLElement) => void;
  onRevise: () => void;
  onKeepOriginal: () => void;
  onClose: () => void;
  live?: boolean;
}

function AlternativeCard({
  alternative,
  selected,
  onSelect,
  onCompare,
  onUse,
}: {
  alternative: RewriteAlternative;
  selected: boolean;
  onSelect: () => void;
  onCompare: () => void;
  onUse: (opener: HTMLElement) => void;
}) {
  return (
    <article
      className={
        selected
          ? "rewrite-panel__alternative rewrite-panel__alternative--selected"
          : "rewrite-panel__alternative"
      }
      aria-label={alternative.label}
    >
      <header>
        <div>
          <p>{alternative.label}</p>
          {alternative.recommended && <span>Recommended</span>}
        </div>
        <label>
          <input
            type="radio"
            name="rewrite-alternative"
            checked={selected}
            onChange={onSelect}
          />
          Select
        </label>
      </header>
      <p className="rewrite-panel__alternative-text">{alternative.text}</p>
      <div className="rewrite-panel__alternative-meta">
        <span>
          {alternative.wordDelta > 0 ? "+" : ""}
          {alternative.wordDelta} words
        </span>
        <span>{alternative.citations.join(" · ")}</span>
      </div>
      <div className="rewrite-panel__alternative-actions">
        <button type="button" onClick={onCompare}>
          Compare with original
        </button>
        <button
          type="button"
          className="rewrite-panel__primary"
          onClick={(event) => onUse(event.currentTarget)}
        >
          Use this version
        </button>
      </div>
    </article>
  );
}

/** Controlled Page 13 rewrite setup and alternatives presentation. */
export function RewritePanel({
  stage,
  fixture,
  instruction,
  keepCitations,
  useSources,
  selectedAlternativeId,
  onInstructionChange,
  onKeepCitationsChange,
  onUseSourcesChange,
  onReviewAlternatives,
  onSelectAlternative,
  onCompare,
  onUse,
  onRevise,
  onKeepOriginal,
  onClose,
  live = false,
}: RewritePanelProps) {
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();
  const instructionId = useId();
  const errorId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = instruction.trim();
    if (normalized === "") {
      setError("Enter a rewrite instruction.");
      return;
    }
    if (normalized.length > REWRITE_INSTRUCTION_LIMIT) {
      setError(
        `Rewrite instructions must be ${REWRITE_INSTRUCTION_LIMIT} characters or fewer.`,
      );
      return;
    }
    setError(null);
    onReviewAlternatives();
  };

  return (
    <aside className="rewrite-panel" aria-labelledby={titleId}>
      <header className="rewrite-panel__header">
        <div>
          <p className="rewrite-panel__eyebrow">Authoring tools</p>
          <h2 id={titleId}>
            {stage === "alternatives"
              ? "Rewrite alternatives"
              : stage === "whole"
                ? `Rewrite section ${fixture.sectionNumber}`
                : "Rewrite selected passage"}
          </h2>
        </div>
        <button
          type="button"
          className="rewrite-panel__close"
          onClick={onClose}
          aria-label="Close rewrite panel"
        >
          <span aria-hidden="true">×</span>
        </button>
      </header>

      {!live && (
        <p className="rewrite-panel__fixture-note" role="note">
          Review fixture — alternatives demonstrate the planned interaction and
          are not produced or saved by the product.
        </p>
      )}

      {stage === "alternatives" ? (
        <div className="rewrite-panel__alternatives">
          <section aria-labelledby={`${titleId}-original`}>
            <p className="rewrite-panel__label" id={`${titleId}-original`}>
              Original selection
            </p>
            <blockquote>{fixture.selectedText}</blockquote>
          </section>

          {fixture.alternatives.map((alternative) => (
            <AlternativeCard
              key={alternative.id}
              alternative={alternative}
              selected={alternative.id === selectedAlternativeId}
              onSelect={() => onSelectAlternative(alternative.id)}
              onCompare={() => onCompare(alternative.id)}
              onUse={(opener) => onUse(alternative.id, opener)}
            />
          ))}

          <div className="rewrite-panel__footer-actions">
            <button type="button" onClick={onKeepOriginal}>
              Keep original
            </button>
            <button type="button" onClick={onRevise}>
              Revise instruction
            </button>
          </div>
        </div>
      ) : (
        <form className="rewrite-panel__form" onSubmit={submit} noValidate>
          <section aria-labelledby={`${titleId}-scope`}>
            <p className="rewrite-panel__label" id={`${titleId}-scope`}>
              {stage === "whole" ? "Current section" : "Selected text"}
            </p>
            <blockquote>
              {stage === "whole" ? fixture.originalText : fixture.selectedText}
            </blockquote>
          </section>

          <label className="rewrite-panel__label" htmlFor={instructionId}>
            Rewrite instruction
          </label>
          <textarea
            id={instructionId}
            value={instruction}
            rows={6}
            maxLength={REWRITE_INSTRUCTION_LIMIT + 1}
            aria-invalid={error === null ? undefined : true}
            aria-describedby={error === null ? undefined : errorId}
            onChange={(event) => {
              onInstructionChange(event.target.value);
              setError(null);
            }}
          />
          {error !== null && (
            <p className="rewrite-panel__error" role="alert" id={errorId}>
              {error}
            </p>
          )}

          <fieldset>
            <legend>Evidence scope</legend>
            <label>
              <input
                type="checkbox"
                checked={keepCitations}
                onChange={(event) =>
                  onKeepCitationsChange(event.target.checked)
                }
              />
              Keep current citations
            </label>
            <label>
              <input
                type="checkbox"
                checked={useSources}
                onChange={(event) => onUseSourcesChange(event.target.checked)}
              />
              Use available workspace sources
            </label>
          </fieldset>

          <button type="submit" className="rewrite-panel__primary">
            Review alternatives
          </button>
        </form>
      )}
    </aside>
  );
}
