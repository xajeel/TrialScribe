import { AccountMenu } from "../components/AccountMenu";
import { BrandLogo } from "../components/BrandLogo";
import { OrganizationOnboarding } from "../components/OrganizationOnboarding";

function CheckIcon() {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="m5.5 10.2 2.8 2.8 6.2-6.2" />
    </svg>
  );
}

function BenefitIcon({
  variant,
}: {
  variant: "isolation" | "roles" | "shared";
}) {
  if (variant === "isolation") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 2.8 4.8 5.6v5.5c0 4.7 3 8.9 7.2 10.1 4.2-1.2 7.2-5.4 7.2-10.1V5.6L12 2.8Z"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinejoin="round"
        />
        <path
          d="M12 6v11.7"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (variant === "roles") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.7" />
        <path
          d="M3.5 19v-1.2A4.8 4.8 0 0 1 8.3 13h1.4c1.7 0 3.2.9 4 2.2M17.5 7.5v7M14 11h7"
          stroke="currentColor"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="6" cy="12" r="2.5" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="18" cy="6" r="2.5" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="18" cy="18" r="2.5" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="m8.3 10.8 7.4-3.6M8.3 13.2l7.4 3.6"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}

const ROLES = [
  {
    name: "Owner",
    description: "Manages organization access and invitations.",
  },
  {
    name: "Admin",
    description: "Can invite members and work across authorized protocols.",
  },
  {
    name: "Member",
    description: "Works inside assigned organization protocols.",
  },
] as const;

const BENEFITS = [
  {
    icon: "isolation" as const,
    title: "Isolated protocol data",
    description:
      "Keeps protocol records and evidence within one organization.",
  },
  {
    icon: "roles" as const,
    title: "Role-based access",
    description:
      "Controls what owners, admins, and members can manage.",
  },
  {
    icon: "shared" as const,
    title: "Shared evidence and workspaces",
    description: "Keeps sources, drafts, and revisions together for the team.",
  },
] as const;

export function OrganizationSetupPage({
  review = false,
}: {
  review?: boolean;
} = {}) {
  return (
    <div className="organization-setup">
      <a className="organization-setup__skip" href="#organization-setup-main">
        Skip to main content
      </a>

      <header className="organization-setup__header">
        <div className="organization-setup__header-inner">
          <BrandLogo
            className="organization-setup__brand"
            to={review ? "/" : "/protocols"}
            ariaLabel={review ? "TrialScribe home" : "TrialScribe protocols"}
          />
          {review ? (
            <span
              className="organization-setup__review-avatar"
              aria-label="Review account MC"
            >
              MC
            </span>
          ) : (
            <AccountMenu />
          )}
        </div>
      </header>

      <main
        id="organization-setup-main"
        className="organization-setup__main"
      >
        <nav
          className="organization-setup__progress"
          aria-label="Setup progress"
        >
          <ol>
            <li className="organization-setup__step organization-setup__step--done">
              <span className="organization-setup__step-marker">
                <CheckIcon />
              </span>
              <span>Account</span>
            </li>
            <li className="organization-setup__step-rule" aria-hidden="true" />
            <li
              className="organization-setup__step organization-setup__step--current"
              aria-current="step"
            >
              <span className="organization-setup__step-marker">2</span>
              <span>Organization</span>
            </li>
            <li className="organization-setup__step-rule" aria-hidden="true" />
            <li className="organization-setup__step">
              <span className="organization-setup__step-marker">3</span>
              <span>First protocol</span>
            </li>
          </ol>
        </nav>

        <div className="organization-setup__layout">
          <aside className="organization-setup__introduction">
            <p className="organization-setup__eyebrow">Workspace setup</p>
            <h1>Where will your protocol work live?</h1>
            <p className="organization-setup__lede">
              Organizations keep protocol workspaces, source documents,
              revisions, and access permissions together.
            </p>
            <p className="organization-setup__privacy">
              Only members of an organization can access its protocol
              workspaces.
            </p>

            <dl className="organization-setup__roles">
              {ROLES.map((role) => (
                <div key={role.name}>
                  <dt>{role.name}</dt>
                  <dd>{role.description}</dd>
                </div>
              ))}
            </dl>
          </aside>

          <OrganizationOnboarding review={review} />
        </div>

        <section
          className="organization-setup__benefits"
          aria-labelledby="organization-benefits-title"
        >
          <h2 id="organization-benefits-title">Why organizations?</h2>
          <div className="organization-setup__benefit-grid">
            {BENEFITS.map((benefit) => (
              <article key={benefit.title}>
                <span className="organization-setup__benefit-icon">
                  <BenefitIcon variant={benefit.icon} />
                </span>
                <div>
                  <h3>{benefit.title}</h3>
                  <p>{benefit.description}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
