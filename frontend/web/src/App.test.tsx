import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "./api/client";
import { renderApp } from "./test/renderApp";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("App", () => {
  beforeEach(() => {
    tokenStore.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the landing page to anonymous visitors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(401, { detail: "Invalid authentication credentials" }),
      ),
    );

    renderApp();

    expect(
      await screen.findByRole("heading", {
        name: /keep the answer on record/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Get started" }),
    ).toBeInTheDocument();
  });
});
