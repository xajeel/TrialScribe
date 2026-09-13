import { BrandLogo } from "../components/BrandLogo";

function SessionDocumentIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M7.5 3.5h6.8l3.2 3.2v13.8h-10Z" />
      <path d="M14 3.8v3.4h3.2M10 11h5M10 14.5h5" />
      <path d="m10.2 18 1.3 1.3 2.7-2.9" />
    </svg>
  );
}

function SessionLockIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="4.5" y="8.5" width="11" height="8" rx="1.5" />
      <path d="M7 8.5V6.4a3 3 0 0 1 6 0v2.1M10 11.7v1.8" />
    </svg>
  );
}

export function SessionCheckPage() {
  return (
    <div className="session-check" aria-busy="true">
      <header className="session-check__header">
        <BrandLogo className="session-check__brand" to="/" />

        <span className="session-check__header-status">
          <SessionLockIcon />
          <span>Secure workspace</span>
        </span>
      </header>

      <main className="session-check__main">
        <div className="session-check__stage">
          <section
            className="session-check__card"
            aria-labelledby="session-check-title"
          >
            <span className="session-check__document-mark">
              <SessionDocumentIcon />
            </span>
            <p className="session-check__eyebrow">Protected workspace</p>
            <h1 id="session-check-title">Checking your session…</h1>
            <p className="session-check__description">
              Restoring secure access to your protocol workspaces.
            </p>

            <div
              className="session-check__progress"
              role="progressbar"
              aria-label="Session verification in progress"
            >
              <span />
            </div>

            <p
              className="session-check__status"
              role="status"
              aria-live="polite"
            >
              <SessionLockIcon />
              <span>Verifying credentials</span>
            </p>
          </section>

          <p className="session-check__note">
            This usually takes only a moment.
          </p>
        </div>
      </main>
    </div>
  );
}
