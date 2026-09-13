import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { BrandLogo } from "./BrandLogo";

describe("BrandLogo", () => {
  it("renders the canonical logo as an accessible router link", () => {
    const { container } = render(
      <MemoryRouter>
        <BrandLogo className="page-position" to="/" />
      </MemoryRouter>,
    );

    const link = screen.getByRole("link", { name: "TrialScribe home" });
    expect(link).toHaveAttribute("href", "/");
    expect(link).toHaveClass("brand-logo", "page-position");
    expect(within(link).getByText("TrialScribe")).toHaveClass(
      "brand-logo__text",
    );
    expect(container.querySelector(".brand-logo__mark")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("renders a non-linked footer lockup with a custom accessible name", () => {
    const { container } = render(
      <BrandLogo ariaLabel="TrialScribe product" />,
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(screen.getByLabelText("TrialScribe product")).toHaveClass(
      "brand-logo",
    );
    expect(container.querySelector(".brand-logo__mark")).toBeInTheDocument();
  });
});
