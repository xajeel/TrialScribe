import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  EVIDENCE_REVIEW_FIXTURES,
  type EvidenceReviewKind,
} from "../product/evidenceRewriteReviewFixtures";
import { EvidenceInspector } from "./EvidenceInspector";

function renderInspector(kind: EvidenceReviewKind) {
  const onSelectKind = vi.fn();
  const onClose = vi.fn();
  render(
    <EvidenceInspector
      evidence={EVIDENCE_REVIEW_FIXTURES[kind]}
      active={kind}
      onSelectKind={onSelectKind}
      onClose={onClose}
    />,
  );
  return { onSelectKind, onClose };
}

describe("EvidenceInspector", () => {
  it("renders PDF provenance and selects another evidence type", async () => {
    const user = userEvent.setup();
    const { onSelectKind } = renderInspector("pdf");
    const inspector = screen.getByRole("complementary", {
      name: "Evidence inspector",
    });

    expect(within(inspector).getByText("investigator_brochure_v8.pdf")).toBeInTheDocument();
    expect(within(inspector).getByText("Page 14, paragraph 3")).toBeInTheDocument();
    expect(within(inspector).getByText("14")).toBeInTheDocument();
    expect(within(inspector).getByText("3")).toBeInTheDocument();

    await user.click(within(inspector).getByRole("tab", { name: "JSON" }));
    expect(onSelectKind).toHaveBeenCalledWith("json");
  });

  it("renders structured JSON fields", () => {
    renderInspector("json");
    expect(screen.getByText("eligibility.inclusion_criteria[2]", { selector: "code" })).toBeInTheDocument();
    expect(screen.getByText("ECOG performance status")).toBeInTheDocument();
    expect(screen.getByText("At screening")).toBeInTheDocument();
  });

  it("renders stored web metadata without external navigation", () => {
    renderInspector("web");
    expect(screen.getByText("Journal of Clinical Oncology")).toBeInTheDocument();
    expect(screen.getByText("ascopubs.org")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders in-section evidence details and closes", async () => {
    const user = userEvent.setup();
    const { onClose } = renderInspector("section");
    expect(screen.getByText("REF-882-03")).toBeInTheDocument();
    expect(screen.getByText(/Cross-reference this passage/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "PDF" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await user.click(
      screen.getByRole("button", { name: "Close evidence inspector" }),
    );
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("announces the copy demonstration and omits unsupported claims", async () => {
    const user = userEvent.setup();
    renderInspector("pdf");

    await user.click(screen.getByRole("button", { name: "Copy citation" }));
    expect(screen.getByRole("status")).toHaveTextContent(
      "Citation copied in this review demonstration.",
    );
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/verified/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/contributor/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/update reference/i)).not.toBeInTheDocument();
  });
});
