import { act, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { renderApp } from "../test/renderApp";

function unauthorizedResponse(): Response {
  return new Response(
    JSON.stringify({ detail: "Invalid authentication credentials" }),
    {
      status: 401,
      headers: { "Content-Type": "application/json" },
    },
  );
}

describe("SessionCheckPage", () => {
  beforeEach(() => {
    tokenStore.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("keeps the development review route visible after bootstrap finishes", async () => {
    let resolveRefresh: (response: Response) => void = () => undefined;
    const refreshRequest = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (): Promise<Response> => refreshRequest),
    );

    renderApp({ route: "/review/session-check" });

    expect(
      screen.getByRole("heading", { name: "Checking your session…" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveAttribute("href", "/");
    expect(
      screen.getByRole("link", { name: "TrialScribe home" }),
    ).toHaveClass("brand-logo");

    await act(async () => {
      resolveRefresh(unauthorizedResponse());
      await refreshRequest;
    });

    expect(
      screen.getByRole("heading", { name: "Checking your session…" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("shows the protected-session check before redirecting an expired session", async () => {
    let resolveRefresh: (response: Response) => void = () => undefined;
    const refreshRequest = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (): Promise<Response> => refreshRequest),
    );

    const { container } = renderApp({ route: "/workspace" });

    expect(
      screen.getByRole("heading", { name: "Checking your session…" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Restoring secure access to your protocol workspaces.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("progressbar", {
        name: "Session verification in progress",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Verifying credentials",
    );
    expect(container.querySelector(".session-check")).toHaveAttribute(
      "aria-busy",
      "true",
    );
    expect(
      screen.queryByRole("button", { name: "Account menu" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Signed in as/)).not.toBeInTheDocument();

    await act(async () => {
      resolveRefresh(unauthorizedResponse());
      await refreshRequest;
    });

    expect(await screen.findByLabelText("Email")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Checking your session…" }),
    ).not.toBeInTheDocument();
  });
});
