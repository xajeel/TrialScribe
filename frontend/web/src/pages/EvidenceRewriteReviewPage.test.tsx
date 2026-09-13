import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  EvidenceReviewPage,
  RewriteReviewPage,
} from "./EvidenceRewriteReviewPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderEvidence(kind: "pdf" | "json" | "web" | "section") {
  return render(
    <MemoryRouter>
      <EvidenceReviewPage initialKind={kind} />
    </MemoryRouter>,
  );
}

function renderRewrite(
  stage: "selection" | "whole" | "alternatives" | "confirm" | "compare",
) {
  return render(
    <MemoryRouter>
      <RewriteReviewPage initialStage={stage} />
    </MemoryRouter>,
  );
}

describe("EvidenceReviewPage", () => {
  it("opens each evidence kind directly and switches tabs", async () => {
    const user = userEvent.setup();
    renderEvidence("json");
    expect(
      screen.getByText("eligibility.inclusion_criteria[2]", {
        selector: "code",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Web" }));
    expect(screen.getByText("ascopubs.org")).toBeInTheDocument();
  });

  it("opens detailed section evidence from the citation and can reopen the panel", async () => {
    const user = userEvent.setup();
    renderEvidence("pdf");

    await user.click(
      screen.getByRole("button", { name: "Inspect citation [S3, p. 14]" }),
    );
    expect(screen.getByText("REF-882-03")).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Close evidence inspector" }),
    );
    expect(
      screen.queryByRole("complementary", { name: "Evidence inspector" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Reopen evidence inspector" }),
    );
    expect(
      screen.getByRole("complementary", { name: "Evidence inspector" }),
    ).toBeInTheDocument();
  });
});

describe("RewriteReviewPage", () => {
  it("does not fetch rewrite jobs on review routes", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderRewrite("selection");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(
      screen.getByText(/not produced or saved by the product/i),
    ).toBeInTheDocument();
  });
  it("moves from setup through compare and back to alternatives", async () => {
    const user = userEvent.setup();
    renderRewrite("selection");

    await user.click(screen.getByRole("button", { name: "Review alternatives" }));
    expect(
      screen.getByRole("heading", { name: "Rewrite alternatives" }),
    ).toBeInTheDocument();
    const first = screen.getByRole("article", { name: "Alternative 1" });
    await user.click(
      within(first).getByRole("button", { name: "Compare with original" }),
    );
    expect(
      screen.getByRole("heading", { name: "Compare wording" }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Back to alternatives" }),
    );
    expect(
      screen.getByRole("heading", { name: "Rewrite alternatives" }),
    ).toBeInTheDocument();
  });

  it("cancels confirmation with focus return, then confirms a demonstration", async () => {
    const user = userEvent.setup();
    renderRewrite("alternatives");
    const first = screen.getByRole("article", { name: "Alternative 1" });
    const useButton = within(first).getByRole("button", {
      name: "Use this version",
    });

    await user.click(useButton);
    let dialog = screen.getByRole("dialog", { name: "Use Alternative 1?" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(useButton).toHaveFocus();

    await user.click(useButton);
    dialog = screen.getByRole("dialog", { name: "Use Alternative 1?" });
    await user.click(
      within(dialog).getByRole("button", {
        name: "Use Alternative 1 in demonstration",
      }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Review demonstration applied",
    );
  });

  it("initializes whole, confirm, and compare states directly", () => {
    const whole = renderRewrite("whole");
    expect(
      screen.getByRole("heading", { name: "Rewrite section 5.1" }),
    ).toBeInTheDocument();
    whole.unmount();

    const confirm = renderRewrite("confirm");
    expect(
      screen.getByRole("dialog", { name: "Use Alternative 1?" }),
    ).toBeInTheDocument();
    confirm.unmount();

    renderRewrite("compare");
    expect(
      screen.getByRole("heading", { name: "Compare wording" }),
    ).toBeInTheDocument();
  });

  it("opens comparison in the inline view on a phone viewport", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({ matches: true } as MediaQueryList),
    );

    renderRewrite("compare");

    expect(screen.getByRole("button", { name: "Inline" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByText("Inline changes")).toBeInTheDocument();
  });
});
