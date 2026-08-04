import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../auth/AuthContext";
import { OrganizationProvider } from "../org/OrganizationContext";
import type { ExportReviewState } from "../product/deliveryAuditReviewFixtures";
import { ExportPage } from "./ExportPage";

function unauthorized(): Response {
  return new Response(JSON.stringify({ detail: "Not authenticated" }), {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
}

function renderReview(review: ExportReviewState) {
  return render(
    <MemoryRouter initialEntries={[`/review/export/${review}`]}>
      <AuthProvider>
        <OrganizationProvider>
          <ExportPage review={review} />
        </OrganizationProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ExportPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () => unauthorized()));
  });

  afterEach(() => vi.unstubAllGlobals());

  it("renders configuration with all fixed-order sections and review disclosure", () => {
    renderReview("configuration");

    expect(screen.getByRole("dialog", { name: "Export protocol" })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(14);
    expect(screen.getByText(/development review data/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate DOCX" })).toBeEnabled();
  });

  it("selects drafts and moves generation into a local-only building state", async () => {
    const user = userEvent.setup();
    renderReview("configuration");

    await user.click(screen.getByLabelText(/include unfinished sections/i));
    expect(screen.getByRole("status")).toHaveTextContent(/marked as draft/i);
    await user.click(screen.getByRole("button", { name: "Generate DOCX" }));
    expect(screen.getByRole("heading", { name: "Preparing export" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/no export job was created/i);
  });

  it("disables generation when no section is Done", () => {
    renderReview("empty");

    expect(screen.getByText(/complete at least one section/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate DOCX" })).toBeDisabled();
  });

  it("supports ready download feedback without creating a file", async () => {
    const user = userEvent.setup();
    renderReview("ready");

    await user.click(screen.getByRole("button", { name: "Download DOCX" }));
    expect(screen.getByRole("status")).toHaveTextContent(/was not downloaded/i);
  });

  it("retries a failed export only inside the review", async () => {
    const user = userEvent.setup();
    renderReview("failed");

    await user.click(screen.getByRole("button", { name: "Retry export" }));
    expect(screen.getByRole("heading", { name: "Preparing export" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/development review only/i);
  });
});
