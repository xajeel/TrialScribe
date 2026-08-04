import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  REWRITE_REVIEW_FIXTURE,
  type RewriteAlternative,
} from "../product/evidenceRewriteReviewFixtures";
import { RewritePanel, type RewritePanelProps } from "./RewritePanel";

function props(overrides: Partial<RewritePanelProps> = {}): RewritePanelProps {
  return {
    stage: "selection",
    fixture: REWRITE_REVIEW_FIXTURE,
    instruction: REWRITE_REVIEW_FIXTURE.instruction,
    keepCitations: true,
    useSources: true,
    selectedAlternativeId: "alternative-1",
    onInstructionChange: vi.fn(),
    onKeepCitationsChange: vi.fn(),
    onUseSourcesChange: vi.fn(),
    onReviewAlternatives: vi.fn(),
    onSelectAlternative: vi.fn(),
    onCompare: vi.fn(),
    onUse: vi.fn(),
    onRevise: vi.fn(),
    onKeepOriginal: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
}

describe("RewritePanel", () => {
  it("validates an instruction before moving to alternatives", async () => {
    const user = userEvent.setup();
    const onReviewAlternatives = vi.fn();
    render(
      <RewritePanel
        {...props({ instruction: "", onReviewAlternatives })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Review alternatives" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a rewrite instruction.",
    );
    expect(onReviewAlternatives).not.toHaveBeenCalled();
  });

  it("reports controlled edits, evidence scope, submit, and close", async () => {
    const user = userEvent.setup();
    const handlers = {
      onInstructionChange: vi.fn(),
      onKeepCitationsChange: vi.fn(),
      onUseSourcesChange: vi.fn(),
      onReviewAlternatives: vi.fn(),
      onClose: vi.fn(),
    };
    render(<RewritePanel {...props(handlers)} />);

    await user.type(screen.getByLabelText("Rewrite instruction"), " More");
    expect(handlers.onInstructionChange).toHaveBeenCalled();
    await user.click(screen.getByLabelText("Keep current citations"));
    expect(handlers.onKeepCitationsChange).toHaveBeenCalledWith(false);
    await user.click(screen.getByLabelText("Use available workspace sources"));
    expect(handlers.onUseSourcesChange).toHaveBeenCalledWith(false);
    await user.click(screen.getByRole("button", { name: "Review alternatives" }));
    expect(handlers.onReviewAlternatives).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Close rewrite panel" }));
    expect(handlers.onClose).toHaveBeenCalledTimes(1);
  });

  it("renders whole-section setup without fabricated usage details", () => {
    render(
      <RewritePanel
        {...props({
          stage: "whole",
          instruction: REWRITE_REVIEW_FIXTURE.wholeInstruction,
        })}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Rewrite section 5.1" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Review fixture");
    expect(screen.queryByText(/token/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cost/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/model/i)).not.toBeInTheDocument();
  });

  it("selects, compares, and uses either deterministic alternative", async () => {
    const user = userEvent.setup();
    const onSelectAlternative = vi.fn();
    const onCompare = vi.fn();
    const onUse = vi.fn();
    render(
      <RewritePanel
        {...props({
          stage: "alternatives",
          onSelectAlternative,
          onCompare,
          onUse,
        })}
      />,
    );

    const second = screen.getByRole("article", { name: "Alternative 2" });
    await user.click(within(second).getByLabelText("Select"));
    expect(onSelectAlternative).toHaveBeenCalledWith("alternative-2");
    await user.click(
      within(second).getByRole("button", { name: "Compare with original" }),
    );
    expect(onCompare).toHaveBeenCalledWith("alternative-2");
    await user.click(
      within(second).getByRole("button", { name: "Use this version" }),
    );
    expect(onUse).toHaveBeenCalledWith(
      "alternative-2" satisfies RewriteAlternative["id"],
      expect.any(HTMLElement),
    );
  });

  it("can revise the instruction or keep the original", async () => {
    const user = userEvent.setup();
    const onRevise = vi.fn();
    const onKeepOriginal = vi.fn();
    render(
      <RewritePanel
        {...props({ stage: "alternatives", onRevise, onKeepOriginal })}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Revise instruction" }));
    expect(onRevise).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Keep original" }));
    expect(onKeepOriginal).toHaveBeenCalledTimes(1);
  });
});
