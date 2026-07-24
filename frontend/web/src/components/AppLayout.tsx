import type { ReactNode } from "react";
import { Link } from "react-router-dom";

/** Accessible responsive frame: skip link, header with actions, main region. */
export function AppLayout({
  actions,
  children,
}: {
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to main content
      </a>
      <header className="app-header">
        <Link to="/workspace" className="app-header__brand">
          TrialScribe
        </Link>
        {actions !== undefined && (
          <nav className="app-header__actions" aria-label="Account">
            {actions}
          </nav>
        )}
      </header>
      <main id="main" className="app-main">
        {children}
      </main>
    </div>
  );
}
