import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../auth/useAuth";
import { BrandLogo } from "../components/BrandLogo";
import { ProductPreview } from "../components/ProductPreview";

type LandingIconName =
  | "check"
  | "framework"
  | "history"
  | "link"
  | "lock"
  | "shield"
  | "review"
  | "source"
  | "upload"
  | "users"
  | "verify";

const ICON_PATHS: Record<LandingIconName, ReactNode> = {
  check: <path d="m5 12 4 4L19 6" />,
  framework: (
    <>
      <path d="m9 3-2 8M15 3l2 8M8 10h8M12 10v10" />
      <path d="M7 21h10M5 15l7-5 7 5" />
    </>
  ),
  history: (
    <>
      <path d="M4 12a8 8 0 1 0 2.3-5.65L4 8.65" />
      <path d="M4 4v4.65h4.65M12 7.5V12l3 2" />
    </>
  ),
  link: (
    <>
      <path d="M9.5 14.5 14.5 9.5" />
      <path d="M7.8 16.2 6.4 17.6a3.1 3.1 0 0 1-4.4-4.4l3.2-3.2a3.1 3.1 0 0 1 4.4 0" />
      <path d="m16.2 7.8 1.4-1.4a3.1 3.1 0 0 1 4.4 4.4L18.8 14a3.1 3.1 0 0 1-4.4 0" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="10" width="14" height="10" rx="2" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2" />
    </>
  ),
  review: (
    <>
      <path d="M5 3.5h11l3 3v14H5z" />
      <path d="M16 3.5v3h3M8.5 11h7M8.5 15h4" />
      <path d="m14 16.5 1.4 1.4 3.1-3.1" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 19 6v5c0 4.6-2.7 8.1-7 10-4.3-1.9-7-5.4-7-10V6z" />
      <path d="m9 12 2 2 4-5" />
    </>
  ),
  source: (
    <>
      <path d="M4 5.5h7.5v13H4zM12.5 5.5H20v13h-7.5" />
      <path d="M7 9h2M7 12h2M15 9h2M15 12h2" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15V4M8 8l4-4 4 4" />
      <path d="M5 14v5.5h14V14" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19v-1.5A4.5 4.5 0 0 1 8 13h2a4.5 4.5 0 0 1 4.5 4.5V19" />
      <path d="M15 5.4a3 3 0 0 1 0 5.2M17 13.4a4.5 4.5 0 0 1 3.5 4.4V19" />
    </>
  ),
  verify: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2" />
      <path d="M8 9h5M8 13h3M14 14l1.5 1.5L19 12" />
    </>
  ),
};

function LandingIcon({ name }: { name: LandingIconName }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

const WORKFLOW = [
  {
    number: "01",
    title: "Bring context",
    description:
      "Upload Investigator Brochures, earlier phase reports, and lab data as your ground truth.",
    visual: "upload" as const,
  },
  {
    number: "02",
    title: "Draft",
    description:
      "Write within the ICH M11 framework with auto-linking to your source evidence material.",
    visual: "document" as const,
  },
  {
    number: "03",
    title: "Verify",
    description:
      "Run automated compliance checks against template requirements and internal SOPs.",
    visual: "verify" as const,
  },
  {
    number: "04",
    title: "Review",
    description:
      "Invite reviewers to a locked, traceable environment for final sign-off and export.",
    visual: "review" as const,
  },
];

const TRUST_ITEMS = [
  {
    icon: "users" as const,
    title: "Organization-scoped access",
    description:
      "Granular permissions ensure that sensitive protocols and evidence are only visible to authorized research personnel.",
  },
  {
    icon: "source" as const,
    title: "Source provenance",
    description:
      "Every file uploaded is cryptographically hashed to ensure its integrity remains unchanged throughout the authoring process.",
  },
  {
    icon: "lock" as const,
    title: "Draft/Done states",
    description:
      "Lock individual sections for finality, preventing accidental edits once a chapter has been formally approved.",
  },
  {
    icon: "history" as const,
    title: "Revision history",
    description:
      "Comprehensive versioning for every ICH section, allowing you to compare drafts and revert changes with one click.",
  },
];

export function LandingPage() {
  const { status } = useAuth();
  const authenticated = status === "authenticated";
  const primaryTo = authenticated ? "/protocols" : "/signup";
  const primaryLabel = authenticated ? "Open workspace" : "Start a protocol";

  return (
    <div className="landing">
      <header className="landing-nav">
        <div className="landing-container landing-nav__inner">
          <BrandLogo to="/" />

          <nav className="landing-nav__sections" aria-label="On this page">
            <a className="landing-nav__section landing-nav__section--active" href="#product">
              Product
            </a>
            <a className="landing-nav__section" href="#workflow">
              Workflow
            </a>
            <a className="landing-nav__section" href="#evidence">
              Evidence
            </a>
            <a className="landing-nav__section" href="#security">
              Security
            </a>
          </nav>

          <nav className="landing-nav__account" aria-label="Account">
            {!authenticated && (
              <Link className="landing-nav__signin" to="/login">
                Sign in
              </Link>
            )}
            <Link className="landing-button landing-button--primary landing-button--small" to={primaryTo}>
              {primaryLabel}
            </Link>
          </nav>
        </div>
      </header>

      <main>
        <section className="landing-hero landing-container" id="product">
          <div className="landing-hero__copy">
            <p className="landing-kicker">ICH M11 protocol authoring</p>
            <h1>Draft a protocol your reviewers can trace.</h1>
            <p className="landing-hero__lede">
              TrialScribe bridges the gap between source evidence and
              regulatory submissions with an academic-grade authoring
              environment.
            </p>
            <div className="landing-hero__actions">
              <Link className="landing-button landing-button--primary" to={primaryTo}>
                {primaryLabel}
              </Link>
              <a className="landing-button landing-button--secondary" href="#workflow">
                Explore the workflow
              </a>
            </div>
            <p className="landing-hero__assurance">
              <LandingIcon name="shield" />
              Validated for GxP environments &amp; SOC2 Type II compliant
            </p>
          </div>

          <div className="landing-hero__preview">
            <ProductPreview variant="protocol" />
          </div>
        </section>

        <section className="landing-value-strip" aria-label="Product highlights">
          <div className="landing-container landing-value-strip__grid">
            <div className="landing-value">
              <LandingIcon name="framework" />
              <span>14-section ICH M11 workspace</span>
            </div>
            <div className="landing-value">
              <LandingIcon name="link" />
              <span>Citation-to-passage traceability</span>
            </div>
            <div className="landing-value">
              <LandingIcon name="history" />
              <span>Immutable section revisions</span>
            </div>
          </div>
        </section>

        <section className="landing-workflow landing-container" id="workflow">
          <header className="landing-section-heading">
            <p className="landing-kicker">From evidence to protocol</p>
            <h2>A disciplined workflow for regulated writing.</h2>
          </header>

          <div className="landing-workflow__grid">
            {WORKFLOW.map((step) => (
              <article className="landing-workflow-card" key={step.number}>
                <div className={`landing-workflow-card__visual landing-workflow-card__visual--${step.visual}`}>
                  {step.visual === "document" ? (
                    <span className="landing-workflow-card__lines" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                  ) : (
                    <LandingIcon name={step.visual} />
                  )}
                </div>
                <p className="landing-workflow-card__number">{step.number}</p>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-evidence" id="evidence">
          <div className="landing-container landing-evidence__grid">
            <div className="landing-evidence-demo" aria-hidden="true">
              <div className="landing-evidence-demo__editor">
                <span>Protocol editor</span>
                <p>
                  …dosage shall not exceed 10mg/kg daily{" "}
                  <mark>[S3, p. 14]</mark> to ensure renal safety parameters
                  remain within baseline limits…
                </p>
              </div>
              <div className="landing-evidence-demo__inspector">
                <span className="landing-evidence-demo__label">
                  <LandingIcon name="verify" />
                  Evidence inspector
                </span>
                <div className="landing-evidence-demo__source">
                  <strong>investigator_brochure_v8.pdf</strong>
                  <small>Page 14 · Paragraph 2</small>
                  <blockquote>
                    “Renal toxicity was observed in preclinical models at
                    doses exceeding 15mg/kg, suggesting a 10mg/kg threshold
                    for human safety.”
                  </blockquote>
                </div>
              </div>
            </div>

            <div className="landing-evidence__copy">
              <h2>A citation matters only when a reviewer can verify it.</h2>
              <p>
                Every claim in your protocol is tethered to its source.
                Reviewers don&apos;t need to hunt through a dozen PDFs—they
                simply click a citation to see the exact paragraph in the
                inspector.
              </p>
              <ul>
                <li>
                  <LandingIcon name="check" />
                  Eliminate transcription errors between documents
                </li>
                <li>
                  <LandingIcon name="check" />
                  Accelerate internal and regulatory review cycles
                </li>
                <li>
                  <LandingIcon name="check" />
                  Maintain a complete audit trail of every source document
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section className="landing-trust" id="security">
          <div className="landing-container">
            <header className="landing-trust__heading">
              <div>
                <h2>Built for work that must withstand review.</h2>
                <p>
                  Security and auditability are not features; they are the
                  foundation of TrialScribe.
                </p>
              </div>
              <a className="landing-button landing-button--secondary" href="#trust-capabilities">
                View Compliance Center
              </a>
            </header>

            <div className="landing-trust__grid" id="trust-capabilities">
              {TRUST_ITEMS.map((item) => (
                <article key={item.title}>
                  <LandingIcon name={item.icon} />
                  <h3>{item.title}</h3>
                  <p>{item.description}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="landing-final">
          <div className="landing-container">
            <div className="landing-final__frame">
              <h2>Start with the evidence. Finish with a protocol.</h2>
              <div className="landing-final__actions">
                <Link className="landing-button landing-button--primary" to={primaryTo}>
                  {authenticated ? "Open workspace" : "Create account"}
                </Link>
                {!authenticated && (
                  <Link className="landing-button landing-button--secondary" to="/login">
                    Sign in
                  </Link>
                )}
              </div>
              <p>
                Free trial includes full ICH M11 template access and 500MB of
                evidence storage.
              </p>
            </div>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-container landing-footer__inner">
          <div className="landing-footer__brand">
            <BrandLogo ariaLabel="TrialScribe" />
            <p>
              Academic excellence in clinical documentation. Precision
              authoring for modern research.
            </p>
            <small>© 2024 TrialScribe. All rights reserved.</small>
          </div>

          <div className="landing-footer__links">
            <nav aria-label="Platform">
              <span>Platform</span>
              <a href="#product">Product</a>
              <a href="#workflow">Workflow</a>
              <a href="#security">Security</a>
            </nav>
            <nav aria-label="Account">
              <span>Account</span>
              <Link to="/login">Sign in</Link>
              <Link to="/signup">Create account</Link>
              <Link to="/signup">Enterprise</Link>
            </nav>
          </div>
        </div>
      </footer>
    </div>
  );
}
