import { Link } from "react-router-dom";

import { ProductPreview } from "../components/ProductPreview";
import { useAuth } from "../auth/useAuth";

const FEATURES = [
  {
    title: "Durable conversations",
    description:
      "Every exchange is stored with its full history, so nothing lives only in a browser tab.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <path d="M8 9h8M8 13h5" />
      </svg>
    ),
  },
  {
    title: "Built for organizations",
    description:
      "Invite your team, assign roles, and keep every workspace scoped to the right people.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    title: "Secure by default",
    description:
      "Short-lived tokens, httpOnly session cookies, and CSRF protection out of the box.",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    ),
  },
];

const STEPS = [
  {
    number: "01",
    title: "Create your account",
    description: "Sign up with your work email and set a strong password.",
  },
  {
    number: "02",
    title: "Set up your organization",
    description:
      "Create or join an organization and give each teammate the right role.",
  },
  {
    number: "03",
    title: "Ask and keep the record",
    description:
      "Every conversation stays durable, searchable, and ready for review.",
  },
];

const SECURITY_POINTS = [
  "Access tokens live in memory only and expire in minutes",
  "Sessions persist in httpOnly cookies that scripts cannot read",
  "State-changing requests carry cross-site request forgery proof",
  "Organization roles decide who sees which workspace",
];

export function LandingPage() {
  const { status } = useAuth();
  const authenticated = status === "authenticated";
  const primaryTo = authenticated ? "/workspace" : "/signup";
  const primaryLabel = authenticated
    ? "Open your workspace"
    : "Create your account";

  return (
    <div className="landing">
      <header className="landing__nav">
        <div className="landing__inner landing__nav-row">
          <Link to="/" className="brand">
            TrialScribe
          </Link>
          <nav className="landing__nav-links" aria-label="Primary">
            {authenticated ? (
              <Link className="button button--primary" to="/workspace">
                Open workspace
              </Link>
            ) : (
              <>
                <Link className="landing__signin" to="/login">
                  Sign in
                </Link>
                <Link className="button button--primary" to="/signup">
                  Get started
                </Link>
              </>
            )}
          </nav>
        </div>
      </header>

      <main>
        <section className="landing__hero landing__inner">
          <div className="landing__hero-copy">
            <p className="eyebrow">Clinical research workspace</p>
            <h1 className="display">Ask once. Keep the answer on record.</h1>
            <p className="landing__lede">
              TrialScribe gives clinical research teams durable AI
              conversations that stay scoped to your organization, secured by
              default, and ready to audit.
            </p>
            <div className="landing__cta">
              <Link className="button button--primary button--lg" to={primaryTo}>
                {primaryLabel}
              </Link>
              {!authenticated && (
                <Link className="button button--ghost button--lg" to="/login">
                  Sign in
                </Link>
              )}
            </div>
          </div>
          <div className="landing__hero-visual">
            <ProductPreview />
          </div>
        </section>

        <section
          className="landing__section landing__inner"
          aria-labelledby="how-title"
        >
          <div className="section-head">
            <p className="eyebrow">How it works</p>
            <h2 className="display section-head__title" id="how-title">
              Up and running in minutes
            </h2>
          </div>
          <div className="how-grid">
            {STEPS.map((step) => (
              <article key={step.number} className="how-step">
                <span className="how-step__number display" aria-hidden="true">
                  {step.number}
                </span>
                <h3 className="how-step__title">{step.title}</h3>
                <p className="how-step__description">{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section
          className="landing__section landing__inner"
          aria-labelledby="features-title"
        >
          <div className="section-head">
            <p className="eyebrow">Why TrialScribe</p>
            <h2 className="display section-head__title" id="features-title">
              Built for regulated research
            </h2>
          </div>
          <div className="landing__features">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="feature">
                <span className="feature__icon">{feature.icon}</span>
                <h3 className="feature__title">{feature.title}</h3>
                <p className="feature__description">{feature.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section
          className="landing__section landing__inner landing__security"
          aria-labelledby="security-title"
        >
          <div>
            <p className="eyebrow">Security</p>
            <h2 className="display section-head__title" id="security-title">
              Safe by design
            </h2>
            <p className="landing__lede">
              Session handling follows the strictest browser practices, and
              every workspace is scoped to an organization role.
            </p>
          </div>
          <ul className="security-list">
            {SECURITY_POINTS.map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </section>

        <section
          className="landing__inner landing__cta-section"
          aria-label="Get started"
        >
          <div className="cta-band">
            <h2 className="display cta-band__title">
              Start keeping every answer on record.
            </h2>
            <p className="cta-band__text">
              Create your account and set up your organization in minutes.
            </p>
            <Link className="button button--inverse button--lg" to={primaryTo}>
              {primaryLabel}
            </Link>
          </div>
        </section>
      </main>

      <footer className="landing__footer">
        <div className="landing__inner landing__footer-row">
          <div>
            <span className="brand">TrialScribe</span>
            <p className="landing__footer-tag">
              Durable AI conversations for clinical research teams.
            </p>
          </div>
          <nav className="landing__footer-links" aria-label="Footer">
            <Link to="/login">Sign in</Link>
            <Link to="/signup">Create account</Link>
          </nav>
        </div>
        <div className="landing__inner landing__footer-copy">
          © 2026 TrialScribe
        </div>
      </footer>
    </div>
  );
}
