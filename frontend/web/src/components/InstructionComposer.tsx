import { useId, useState, type FormEvent } from "react";

import { INSTRUCTION_LIMIT } from "../workspace/useProtocolOverview";

const COUNTER_FROM = 3600;
const BLANK = "Enter an instruction.";
const TOO_LONG = `Instructions must be ${INSTRUCTION_LIMIT} characters or fewer.`;

/** Adds one durable writing instruction to the protocol workspace. */
export function InstructionComposer({
  pending,
  disabled = false,
  onSave,
}: {
  pending: boolean;
  disabled?: boolean;
  onSave: (text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const fieldId = useId();
  const alertId = useId();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (pending || disabled) {
      return;
    }
    const normalized = text.trim();
    if (normalized === "") {
      setError(BLANK);
      return;
    }
    if (normalized.length > INSTRUCTION_LIMIT) {
      setError(TOO_LONG);
      return;
    }
    setError(null);
    // The typed text is cleared only once the save has actually succeeded, so a
    // failed request never loses what the user wrote.
    if (await onSave(normalized)) {
      setText("");
    }
  };

  return (
    <form className="instruction-composer" onSubmit={submit} noValidate>
      <label htmlFor={fieldId}>Add a workspace instruction</label>
      <textarea
        id={fieldId}
        value={text}
        rows={4}
        disabled={pending || disabled}
        aria-invalid={error === null ? undefined : true}
        aria-describedby={error === null ? undefined : alertId}
        placeholder="Define global tone, reference requirements, or structural constraints…"
        onChange={(event) => {
          setText(event.target.value);
          setError(null);
        }}
      />
      {text.length >= COUNTER_FROM && (
        <p className="instruction-composer__counter" aria-live="polite">
          {text.length} of {INSTRUCTION_LIMIT} characters
        </p>
      )}
      {error !== null && (
        <p className="instruction-composer__alert" id={alertId} role="alert">
          {error}
        </p>
      )}
      <div className="instruction-composer__actions">
        <button type="submit" disabled={pending || disabled}>
          {pending ? "Saving instruction…" : "Save instruction"}
        </button>
      </div>
    </form>
  );
}
