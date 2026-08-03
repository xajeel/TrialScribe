import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import {
  REVIEW_EXPORT_JOB,
  REVIEW_EXPORT_VIEW,
} from "../product/deliveryAuditReviewFixtures";
import { ExportJobPanel } from "./ExportJobPanel";
import { ExportScopeSelector } from "./ExportScopeSelector";
import { SectionManifest } from "./SectionManifest";

describe("export components", () => {
  it("uses explicit scope choices and warns when drafts are included", async () => {
    const user = userEvent.setup();
    const onScopeChange = vi.fn();
    const view = render(
      <ExportScopeSelector
        view={REVIEW_EXPORT_VIEW}
        scope="done-only"
        onScopeChange={onScopeChange}
      />,
    );

    await user.click(screen.getByLabelText(/include unfinished sections/i));
    expect(onScopeChange).toHaveBeenCalledWith("include-drafts");

    view.rerender(
      <ExportScopeSelector
        view={REVIEW_EXPORT_VIEW}
        scope="include-drafts"
        onScopeChange={onScopeChange}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/clearly marked as draft/i);
  });

  it("renders all fixed-order manifest rows and reveals row detail", async () => {
    const user = userEvent.setup();
    render(
      <SectionManifest sections={REVIEW_EXPORT_VIEW.sections} scope="done-only" />,
    );

    expect(screen.getAllByRole("listitem")).toHaveLength(
      REVIEW_EXPORT_VIEW.sections.length,
    );
    expect(screen.queryByText(/drag|reorder/i)).not.toBeInTheDocument();
    const first = screen.getAllByRole("button")[0];
    expect(first).toHaveAttribute("aria-expanded", "false");
    await user.click(first);
    expect(first).toHaveAttribute("aria-expanded", "true");
  });

  it("renders building stages without an invented estimate", () => {
    render(
      <ExportJobPanel
        state="building"
        job={REVIEW_EXPORT_JOB}
        onClose={vi.fn()}
        onRetry={vi.fn()}
        onBack={vi.fn()}
        onCreateAnother={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(screen.getByRole("heading", { name: "Preparing export" })).toBeInTheDocument();
    expect(screen.getByText("Assembling sections")).toBeInTheDocument();
    expect(screen.queryByText(/minutes|seconds remaining|estimated/i)).not.toBeInTheDocument();
  });

  it("keeps failure copy public and wires retry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <ExportJobPanel
        state="failed"
        job={REVIEW_EXPORT_JOB}
        onClose={vi.fn()}
        onRetry={onRetry}
        onBack={vi.fn()}
        onCreateAnother={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(screen.queryByText(/stack|storage|exception/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry export" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("renders ready metadata and routes download through a callback", async () => {
    const user = userEvent.setup();
    const onDownload = vi.fn();
    render(
      <ExportJobPanel
        state="ready"
        job={REVIEW_EXPORT_JOB}
        onClose={vi.fn()}
        onRetry={vi.fn()}
        onBack={vi.fn()}
        onCreateAnother={vi.fn()}
        onDownload={onDownload}
      />,
    );

    expect(
      screen.getAllByText(REVIEW_EXPORT_JOB.readyFile.filename),
    ).toHaveLength(2);
    await user.click(screen.getByRole("button", { name: "Download DOCX" }));
    expect(onDownload).toHaveBeenCalledWith(REVIEW_EXPORT_JOB.readyFile);
  });
});
