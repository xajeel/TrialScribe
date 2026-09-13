/** Standard loading, empty, and error+retry states shared across screens. */

export function LoadingState({ label }: { label: string }) {
  return (
    <p className="async-state" role="status" aria-live="polite">
      {label}
    </p>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="async-state async-state--empty">
      <p className="async-state__title">{title}</p>
      <p className="async-state__description">{description}</p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="async-state async-state--error" role="alert">
      <p className="async-state__title">{message}</p>
      <button type="button" className="retry-button" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
