import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { REWRITE_REVIEW_FIXTURE } from "../product/evidenceRewriteReviewFixtures";
import { ComparePanel, type ComparePanelProps } from "./ComparePanel";

function props(overrides: Partial<ComparePanelProps> = {}): ComparePanelProps {
  return {
    fixture: REWRITE_REVIEW_FIXTURE,
    alternative: REWRITE_REVIEW_FIXTURE.alternatives[0],
    view: "side-by-side",
    onChangeView: vi.fn(),
    onBack: vi.fn(),
    onUse: vi.fn(),
    ...overrides,
  };
}

describe("ComparePanel", () => {
  it("renders side-by-side semantic additions and removals", () => {
    const { container } = render(<ComparePanel {...props()} />);
    expect(
      screen.getByRole("heading", { name: "Compare wording" }),
    ).toBeInTheDocument();
    expect(screen.getByText("12 additions")).toBeInTheDocument();
    expect(screen.getByText("4 removals")).toBeInTheDocument();
    expect(container.querySelectorAll("del").length).toBeGreaterThan(0);
    expect(container.querySelectorAll("ins").length).toBeGreaterThan(0);
    expect(screen.getByText("Revision 7 · Earlier")).toBeInTheDocument();
    expect(screen.getByText("Alternative 1 · Later")).toBeInTheDocument();
  });

  it("renders one inline document from the same segments", () => {
    const { container } = render(
      <ComparePanel {...props({ view: "inline" })} />,
    );
    expect(screen.getByText("Inline changes")).toBeInTheDocument();
    expect(screen.getByText("Revised wording")).toBeInTheDocument();
    expect(container.querySelector("del")).toBeInTheDocument();
    expect(container.querySelector("ins")).toBeInTheDocument();
  });

  it("changes view and returns to alternatives", async () => {
    const user = userEvent.setup();
    const onChangeView = vi.fn();
    const onBack = vi.fn();
    render(<ComparePanel {...props({ onChangeView, onBack })} />);

    await user.click(screen.getByRole("button", { name: "Inline" }));
    expect(onChangeView).toHaveBeenCalledWith("inline");
    await user.click(
      screen.getByRole("button", { name: "Back to alternatives" }),
    );
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("offers safe use without Page 14 revision actions", async () => {
    const user = userEvent.setup();
    const onUse = vi.fn();
    render(<ComparePanel {...props({ onUse })} />);

    await user.click(screen.getByRole("button", { name: "Use this version" }));
    expect(onUse).toHaveBeenCalledWith(expect.any(HTMLElement));
    expect(screen.queryByText(/restore/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/publish/i)).not.toBeInTheDocument();
  });
});
