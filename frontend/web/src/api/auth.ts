import { apiFetch } from "./client";
import type { Account, TokenResponse } from "./types";

/** Create a new account; the caller signs in separately afterwards. */
export function register(email: string, password: string): Promise<Account> {
  return apiFetch<Account>("/v1/auth/register", {
    method: "POST",
    json: { email, password },
  });
}

/** Exchange credentials for a short-lived access token; sets session cookies. */
export function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/v1/auth/login", {
    method: "POST",
    json: { email, password },
  });
}

/** Rotate the refresh cookie into a fresh access token (double-submit CSRF). */
export function refresh(): Promise<TokenResponse> {
  return apiFetch<TokenResponse>("/v1/auth/refresh", {
    method: "POST",
    csrf: true,
  });
}

/** Revoke the current session and clear its cookies (double-submit CSRF). */
export function logout(): Promise<void> {
  return apiFetch<void>("/v1/auth/logout", { method: "POST", csrf: true });
}

/** Load the account for the current access token. */
export function fetchMe(): Promise<Account> {
  return apiFetch<Account>("/v1/auth/me", { auth: true });
}
