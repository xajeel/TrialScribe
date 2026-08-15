import { splitCitedText } from "../citations/citeMarkers";

/** Render stored section prose with each canonical citation as a button. */
export function CitedSectionText({
  content,
  onInspect,
}: {
  content: string;
  onInspect: (id: string) => void;
}) {
  return (
    <>
      {splitCitedText(content).map((part, index) =>
        part.type === "text" ? (
          <span key={`text-${index}`}>{part.value}</span>
        ) : (
          <button
            key={`cite-${part.id}-${index}`}
            type="button"
            className="cited-section__citation"
            aria-label={`Inspect citation ${part.id}`}
            onClick={() => onInspect(part.id)}
          >
            [cite]
          </button>
        ),
      )}
    </>
  );
}
