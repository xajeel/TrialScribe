import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  READINESS_REVIEW_INCOMPLETE,
  READINESS_REVIEW_READY,
  type ReadinessIssueView,
} from "../product/governanceReviewFixtures";
import { ReadinessSummary } from "./ReadinessSummary";
import { ReadinessTable, type ReadinessFilter } from "./ReadinessTable";

function TableHarness({
  data = READINESS_REVIEW_INCOMPLETE,
  initialFilter = "all",
  onIssueAction,
  withNavigation = true,
}: {
  data?: typeof READINESS_REVIEW_INCOMPLETE;
  initialFilter?: ReadinessFilter;
  onIssueAction?: (issue: ReadinessIssueView) => void;
  withNavigation?: boolean;
}) {
  const [filter, setFilter] = useState<ReadinessFilter>(initialFilter);
  return (
    <ReadinessTable
      data={data}
      filter={filter}
      onFilterChange={setFilter}
      onIssueAction={onIssueAction}
      onOpenSection={withNavigation ? vi.fn() : undefined}
      onOpenEditor={withNavigation ? vi.fn() : undefined}
      onViewHistory={withNavigation ? vi.fn() : undefined}
    />
  );
}

describe("ReadinessSummary and ReadinessTable", () => {
  it("renders structured mixed and ready summaries", () => {
    const mixed = render(<ReadinessSummary data={READINESS_REVIEW_INCOMPLETE} />);
    expect(screen.getByText("Sections").parentElement).toHaveTextContent(
      "8 done · 6 draft",
    );
    expect(screen.getByText("Citations").parentElement).toHaveTextContent(
      "24 resolved · 1 needs review",
    );
    mixed.unmount();
    render(<ReadinessSummary data={READINESS_REVIEW_READY} />);
    expect(screen.getByRole("status")).toHaveTextContent("Protocol checks complete");
  });

  it("filters fixed-order sections and keeps controls in empty results", async () => {
    const user = userEvent.setup();
    render(<TableHarness />);
    const initialRows = screen.getAllByRole("row");
    expect(initialRows).toHaveLength(15);
    await user.click(screen.getByRole("button", { name: "Draft" }));
    expect(screen.getAllByRole("row").length).toBeLessThan(initialRows.length);
    await user.click(screen.getByRole("button", { name: "Needs attention" }));
    expect(screen.getByRole("button", { name: "All sections" })).toBeInTheDocument();
  });

  it("expands a row, opens quick review, and restores focus on close", async () => {
    const user = userEvent.setup();
    render(<TableHarness />);
    const sectionButton = screen.getByRole("button", { name: /5.*trial population/i });
    await user.click(sectionButton);
    expect(sectionButton).toHaveAttribute("aria-expanded", "true");
    const row = sectionButton.closest("tr");
    if (row === null) throw new Error("Expected section row");
    const review = within(row).getByRole("button", { name: "Review" });
    await user.click(review);
    expect(screen.getByRole("complementary", { name: /trial population/i })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close section quick review" }));
    expect(review).toHaveFocus();
  });

  it("runs only explicitly supplied review issue actions", async () => {
    const user = userEvent.setup();
    const action = vi.fn();
    const view = render(<TableHarness onIssueAction={action} />);
    await user.click(screen.getByRole("button", { name: "Retry demonstration" }));
    expect(action).toHaveBeenCalledWith(expect.objectContaining({ action: "retry-demo" }));
    view.unmount();
    render(<TableHarness withNavigation={false} />);
    expect(screen.queryByRole("button", { name: "Retry demonstration" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|comment/i })).not.toBeInTheDocument();
  });

  it("does not replace filters when attention is empty", async () => {
    const user = userEvent.setup();
    render(<TableHarness data={READINESS_REVIEW_READY} initialFilter="attention" />);
    expect(screen.getByRole("status")).toHaveTextContent("No sections match this filter");
    expect(screen.getByRole("button", { name: "All sections" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show all sections" }));
    expect(screen.getAllByRole("row")).toHaveLength(15);
  });
});
