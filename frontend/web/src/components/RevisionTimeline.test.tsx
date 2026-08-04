import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  REVISION_REVIEW_ROWS,
  type RevisionRowView,
} from "../product/governanceReviewFixtures";
import { RevisionPreview } from "./RevisionPreview";
import {
  EMPTY_REVISION_FILTERS,
  RevisionTimeline,
  type RevisionFiltersValue,
} from "./RevisionTimeline";

function TimelineHarness({
  status = "ready",
  rows = REVISION_REVIEW_ROWS,
  onPreview = vi.fn<(revision: RevisionRowView, opener: HTMLElement) => void>(),
  onCompare = vi.fn<(revision: RevisionRowView) => void>(),
  onRetry = vi.fn<() => void>(),
  onReturn = vi.fn<() => void>(),
}: {
  status?: "loading" | "ready" | "error";
  rows?: typeof REVISION_REVIEW_ROWS;
  onPreview?: (revision: RevisionRowView, opener: HTMLElement) => void;
  onCompare?: (revision: RevisionRowView) => void;
  onRetry?: () => void;
  onReturn?: () => void;
}) {
  const [filters, setFilters] = useState<RevisionFiltersValue>(EMPTY_REVISION_FILTERS);
  return (
    <RevisionTimeline
      status={status}
      rows={rows}
      filters={filters}
      onFiltersChange={setFilters}
      onPreview={onPreview}
      onCompare={onCompare}
      onRetry={onRetry}
      onReturnToDocument={onReturn}
    />
  );
}

describe("RevisionTimeline and RevisionPreview", () => {
  it("renders semantic newest-first history and current state", () => {
    render(<TimelineHarness />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(within(items[0]).getByText("Revision 7")).toBeInTheDocument();
    expect(within(items[0]).getByText("Current")).toBeInTheDocument();
  });

  it("filters by author and action, then resets", async () => {
    const user = userEvent.setup();
    render(<TimelineHarness />);
    await user.selectOptions(screen.getByLabelText("Author"), "Omar Shah");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("Safety exclusions clarified")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset filters" }));
    await user.selectOptions(screen.getByLabelText("Action"), "generated");
    const generated = screen.getAllByRole("listitem");
    expect(generated).toHaveLength(1);
    expect(within(generated[0]).getByText("Generated draft")).toBeInTheDocument();
  });

  it("expands a row and exposes preview and compare callbacks", async () => {
    const user = userEvent.setup();
    const preview = vi.fn();
    const compare = vi.fn();
    render(<TimelineHarness onPreview={preview} onCompare={compare} />);
    await user.click(screen.getByRole("button", { name: /revision 6/i }));
    await user.click(screen.getAllByRole("button", { name: "Preview" })[1]);
    await user.click(screen.getAllByRole("button", { name: "Compare" })[1]);
    expect(preview).toHaveBeenCalledWith(REVISION_REVIEW_ROWS[1], expect.any(HTMLElement));
    expect(compare).toHaveBeenCalledWith(REVISION_REVIEW_ROWS[1]);
  });

  it("keeps loading, error/retry, and true empty states explicit", async () => {
    const user = userEvent.setup();
    const loading = render(<TimelineHarness status="loading" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading revision history");
    loading.unmount();

    const retry = vi.fn();
    const error = render(<TimelineHarness status="error" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Could not load revision history");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
    error.unmount();

    const onReturn = vi.fn();
    render(<TimelineHarness rows={[]} onReturn={onReturn} />);
    expect(screen.getByRole("heading", { name: "No revision history yet" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Return to document" }));
    expect(onReturn).toHaveBeenCalledOnce();
  });

  it("renders a read-only preview and hides unsupported restore", async () => {
    const user = userEvent.setup();
    const close = vi.fn();
    const compare = vi.fn();
    render(
      <RevisionPreview
        revision={REVISION_REVIEW_ROWS[1]}
        returnFocusTo={null}
        onClose={close}
        onCompare={compare}
      />,
    );
    expect(screen.getByLabelText("Revision 6 section text")).toHaveTextContent("Participants");
    expect(screen.queryByRole("button", { name: /restore/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Compare with current" }));
    expect(compare).toHaveBeenCalledWith(REVISION_REVIEW_ROWS[1]);
    await user.click(screen.getByRole("button", { name: "Close revision preview" }));
    expect(close).toHaveBeenCalledOnce();
  });
});
