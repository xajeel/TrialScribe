import { API_BASE_URL } from "../config";

/** Error carrying the gateway's HTTP status and public detail message. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

const CSRF_COOKIE = "trialscribe_csrf";

let accessToken: string | null = null;

/** In-memory holder for the short-lived access token (never persisted). */
export const tokenStore = {
  get(): string | null {
    return accessToken;
  },
  set(token: string): void {
    accessToken = token;
  },
  clear(): void {
    accessToken = null;
  },
};

/** Read a non-httpOnly cookie value, or null when absent. */
export function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const entry of document.cookie.split(";")) {
    const trimmed = entry.trim();
    if (trimmed.startsWith(prefix)) {
      return decodeURIComponent(trimmed.slice(prefix.length));
    }
  }
  return null;
}

export interface RequestOptions {
  method?: string;
  json?: unknown;
  body?: BodyInit;
  headers?: HeadersInit;
  auth?: boolean;
  csrf?: boolean;
}

/** Build the public organization-selection header required by AI routes. */
export function organizationHeaders(organizationId: string): HeadersInit {
  return { "X-Organization-ID": organizationId };
}

/**
 * Send one credentialed request to the gateway. Attaches the bearer token when
 * `auth`, echoes the CSRF cookie when `csrf`, and throws `ApiError` on failure.
 */
export async function apiFetch<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  if (opts.json !== undefined && opts.body !== undefined) {
    throw new TypeError("Request cannot contain both JSON and a raw body");
  }

  const headers = new Headers(opts.headers);
  let body = opts.body;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  if (opts.auth) {
    const token = tokenStore.get();
    if (token !== null) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  if (opts.csrf) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf !== null) {
      headers.set("X-CSRF-Token", csrf);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: opts.method ?? "GET",
    credentials: "include",
    headers,
    body,
  });

  if (!response.ok) {
    throw new ApiError(response.status, await readDetail(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function readDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // Non-JSON error body — fall through to the status text.
  }
  return response.statusText || `Request failed (${response.status})`;
}
