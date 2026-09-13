import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { register } from "../api/auth";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/useAuth";
import { BrandLogo } from "../components/BrandLogo";

type AuthMode = "signin" | "signup";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;
const MIN_PASSWORD_LENGTH = 15;

const COPY: Record<
  AuthMode,
  { action: string; pending: string }
> = {
  signin: {
    action: "Sign in",
    pending: "Signing in…",
  },
  signup: {
    action: "Create account",
    pending: "Creating account…",
  },
};

function messageFor(error: unknown, mode: AuthMode): string {
  if (error instanceof ApiError) {
    if (mode === "signin" && error.status === 401) {
      return "Incorrect email or password.";
    }
    if (error.status === 409) {
      return "An account with this email already exists.";
    }
    if (error.status < 500) {
      return error.detail;
    }
  }
  return "Something went wrong. Please try again.";
}

function useCompactAuth(): boolean {
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia("(max-width: 48rem)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return compact;
}

function SignInRailIcon({ path }: { path: string }) {
  return (
    <svg viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true">
      <path d={path} />
    </svg>
  );
}

function SignInEyeIcon({ visible }: { visible: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" />
      <circle cx="12" cy="12" r="2.5" />
      {visible && <path d="m4 4 16 16" />}
    </svg>
  );
}

function SignInCheckIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8 12 2.5 2.5L16 9" />
    </svg>
  );
}

const MOBILE_ARCHIVE_IMAGE =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuCyNJJmD3S1kG-rVq_dU5_Yw0vay0VOEFbBZJN1taCI2dSmLURoa_YRaNZdk5Atq40R19PeSqoT_ZNaAJgH2p4zRvbANffg3MDtw7hocHrllwBjhHR8EEUJ2P1brimm1gimzmkDbo3q0MuP4EvkWCDvcL6bNyxxbahkFU-mmUJmsRApG8FjNfZ47KHSUWOapPyfnnuWZNEOuq2XRXe1jhwo3KPJ5nhEAzpGxxzowoGsCEjcVsvVoMyyYg";

const SIGNUP_WORKSPACE_IMAGE =
  "https://lh3.googleusercontent.com/aida-public/AB6AXuB8pijWJ8SApallbh75XJ-1gJ_D0IQsBHtpAg9F6AFKgt8Li980Mv_XBWdmBRla3a-fWvmCCMtNcgkRFLP16NZljR4nBOQOpu7W0osEJOHDRaEP1MG0tW-avt7-o8AMe7-qSr0QGAal5wpVphX45DVBD_XukdsgGEHyCpXazDSV31iOIUUUY4cyzIYjdwnyLxhSCycf3MdWY1uTEEz98YvhLUYVhB0ZOwzKRT_2_UPTbpFh7In4TbEOMw";

type PasswordFeedback = "empty" | "invalid" | "valid";

function SignupFeedbackIcon({ state }: { state: PasswordFeedback }) {
  if (state === "valid") {
    return (
      <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="7.5" stroke="currentColor" />
        <path
          d="m6.6 10.1 2.1 2.2 4.7-4.8"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" />
      <path
        d={state === "invalid" ? "M10 5.8v5.1m0 2.9v.1" : "M10 8.4v5.1m0-7.4v.1"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SignupAssuranceIcon({
  variant,
}: {
  variant: "access" | "roles" | "history";
}) {
  if (variant === "access") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 2.8 4.8 5.6v5.6c0 4.7 3 8.9 7.2 10 4.2-1.1 7.2-5.3 7.2-10V5.6L12 2.8Z"
          fill="currentColor"
        />
        <path d="M12 5.3v13.4c2.8-1.2 4.8-4.2 4.8-7.5V7.3L12 5.3Z" fill="white" />
      </svg>
    );
  }

  if (variant === "roles") {
    return (
      <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <circle cx="9" cy="7.5" r="3" stroke="currentColor" strokeWidth="1.8" />
        <path
          d="M3.5 18.5v-1.7c0-2.7 2.2-4.8 4.8-4.8h1.4c1 0 1.9.3 2.7.8"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <circle cx="17" cy="16.5" r="2.7" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M17 12.4v1.2m0 5.8v1.2m4.1-4.1h-1.2m-5.8 0h-1.2m7-2.9-.9.8m-4.1 4.2-.9.8m5.9 0-.9-.8m-4.1-4.2-.9-.8"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4.7 8.4A8.2 8.2 0 1 1 4 14"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M4.7 3.8v4.6h4.6M12 7.2v5.1l3.4 2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function AuthPage({ mode }: { mode: AuthMode }) {
  const { status, signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const compactAuth = useCompactAuth();
  const copy = COPY[mode];
  const passwordFeedback: PasswordFeedback =
    password.length === 0
      ? "empty"
      : password.length < MIN_PASSWORD_LENGTH
        ? "invalid"
        : "valid";
  const passwordFeedbackText =
    passwordFeedback === "empty"
      ? `Use at least ${MIN_PASSWORD_LENGTH} characters`
      : passwordFeedback === "invalid"
        ? `${MIN_PASSWORD_LENGTH}+ characters required`
        : "Password strength validated";

  if (status === "authenticated") {
    return <Navigate to="/protocols" replace />;
  }

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!EMAIL_PATTERN.test(email)) {
      setError("Enter a valid email address.");
      return;
    }
    if (mode === "signup" && password.length < MIN_PASSWORD_LENGTH) {
      setError(`Passwords need at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    setPending(true);
    try {
      if (mode === "signup") {
        await register(email, password);
      }
      await signIn(email, password);
      navigate("/protocols", { replace: true });
    } catch (submitError) {
      setError(messageFor(submitError, mode));
    } finally {
      setPending(false);
    }
  };

  if (mode === "signin") {
    return (
      <div className="signin-page">
        <main className="signin-page__auth">
          <BrandLogo className="signin-brand" to="/" />

          <div className="signin-form-wrap">
            <nav className="signin-tabs" aria-label="Authentication">
              <Link
                className="signin-tabs__item signin-tabs__item--active"
                aria-current="page"
                to="/login"
              >
                Sign in
              </Link>
              <Link className="signin-tabs__item" to="/signup">
                Create account
              </Link>
            </nav>

            <section className="signin-form-section" aria-labelledby="signin-title">
              <header className="signin-form-heading">
                <h1
                  className="signin-form-heading__eyebrow"
                  id="signin-title"
                >
                  Welcome back
                </h1>
                <p>
                  <span className="signin-copy--desktop">
                    Continue to your protocol workspaces.
                  </span>
                  <span className="signin-copy--mobile">
                    Continue your clinical documentation research.
                  </span>
                </p>
              </header>

              <form
                className="signin-form"
                onSubmit={onSubmit}
                aria-labelledby="signin-title"
                noValidate
              >
                <div className="signin-field">
                  <label htmlFor="signin-email">Email address</label>
                  <input
                    id="signin-email"
                    aria-label="Email"
                    type="email"
                    name="email"
                    autoComplete="username"
                    placeholder={
                      compactAuth
                        ? "dr.smith@institution.edu"
                        : "you@organization.org"
                    }
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>

                <div className="signin-field">
                  <div className="signin-field__label-row">
                    <label htmlFor="signin-password">Password</label>
                    <button
                      type="button"
                      className="signin-forgot"
                      onClick={() =>
                        setError(
                          "Password recovery is not available yet. Contact your organization administrator.",
                        )
                      }
                    >
                      Forgot?
                    </button>
                  </div>
                  <div className="signin-password">
                    <input
                      id="signin-password"
                      aria-label="Password"
                      type={passwordVisible ? "text" : "password"}
                      name="password"
                      autoComplete="current-password"
                      placeholder={compactAuth ? "••••••••" : undefined}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                    />
                    <button
                      type="button"
                      className="signin-password__toggle"
                      aria-label={
                        passwordVisible ? "Hide password" : "Show password"
                      }
                      onClick={() => setPasswordVisible((value) => !value)}
                    >
                      <span className="signin-password__toggle-text">
                        {passwordVisible ? "Hide" : "Show"}
                      </span>
                      <span className="signin-password__toggle-icon">
                        <SignInEyeIcon visible={passwordVisible} />
                      </span>
                    </button>
                  </div>
                </div>

                {error !== null && (
                  <p className="signin-form__error" role="alert">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  className="signin-submit"
                  disabled={pending}
                >
                  <span>{pending ? "Signing in…" : "Sign in"}</span>
                  {!pending && (
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M5 12h14M14 7l5 5-5 5" />
                    </svg>
                  )}
                </button>
              </form>
            </section>

            <p className="signin-new-account">
              New to TrialScribe?{" "}
              <Link to="/signup">Create an account</Link>
            </p>

            <section className="signin-mobile-archive" aria-hidden="true">
              <p>Intelligent evidence archive</p>
              <div className="signin-mobile-archive__frame">
                <div className="signin-mobile-archive__skeleton">
                  <i />
                  <i />
                  <i />
                  <i />
                  <span />
                </div>
                <div
                  className="signin-mobile-archive__image"
                  style={{ backgroundImage: `url("${MOBILE_ARCHIVE_IMAGE}")` }}
                />
              </div>
            </section>
          </div>

          <footer className="signin-desktop-footer">
            © 2024 TrialScribe Clinical Research • Precision Documentation
          </footer>
        </main>

        <section className="signin-showcase" aria-hidden="true">
          <div className="signin-showcase__texture" />
          <div className="signin-product">
            <aside className="signin-product__rail">
              <span>
                <SignInRailIcon path="M319-250h322v-60H319v60Zm0-170h322v-60H319v60ZM220-80q-24 0-42-18t-18-42v-680q0-24 18-42t42-18h361l219 219v521q0 24-18 42t-42 18H220Zm331-554v-186H220v680h520v-494H551ZM220-820v186-186 680-680Z" />
              </span>
              <span className="is-active">
                <SignInRailIcon path="M160-410v-60h300v60H160Zm0-165v-60h470v60H160Zm0-165v-60h470v60H160Zm360 580v-123l221-220q9-9 20-13t22-4q12 0 23 4.5t20 13.5l37 37q9 9 13 20t4 22q0 11-4.5 22.5T862.09-380L643-160H520Zm300-263-37-37 37 37ZM580-220h38l121-122-18-19-19-18-122 121v38Zm141-141-19-18 37 37-18-19Z" />
              </span>
              <span>
                <SignInRailIcon path="M477-120q-149 0-253-105.5T120-481h60q0 125 86 213t211 88q127 0 215-89t88-216q0-124-89-209.5T477-780q-68 0-127.5 31T246-667h105v60H142v-208h60v106q52-61 123.5-96T477-840q75 0 141 28t115.5 76.5Q783-687 811.5-622T840-482q0 75-28.5 141t-78 115Q684-177 618-148.5T477-120Zm128-197L451-469v-214h60v189l137 134-43 43Z" />
              </span>
              <span>
                <SignInRailIcon path="m388-80-20-126q-19-7-40-19t-37-25l-118 54-93-164 108-79q-2-9-2.5-20.5T185-480q0-9 .5-20.5T188-521L80-600l93-164 118 54q16-13 37-25t40-18l20-127h184l20 126q19 7 40.5 18.5T669-710l118-54 93 164-108 77q2 10 2.5 21.5t.5 21.5q0 10-.5 21t-2.5 21l108 78-93 164-118-54q-16 13-36.5 25.5T592-206L572-80H388Zm48-60h88l14-112q33-8 62.5-25t53.5-41l106 46 40-72-94-69q4-17 6.5-33.5T715-480q0-17-2-33.5t-7-33.5l94-69-40-72-106 46q-23-26-52-43.5T538-708l-14-112h-88l-14 112q-34 7-63.5 24T306-642l-106-46-40 72 94 69q-4 17-6.5 33.5T245-480q0 17 2.5 33.5T254-413l-94 69 40 72 106-46q24 24 53.5 41t62.5 25l14 112Zm44-210q54 0 92-38t38-92q0-54-38-92t-92-38q-54 0-92 38t-38 92q0 54 38 92t92 38Zm0-130Z" />
              </span>
            </aside>
            <div className="signin-product__editor">
              <header>
                <div>
                  <span>ICH M11 · Revision 7</span>
                  <i>/</i>
                  <strong>5 · Trial Population</strong>
                </div>
                <div className="signin-product__session">
                  <i />
                  <span>Active session</span>
                </div>
              </header>
              <article>
                <h2>5 · Trial Population</h2>
                <p>
                  The inclusion criteria for the phase 3 study will focus on
                  adults aged 18 to 75 with confirmed diagnosis of chronic
                  metabolic dysfunction.{" "}
                  <mark>
                    Participants must exhibit a baseline HbA1c between 7.0%
                    and 10.5% <sup>[S1]</sup>
                  </mark>{" "}
                  to ensure a consistent baseline across multi-center sites.
                </p>
                <p>
                  Exclusion criteria include prior exposure to targeted GLP-1
                  therapies within 90 days of screening.
                </p>
              </article>
            </div>
            <aside className="signin-product__evidence">
              <header>Evidence inspector</header>
              <div>
                <span>
                  <strong>[S1] Source detail</strong>
                  <i>↗</i>
                </span>
                <blockquote>
                  “Subject inclusion necessitates a glycemic window of
                  7–10.5% to maintain power.”
                </blockquote>
                <small>Ref: Study-Paradigm-2023</small>
              </div>
            </aside>
          </div>

          <div className="signin-showcase__details">
            <div>
              <h2>Every claim connected to its evidence.</h2>
              <ul>
                <li>
                  <SignInCheckIcon />
                  Section-by-section M11 authoring
                </li>
                <li>
                  <SignInCheckIcon />
                  Traceable citations and source passages
                </li>
                <li>
                  <SignInCheckIcon />
                  Durable revisions inside your organization
                </li>
              </ul>
            </div>
            <div className="signin-workspace-card">
              <span>Current workspace</span>
              <strong>AURORA-301</strong>
              <div>
                <i />
              </div>
              <p>
                <span>8 of 14 sections complete</span>
                <strong>57%</strong>
              </p>
            </div>
          </div>
        </section>

        <footer className="signin-mobile-footer">
          <nav aria-label="Legal">
            <a href="#privacy">Privacy</a>
            <a href="#terms">Terms</a>
            <a href="#support">Support</a>
          </nav>
          <p>© 2024 TrialScribe Clinical Research Systems</p>
        </footer>
      </div>
    );
  }

  return (
    <div className={`signup-page signup-page--password-${passwordFeedback}`}>
      <main className="signup-page__form-column">
        <BrandLogo className="signup-brand" to="/" />

        <div className="signup-form-stage">
          <div className="signup-form-wrap">
            <nav className="signup-tabs" aria-label="Authentication">
              <Link className="signup-tabs__item" to="/login">
                Sign in
              </Link>
              <Link
                className="signup-tabs__item signup-tabs__item--active"
                aria-current="page"
                to="/signup"
              >
                Create account
              </Link>
            </nav>

            <header className="signup-heading">
              <h1 className="signup-heading__eyebrow" id="signup-title">
                Get started
              </h1>
              <p>
                Use your work email. You will create or join an organization
                next.
              </p>
            </header>

            <form
              className="signup-form"
              onSubmit={onSubmit}
              aria-labelledby="signup-title"
              noValidate
            >
              <div className="signup-field">
                <label htmlFor="signup-email">Work email</label>
                <input
                  id="signup-email"
                  aria-label="Email"
                  type="email"
                  name="email"
                  autoComplete="email"
                  placeholder={
                    compactAuth
                      ? "name@organization.edu"
                      : "you@organization.org"
                  }
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>

              <div className="signup-field">
                <div className="signup-field__label-row">
                  <label htmlFor="signup-password">Password</label>
                </div>
                <div className="signup-password">
                  <input
                    id="signup-password"
                    aria-label="Password"
                    type={passwordVisible ? "text" : "password"}
                    name="password"
                    autoComplete="new-password"
                    aria-describedby="signup-password-feedback"
                    placeholder="•••••••••••••••"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="signup-password__toggle"
                    aria-label={
                      passwordVisible ? "Hide password" : "Show password"
                    }
                    onClick={() => setPasswordVisible((value) => !value)}
                  >
                    <SignInEyeIcon visible={passwordVisible} />
                    <span>{passwordVisible ? "Hide" : "Show"}</span>
                  </button>
                </div>
                <div className="signup-password__status">
                  <p className="signup-password__desktop-requirement">
                    Use at least {MIN_PASSWORD_LENGTH} characters
                  </p>
                  <div className="signup-password__meter" aria-hidden="true">
                    <span
                      style={{
                        width: `${Math.min(
                          (password.length / MIN_PASSWORD_LENGTH) * 100,
                          100,
                        )}%`,
                      }}
                    />
                  </div>
                  <p
                    id="signup-password-feedback"
                    className="signup-password__feedback"
                    aria-live="polite"
                  >
                    <SignupFeedbackIcon state={passwordFeedback} />
                    <span>{passwordFeedbackText}</span>
                  </p>
                </div>
              </div>

              {error !== null && (
                <p className="signup-form__error" role="alert">
                  {error}
                </p>
              )}

              <button
                type="submit"
                className="signup-submit"
                disabled={pending}
              >
                {pending ? copy.pending : copy.action}
              </button>

              <p className="signup-existing-account">
                Already have an account? <Link to="/login">Sign in</Link>
              </p>
            </form>

            <section
              className="signup-mobile-next"
              aria-labelledby="signup-next-title"
            >
              <h2 id="signup-next-title">What happens next</h2>
              <ol>
                <li>
                  <span>1</span>
                  <p>
                    <strong>Create account</strong>
                    Establish your researcher identity.
                  </p>
                </li>
                <li>
                  <span>2</span>
                  <p>
                    <strong>Join organization</strong>
                    Verify academic affiliation via email.
                  </p>
                </li>
                <li>
                  <span>3</span>
                  <p>
                    <strong>Open protocol workspace</strong>
                    Start drafting your first clinical study.
                  </p>
                </li>
              </ol>
            </section>
          </div>
        </div>

        <footer className="signup-desktop-footer">
          <a href="#privacy">Privacy Policy</a>
          <a href="#terms">Terms of Service</a>
        </footer>
      </main>

      <aside className="signup-context" aria-labelledby="signup-context-title">
        <div className="signup-context__inner">
          <h2 id="signup-context-title">From account to first protocol.</h2>

          <ol className="signup-sequence">
            <li className="signup-sequence__item signup-sequence__item--active">
              <span>1</span>
              <div>
                <h3>Account</h3>
                <p>
                  Establish your academic credentials and secure your personal
                  researcher profile.
                </p>
              </div>
            </li>
            <li className="signup-sequence__item">
              <span>2</span>
              <div>
                <h3>Organization</h3>
                <p>
                  Join an existing lab or create a new institutional workspace
                  for your team.
                </p>
              </div>
            </li>
            <li className="signup-sequence__item">
              <span>3</span>
              <div>
                <h3>Protocol</h3>
                <p>
                  Start drafting your first clinical study protocol using our
                  structured editor.
                </p>
              </div>
            </li>
          </ol>

          <figure className="signup-workspace-preview">
            <img src={SIGNUP_WORKSPACE_IMAGE} alt="" draggable="false" />
            <figcaption>
              <span>
                <i />
                Live workspace preview
              </span>
              <em>Configuring: Mayo Clinic Research Group</em>
            </figcaption>
          </figure>

          <section
            className="signup-assurances"
            aria-label="Workspace assurances"
          >
            <article>
              <SignupAssuranceIcon variant="access" />
              <div>
                <h3>Organization-scoped access</h3>
                <p>
                  Your data stays within your institution&apos;s sovereign
                  digital boundary.
                </p>
              </div>
            </article>
            <article>
              <SignupAssuranceIcon variant="roles" />
              <div>
                <h3>Role-based workspace permissions</h3>
                <p>
                  Granular control for PIs, researchers, and regulatory
                  auditors.
                </p>
              </div>
            </article>
            <article>
              <SignupAssuranceIcon variant="history" />
              <div>
                <h3>Durable protocol and revision history</h3>
                <p>
                  Immutable logs of every change for total regulatory
                  compliance.
                </p>
              </div>
            </article>
          </section>
        </div>
      </aside>

      <footer className="signup-mobile-footer">
        <BrandLogo ariaLabel="TrialScribe" />
        <p>
          © 2024 TrialScribe. Academic excellence in clinical documentation.
        </p>
        <nav aria-label="Legal and support">
          <a href="#privacy">Privacy</a>
          <a href="#security">Security</a>
          <a href="#support">Support</a>
        </nav>
      </footer>
    </div>
  );
}
