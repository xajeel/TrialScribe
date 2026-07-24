import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { renderApp } from "../test/renderApp";

interface MockResponse {
  status: number;
  body?: unknown;
}

type Handler = MockResponse | MockResponse[];

const ACCOUNT = {
  id: "acc-1",
  email: "user@example.com",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};
const TOKENS = { access_token: "access-1", token_type: "bearer", expires_in: 900 };
const ORGS = [
  { id: "org-1", name: "Acme Trials", role: "owner", created_at: "2026-01-01T00:00:00Z" },
];
const UNAUTHORIZED: MockResponse = {
  status: 401,
  body: { detail: "Invalid authentication credentials" },
};

function toResponse({ status, body }: MockResponse): Response {
  if (status === 204) {
    return new Response(null, { status });
  }
  return new Response(JSON.stringify(body ?? {}), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stub `fetch`, dispatching on `"METHOD /pathname"`; array handlers step per call. */
function mockFetch(routes: Record<string, Handler>) {
  const calls: Record<string, number> = {};
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input.toString());
    const key = `${(init?.method ?? "GET").toUpperCase()} ${url.pathname}`;
    const handler = routes[key];
    if (handler === undefined) {
      throw new Error(`unexpected request: ${key}`);
    }
    if (Array.isArray(handler)) {
      const index = calls[key] ?? 0;
      calls[key] = index + 1;
      return toResponse(handler[Math.min(index, handler.length - 1)]);
    }
    return toResponse(handler);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

describe("session flow", () => {
  beforeEach(() => {
    tokenStore.clear();
    localStorage.clear();
    document.cookie = "trialscribe_csrf=csrf-token";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("restores a session on load", async () => {
    mockFetch({
      "POST /v1/auth/refresh": { status: 200, body: TOKENS },
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      "GET /v1/organizations": { status: 200, body: ORGS },
    });

    renderApp({ route: "/workspace" });

    expect(await screen.findByText(/Signed in as user@example.com/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("rejects a protected route without a session", async () => {
    mockFetch({ "POST /v1/auth/refresh": UNAUTHORIZED });

    renderApp({ route: "/workspace" });

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("signs in from the login form", async () => {
    mockFetch({
      "POST /v1/auth/refresh": UNAUTHORIZED,
      "POST /v1/auth/login": { status: 200, body: TOKENS },
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      "GET /v1/organizations": { status: 200, body: ORGS },
    });
    const user = userEvent.setup();

    renderApp({ route: "/login" });

    await user.type(await screen.findByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText(/Signed in as user@example.com/)).toBeInTheDocument();
  });

  it("creates an account from the signup form", async () => {
    mockFetch({
      "POST /v1/auth/refresh": UNAUTHORIZED,
      "POST /v1/auth/register": { status: 201, body: ACCOUNT },
      "POST /v1/auth/login": { status: 200, body: TOKENS },
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      "GET /v1/organizations": { status: 200, body: ORGS },
    });
    const user = userEvent.setup();

    renderApp({ route: "/signup" });

    await user.type(await screen.findByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByText(/Signed in as user@example.com/)).toBeInTheDocument();
  });

  it("blocks a too-short signup password before calling the API", async () => {
    const fetchMock = mockFetch({ "POST /v1/auth/refresh": UNAUTHORIZED });
    const user = userEvent.setup();

    renderApp({ route: "/signup" });

    await user.type(await screen.findByLabelText("Email"), "user@example.com");
    await user.type(screen.getByLabelText("Password"), "short");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 15/i);
    // Only the bootstrap refresh ran — no register or login request went out.
    expect(
      fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").length,
    ).toBe(1);
  });

  it("logs out back to the login form", async () => {
    mockFetch({
      "POST /v1/auth/refresh": { status: 200, body: TOKENS },
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      "GET /v1/organizations": { status: 200, body: ORGS },
      "POST /v1/auth/logout": { status: 204 },
    });
    const user = userEvent.setup();

    renderApp({ route: "/workspace" });
    await user.click(
      await screen.findByRole("button", { name: "Account menu" }),
    );
    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });

  it("shows the profile page with account and organization details", async () => {
    mockFetch({
      "POST /v1/auth/refresh": { status: 200, body: TOKENS },
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      "GET /v1/organizations": { status: 200, body: ORGS },
    });

    renderApp({ route: "/profile" });

    expect(
      await screen.findByRole("heading", { name: "Profile and settings" }),
    ).toBeInTheDocument();
    expect(screen.getByText("user@example.com")).toBeInTheDocument();
    // Listed in the Organizations card and again in the Preferences select.
    expect(await screen.findAllByText("Acme Trials")).not.toHaveLength(0);
    expect(
      screen.getByLabelText("Active organization"),
    ).toBeInTheDocument();
  });

  it("recovers an expired token by silently refreshing and retrying", async () => {
    mockFetch({
      "POST /v1/auth/refresh": { status: 200, body: TOKENS },
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      // First org load 401s (expired access token); the retry after refresh succeeds.
      "GET /v1/organizations": [UNAUTHORIZED, { status: 200, body: ORGS }],
    });

    renderApp({ route: "/workspace" });

    expect(await screen.findByText(/Signed in as user@example.com/)).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: "Acme Trials" })).toBeInTheDocument();
  });

  it("redirects to login when the silent refresh also fails", async () => {
    mockFetch({
      // Bootstrap refresh succeeds; the retry refresh (after a 401) fails.
      "POST /v1/auth/refresh": [{ status: 200, body: TOKENS }, UNAUTHORIZED],
      "GET /v1/auth/me": { status: 200, body: ACCOUNT },
      "GET /v1/organizations": UNAUTHORIZED,
    });

    renderApp({ route: "/workspace" });

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  });
});
