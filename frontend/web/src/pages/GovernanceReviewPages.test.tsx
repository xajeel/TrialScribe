import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { tokenStore } from "../api/client";
import { renderApp } from "../test/renderApp";

function unauthorized(): Response {
  return new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

describe("governance review pages", () => {
  beforeEach(() => {
    tokenStore.clear();
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("opens timeline, preview, empty, and comparison directly", async () => {
    const timeline = renderApp({ route: "/review/revisions" });
    expect(await screen.findByRole("heading", { name: "Revision history" })).toBeInTheDocument();
    expect(screen.getByText(/development review data/i)).toBeInTheDocument();
    timeline.unmount();

    const preview = renderApp({ route: "/review/revisions/preview" });
    expect(await screen.findByRole("complementary")).toHaveTextContent("Revision 6");
    preview.unmount();

    const empty = renderApp({ route: "/review/revisions/empty" });
    expect(await screen.findByRole("heading", { name: "No revision history yet" })).toBeInTheDocument();
    empty.unmount();

    renderApp({ route: "/review/revisions/compare" });
    expect(await screen.findByText("Compare revisions")).toBeInTheDocument();
    expect(screen.getByText("12 additions")).toBeInTheDocument();
  });

  it("cancels and confirms the local restore demonstration", async () => {
    const user = userEvent.setup();
    const view = renderApp({ route: "/review/revisions/restore" });
    expect(await screen.findByRole("dialog", { name: /restore revision 6/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    view.unmount();

    renderApp({ route: "/review/revisions/restore" });
    await user.click(await screen.findByRole("button", { name: "Restore as revision 8" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Stored history was not changed");
    expect(
      vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("/restore")),
    ).toBe(false);
  });

  it("opens readiness attention, filtered, ready, and retry states directly", async () => {
    const attention = renderApp({ route: "/review/readiness/attention" });
    expect(await screen.findByRole("heading", { name: "Protocol readiness" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Needs attention" })).toHaveAttribute("aria-pressed", "true");
    attention.unmount();

    const filtered = renderApp({ route: "/review/readiness/filtered" });
    expect(await screen.findByRole("button", { name: "Needs attention" })).toHaveAttribute("aria-pressed", "true");
    filtered.unmount();

    const ready = renderApp({ route: "/review/readiness/ready" });
    expect(await screen.findByRole("status")).toHaveTextContent("Protocol checks complete");
    ready.unmount();

    renderApp({ route: "/review/readiness/retry" });
    expect(await screen.findByRole("status")).toHaveTextContent("Retrying in this review demonstration");
    expect(
      vi.mocked(fetch).mock.calls.some(([input]) => String(input).includes("/v1/jobs")),
    ).toBe(false);
  });

  it("completes retry locally without claiming a stored change", async () => {
    const user = userEvent.setup();
    renderApp({ route: "/review/readiness" });
    await user.click(await screen.findByRole("button", { name: "Retry demonstration" }));
    expect(screen.getByText(/retry completed in this development review/i)).toBeInTheDocument();
    expect(screen.getByText(/resolved in this review demonstration/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|comment|export/i })).not.toBeInTheDocument();
  });
});
