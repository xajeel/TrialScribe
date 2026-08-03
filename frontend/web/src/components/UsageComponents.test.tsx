import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import {
  REVIEW_USAGE_EMPTY,
  REVIEW_USAGE_RUNNING,
  REVIEW_USAGE_VIEW,
} from "../product/deliveryAuditReviewFixtures";
import {
  DEFAULT_USAGE_FILTERS,
  GenerationUsageTable,
  type UsageFiltersValue,
} from "./GenerationUsageTable";
import { UsageSummary } from "./UsageSummary";

function InteractiveTable({ initial = DEFAULT_USAGE_FILTERS }: { initial?: UsageFiltersValue }) {
  const [filters, setFilters] = useState(initial);
  return (
    <GenerationUsageTable
      view={REVIEW_USAGE_VIEW}
      filters={filters}
      onFiltersChange={setFilters}
    />
  );
}

describe("usage components", () => {
  it("renders exact totals and no visualization", () => {
    render(<UsageSummary view={REVIEW_USAGE_VIEW} />);

    expect(screen.getByText("$12.46")).toBeInTheDocument();
    expect(screen.getByText("1,284,620")).toBeInTheDocument();
    expect(document.querySelector("svg, canvas")).toBeNull();
  });

  it("expands a generation into allowed audit metadata and restores focus", async () => {
    const user = userEvent.setup();
    render(<InteractiveTable />);

    const opener = screen.getByRole("button", { name: "Sections 5–6" });
    await user.click(opener);
    expect(opener).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("JOB-7729-X")).toBeInTheDocument();
    expect(screen.getByText("Provider-call breakdown")).toBeInTheDocument();
    expect(screen.queryByText(/prompt|evidence passage|credential|stack/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close detail" }));
    expect(opener).toHaveFocus();
  });

  it("filters by outcome and keeps controls when no rows match", async () => {
    const user = userEvent.setup();
    render(<InteractiveTable />);

    await user.selectOptions(screen.getByLabelText("Outcome"), "running");
    expect(screen.getByText(/no generations match/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Outcome")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("button", { name: "Sections 5–6" })).toBeInTheDocument();
  });

  it("filters older records by date and Clear filters restores them", async () => {
    const user = userEvent.setup();
    render(<InteractiveTable />);

    expect(screen.getByRole("button", { name: "Sections 5–6" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Date range"), "24-hours");
    expect(screen.queryByRole("button", { name: "Sections 5–6" })).not.toBeInTheDocument();
    expect(screen.getByText(/no generations match/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Date range")).toHaveValue("24-hours");
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("button", { name: "Sections 5–6" })).toBeInTheDocument();
    expect(screen.getByLabelText("Date range")).toHaveValue("all");
  });

  it("renders running cost as finalizing rather than estimating", () => {
    render(
      <GenerationUsageTable
        view={REVIEW_USAGE_RUNNING}
        filters={DEFAULT_USAGE_FILTERS}
        onFiltersChange={vi.fn()}
      />,
    );

    expect(screen.getAllByText("Finalizes on completion").length).toBeGreaterThan(0);
    expect(screen.queryByText(/estimate/i)).not.toBeInTheDocument();
  });

  it("renders exact empty and safe retryable error states", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const view = render(
      <GenerationUsageTable
        view={REVIEW_USAGE_EMPTY}
        filters={DEFAULT_USAGE_FILTERS}
        onFiltersChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/no model usage recorded/i)).toBeInTheDocument();

    view.rerender(
      <GenerationUsageTable
        view={REVIEW_USAGE_EMPTY}
        filters={DEFAULT_USAGE_FILTERS}
        onFiltersChange={vi.fn()}
        error
        onRetry={onRetry}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.queryByText(/exception|stack|provider/i)).not.toBeInTheDocument();
  });
});
