import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { OrganizationProvider } from "../org/OrganizationContext";
import { UsagePage, type UsageReviewState } from "./UsagePage";

function unauthorized(): Response {
  return new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

function renderReview(review: UsageReviewState) {
  return render(
    <MemoryRouter initialEntries={[`/review/usage/${review}`]}>
      <AuthProvider>
        <OrganizationProvider>
          <UsagePage review={review} />
        </OrganizationProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("UsagePage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders a workspace-scoped populated audit with an explicit fixture note", () => {
    renderReview("populated");

    expect(screen.getByRole("dialog", { name: "Usage and cost" })).toBeInTheDocument();
    expect(screen.getByText("$12.46")).toBeInTheDocument();
    expect(screen.getByText(/costs and provider calls are illustrative/i)).toBeInTheDocument();
    expect(screen.queryByText(/manage billing|download csv|export json/i)).not.toBeInTheDocument();
  });

  it("opens expanded call detail directly", () => {
    renderReview("expanded");

    expect(screen.getByText("JOB-7729-X")).toBeInTheDocument();
    expect(screen.getByText("Provider-call breakdown")).toBeInTheDocument();
  });

  it("shows running activity without estimating final cost", () => {
    renderReview("running");

    expect(screen.getAllByText("In progress").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Finalizes on completion").length).toBeGreaterThan(0);
    expect(screen.queryByText(/estimated cost/i)).not.toBeInTheDocument();
  });

  it("keeps filters visible in a filtered-to-nothing state and clears them", async () => {
    const user = userEvent.setup();
    renderReview("filtered");

    expect(screen.getByLabelText("Outcome")).toHaveValue("attention");
    await user.selectOptions(screen.getByLabelText("Section"), "5");
    expect(screen.getByText(/filters changed locally/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Section")).toBeInTheDocument();
  });

  it("recovers from the review error without claiming a stored read", async () => {
    const user = userEvent.setup();
    renderReview("error");

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(screen.getByText(/no model usage recorded/i)).toBeInTheDocument();
    expect(screen.getByText(/no stored usage was read or changed/i)).toBeInTheDocument();
  });
});
