import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { register } from "../api/auth";
import { ApiError } from "../api/client";
import { ProductPreview } from "../components/ProductPreview";
import { useAuth } from "../auth/useAuth";

type AuthMode = "signin" | "signup";

const EMAIL_PATTERN = /^\S+@\S+\.\S+$/;
const MIN_PASSWORD_LENGTH = 15;

const COPY: Record<
  AuthMode,
  { eyebrow: string; title: string; action: string; pending: string }
> = {
  signin: {
    eyebrow: "Welcome back",
    title: "Sign in to TrialScribe",
    action: "Sign in",
    pending: "Signing in…",
  },
  signup: {
    eyebrow: "Get started",
    title: "Create your account",
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

export function AuthPage({ mode }: { mode: AuthMode }) {
  const { status, signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = COPY[mode];

  if (status === "authenticated") {
    return <Navigate to="/workspace" replace />;
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
      navigate("/workspace", { replace: true });
    } catch (submitError) {
      setError(messageFor(submitError, mode));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="auth">
      <div className="auth__form-col">
        <Link to="/" className="brand">
          TrialScribe
        </Link>
        <div className="auth__form-wrap">
          <nav className="auth__tabs" aria-label="Authentication">
            <Link
              className={
                mode === "signin" ? "auth__tab auth__tab--active" : "auth__tab"
              }
              aria-current={mode === "signin" ? "page" : undefined}
              to="/login"
            >
              Sign in
            </Link>
            <Link
              className={
                mode === "signup" ? "auth__tab auth__tab--active" : "auth__tab"
              }
              aria-current={mode === "signup" ? "page" : undefined}
              to="/signup"
            >
              Create account
            </Link>
          </nav>
          <p className="eyebrow">{copy.eyebrow}</p>
          <h1 className="auth__title display" id="auth-title">
            {copy.title}
          </h1>
          <form
            className="auth-form"
            onSubmit={onSubmit}
            aria-labelledby="auth-title"
            noValidate
          >
            <div className="field">
              <label className="field__label" htmlFor="auth-email">
                Email
              </label>
              <input
                id="auth-email"
                type="email"
                name="email"
                autoComplete={mode === "signup" ? "email" : "username"}
                placeholder="you@organization.org"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="field">
              <label className="field__label" htmlFor="auth-password">
                Password
              </label>
              <input
                id="auth-password"
                type="password"
                name="password"
                autoComplete={
                  mode === "signup" ? "new-password" : "current-password"
                }
                aria-describedby={
                  mode === "signup" ? "auth-password-hint" : undefined
                }
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
              {mode === "signup" && (
                <span className="field__hint" id="auth-password-hint">
                  Use at least {MIN_PASSWORD_LENGTH} characters.
                </span>
              )}
            </div>
            {error !== null && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="button button--primary button--block"
              disabled={pending}
            >
              {pending ? copy.pending : copy.action}
            </button>
          </form>
        </div>
      </div>

      <aside className="auth__panel" aria-hidden="true">
        <div className="auth__panel-inner">
          <ProductPreview />
          <h2 className="auth__panel-title display">
            Every protocol answer, on the record.
          </h2>
          <ul className="auth__points">
            <li>Durable, auditable AI conversations</li>
            <li>Organization-grade access control</li>
            <li>Secure sessions by default</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
